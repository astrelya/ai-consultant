"""
POST /projects/{project_id}/execute route (Story 5.1 & 5.2).

Acquires the process-level execution lock before starting any ticket work and
releases it only after all ticket statuses have been updated.  While the lock
is held any concurrent request to this endpoint receives 409 Conflict.

Rules (from architecture & story dev notes):
- AD-2: Global sequential execution lock — system-wide, not per-project.
- AD-9: All handlers must be async def; use asyncio.Lock, not threading.Lock.
- Lock is acquired before the first ticket begins and released after the last
  ticket's work is committed (status updated in DB + branch committed/pushed).
- Story 5.2: SupervisorAgent.run_tickets() is called inside the lock and
  receives the project_id and ticket_ids so it can load state from the DB
  and publish SSE events throughout execution.
"""
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import execution_lock as _el
from backend.store import project_store
from agents.supervisor_agent import SupervisorAgent

router = APIRouter()


class ExecuteRequest(BaseModel):
    ticket_ids: list[str]


@router.post("/projects/{project_id}/execute", status_code=200)
async def execute_tickets_endpoint(project_id: uuid.UUID, body: ExecuteRequest) -> dict:
    """
    Start sequential ticket execution for the given project.

    Returns:
        200 {"ok": True, "results": [...]}  — execution completed.
        404               — project not found.
        409               — another execution is already in progress.
    """
    # 409 guard: fail fast if another execution is running (AD-2)
    if _el.is_execution_running():
        raise HTTPException(
            status_code=409,
            detail="Execution already in progress. Only one execution may run at a time.",
        )

    # Validate project exists before acquiring the lock
    project = await project_store.get_project(str(project_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    lock = _el.get_execution_lock()
    async with lock:
        # Double-check inside the lock (guards against race between the is_locked
        # check above and actually acquiring the lock)
        if not lock.locked():
            # Shouldn't happen, but be defensive
            raise HTTPException(
                status_code=409,
                detail="Execution already in progress.",
            )

        # Mark every requested ticket as In Progress in the DB
        for ticket_id in body.ticket_ids:
            await project_store.update_ticket_status(str(project_id), ticket_id, "In Progress")

        # --- Story 5.2: SupervisorAgent execution ---------------------------
        # SupervisorAgent loads ticket context from the project store, delegates
        # to the appropriate developer sub-agent (AGENT_MODE), publishes SSE
        # events, runs tests, and updates ticket status before returning.
        # The lock is held for the full duration; it is released only after
        # the agent has updated every ticket status.
        supervisor = SupervisorAgent()
        execution_result = await supervisor.run_tickets(
            project_id=str(project_id),
            ticket_ids=body.ticket_ids,
        )

    return {"ok": True, "results": execution_result.get("results", [])}
