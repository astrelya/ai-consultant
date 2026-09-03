"""LLM tools bound to the chat agent.

The LLM decides when to invoke these based on natural conversation — no more
rigid keyword pipeline in the route handler. Each tool closes over the project
id so the LLM never needs to know identifiers.

Design constraints:
- Every tool returns a short string. That string is fed back to the LLM as a
  `ToolMessage` and shapes its next reply.
- Long-running actions (like `execute_pending_tickets`) fire-and-forget a
  background coroutine so the LLM stream is never blocked.
- Side effects (spec saved, tickets generated, execution started) always emit
  SSE events so the UI surfaces (spec preview card, ticket cards, execution
  status block) update independently of the LLM's textual reply.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from langchain_core.tools import tool

from backend import execution_lock as _el
from backend.api.sse import publish_event
from backend.chat.actions import generate_tickets_from_spec
from backend.store import project_store, spec_store

logger = logging.getLogger(__name__)


ProjectGetter = Callable[[], Awaitable[dict | None]]


def build_tools(project_id: str, project_getter: ProjectGetter) -> list:
    """Return the list of tools bound for this project."""

    @tool
    async def save_spec(spec_text: str) -> str:
        """Persist the provided text as the project's canonical specification.

        Call this once you and the user agree on the spec content. Pass the
        FULL spec markdown, not a summary or a filename. After saving, tell the
        user the spec was saved and propose the next step (generate tickets).
        """
        if not spec_text or not spec_text.strip():
            return "ERROR: spec_text is empty."
        stored = await spec_store.update_project_spec(project_id, spec_text)
        if not stored:
            return "ERROR: failed to save spec to database."
        preview = spec_text[:200] + ("..." if len(spec_text) > 200 else "")
        await publish_event(project_id, "spec_stored", {"preview": preview})
        return f"OK: spec saved ({len(spec_text)} characters)."

    @tool
    async def generate_tickets() -> str:
        """Generate a comprehensive list of implementation tickets from the
        currently-saved spec. Requires a spec to exist — call `save_spec` first
        if none is present.
        """
        project = await project_getter()
        spec = (project or {}).get("spec")
        if not spec:
            return "ERROR: no spec is saved yet. Ask the user for the spec then call save_spec first."
        try:
            tickets = await generate_tickets_from_spec(project_id, spec)
        except Exception as exc:  # noqa: BLE001 — surface message to the LLM
            logger.exception("generate_tickets tool failed")
            return f"ERROR: {exc}"
        titles = ", ".join(t["title"] for t in tickets)
        return f"OK: generated {len(tickets)} ticket(s): {titles}"

    @tool
    async def execute_pending_tickets() -> str:
        """Kick off sequential execution of every Pending ticket by the
        SupervisorAgent. Fire-and-forget: returns immediately once execution
        starts. Requires at least one Pending ticket.
        """
        project = await project_getter()
        tickets = (project or {}).get("ticket_history") or []
        pending_ids = [
            t["id"]
            for t in tickets
            if isinstance(t, dict) and t.get("status") in (None, "Pending")
        ]
        if not pending_ids:
            return "ERROR: no Pending tickets to execute. Generate tickets first."
        if _el.is_execution_running():
            return "ERROR: another execution is already running."
        asyncio.create_task(_run_supervisor(project_id, pending_ids))
        return f"OK: execution started on {len(pending_ids)} ticket(s)."

    @tool
    async def get_project_state() -> str:
        """Return a compact summary of the project's current state: whether a
        spec is saved, how many tickets exist and their statuses. Use before
        deciding whether to save a new spec or generate/execute tickets.
        """
        project = await project_getter()
        if not project:
            return "ERROR: project not found."
        spec = project.get("spec")
        tickets = project.get("ticket_history") or []
        by_status: dict[str, int] = {}
        for t in tickets:
            if isinstance(t, dict):
                by_status[t.get("status", "Pending")] = by_status.get(t.get("status", "Pending"), 0) + 1
        spec_line = f"spec: {'saved (' + str(len(spec)) + ' chars)' if spec else 'not saved'}"
        tickets_line = (
            "tickets: " + ", ".join(f"{k}={v}" for k, v in by_status.items())
            if by_status
            else "tickets: none"
        )
        return f"{spec_line}; {tickets_line}"

    return [save_spec, generate_tickets, execute_pending_tickets, get_project_state]


async def _run_supervisor(project_id: str, ticket_ids: list[str]) -> None:
    """Background: acquire the execution lock, mark tickets In Progress, run agent."""
    from agents.supervisor_agent import SupervisorAgent  # heavy import: lazy

    lock = _el.get_execution_lock()
    async with lock:
        for tid in ticket_ids:
            try:
                await project_store.update_ticket_status(project_id, tid, "In Progress")
            except Exception as exc:
                logger.warning("update_ticket_status failed for %s/%s: %s", project_id, tid, exc)
        try:
            supervisor = SupervisorAgent()
            await supervisor.run_tickets(project_id=project_id, ticket_ids=ticket_ids)
        except Exception as exc:
            logger.exception("SupervisorAgent.run_tickets failed")
            await publish_event(
                project_id,
                "chat_error",
                {"error": f"Execution failed: {exc}"},
            )
