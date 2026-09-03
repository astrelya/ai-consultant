"""POST /projects/{project_id}/chat — single unified path.

The LLM decides on its own when to invoke tools (save_spec, generate_tickets,
execute_pending_tickets). No more keyword pipeline in the route: the agent is
one thing.
"""
import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.chat.context import build_session_context_preamble
from backend.chat.llm_chat import stream_chat_reply
from backend.store import project_store

router = APIRouter()
logger = logging.getLogger(__name__)


async def _safe_append(
    project_id: str, role: str, content: str, metadata: dict | None = None
) -> None:
    """Persist a chat message, swallowing errors so chat delivery is never blocked."""
    try:
        await project_store.append_chat_message(project_id, role, content, metadata)
    except Exception as exc:
        logger.warning("append_chat_message failed for project %s: %s", project_id, exc)


class ChatMessage(BaseModel):
    message: str


class ChatResponse(BaseModel):
    status: str
    project_id: str
    message: str
    mode: str


async def _run_agent_turn(project_id: str, preamble: str, message: str) -> None:
    """Background task: stream one LLM turn (with tool calls) and persist the reply."""

    async def _project_getter() -> dict | None:
        return await project_store.get_project(project_id)

    reply = await stream_chat_reply(project_id, preamble, message, _project_getter)
    if reply:
        await _safe_append(project_id, "agent", reply, {"mode": "agent"})


@router.post(
    "/projects/{project_id}/chat",
    response_model=ChatResponse,
    status_code=200,
)
async def chat_endpoint(project_id: uuid.UUID, body: ChatMessage) -> ChatResponse:
    project_id_str = str(project_id)

    project = await project_store.get_project(project_id_str)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    message = body.message
    await _safe_append(project_id_str, "user", message)

    preamble = build_session_context_preamble(project)
    asyncio.create_task(_run_agent_turn(project_id_str, preamble, message))

    return ChatResponse(
        status="accepted",
        project_id=project_id_str,
        message="",
        mode="agent",
    )
