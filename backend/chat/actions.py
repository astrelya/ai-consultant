"""Action handlers reused by the chat route and the ticket/execute REST endpoints.

Extracted from `backend/api/routes/projects.py` (which had two live bugs:
`await SSEManager.get_instance()` — not an awaitable — and `sse_manager.publish`
— no such method). The correct SSE call is the module-level `publish_event`
coroutine from `backend/api/sse.py`.
"""
from __future__ import annotations

import logging
import os
import uuid

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from agents import token_tracker
from backend.api.sse import publish_event
from backend.store import project_store

logger = logging.getLogger(__name__)


class _GeneratedTicket(BaseModel):
    title: str
    description: str
    acceptance_criteria: str


class _TicketGenerationResult(BaseModel):
    tickets: list[_GeneratedTicket]


async def generate_tickets_from_spec(project_id: str, spec: str) -> list[dict]:
    """Ask the LLM for a ticket breakdown, persist it, and publish SSE.

    Raises ValueError if the spec is empty. Returns the persisted tickets.
    """
    if not spec:
        raise ValueError("spec is empty")

    model_name = os.environ.get("TICKET_MODEL", "gemini-2.5-flash")
    llm = ChatGoogleGenerativeAI(model=model_name)
    structured_llm = llm.with_structured_output(_TicketGenerationResult)

    prompt = (
        "Based on the following specification, generate a comprehensive set of "
        "implementation tickets. Each ticket should have a clear title, a "
        "concise description, and testable acceptance criteria.\n\n"
        f"Spec:\n{spec}"
    )

    token_tracker.CURRENT_PROJECT_ID.set(project_id)
    token_tracker.CURRENT_SESSION_ID.set(f"chat-{project_id}")
    result = await token_tracker.tracked_ainvoke(
        structured_llm, prompt,
        project_id=project_id, session_id=f"chat-{project_id}",
    )

    tickets: list[dict] = []
    for t in result.tickets:
        tickets.append({
            "id": str(uuid.uuid4()),
            "title": t.title,
            "description": t.description,
            "acceptance_criteria": t.acceptance_criteria,
            "status": "Pending",
            "blocking": [],
            "blocked_by": [],
        })

    await project_store.save_generated_tickets(project_id, tickets)
    await publish_event(project_id, "tickets_generated", {"tickets": tickets})
    return tickets
