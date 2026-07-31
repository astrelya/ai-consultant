"""
POST /projects/{project_id}/chat — unified chat endpoint handling brainstorm and spec review intents.

Rules:
- Route handler is async def (AD-9).
- Validates project_id exists; returns 404 if not found.
- Spec review intent: keyword-based detection, no LLM call (AD-4).
- Subprocess invocation is fire-and-forget (asyncio.create_task) to return 200 quickly.
- SSE events are published via publish_event() for each subprocess output line.
"""
import asyncio
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.store import project_store, spec_store
from backend.api.sse import publish_event
from backend.chat.intent_detector import detect_brainstorm_intent, detect_spec_review_intent, detect_direct_implementation_intent
from backend.chat.subprocess_runner import run_brainstorm_pipeline, run_spec_review_pipeline


router = APIRouter()


class ChatMessage(BaseModel):
    message: str


class ChatResponse(BaseModel):
    status: str
    project_id: str
    message: str
    mode: str


@router.post(
    "/projects/{project_id}/chat",
    response_model=ChatResponse,
    status_code=200,
)
async def chat_endpoint(
    project_id: uuid.UUID,
    body: ChatMessage,
) -> ChatResponse:
    """Handle an incoming chat message for the given project.

    Detects intent (spec review, brainstorm, or generic) and routes accordingly.

    Spec review mode:
    - If message contains spec review keywords, the validation subprocess is launched
      fire-and-forget. Progress is streamed via SSE.

    Brainstorm mode:
    - If message contains brainstorm keywords, the brainstorm subprocess is launched
      fire-and-forget. Progress is streamed via SSE.

    Generic messages:
    - Acknowledged but not processed further (deferred to Story 4.1+).

    Returns 404 if the project does not exist.
    """
    project_id_str = str(project_id)

    project = await project_store.get_project(project_id_str)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    message = body.message

    if detect_direct_implementation_intent(message):
        asyncio.create_task(
            _run_direct_implementation_and_store(project_id_str, message)
        )
        return ChatResponse(
            status="accepted",
            project_id=project_id_str,
            message="Spec saved for implementation. Next: Generate Tickets or Execute Directly.",
            mode="direct_implementation",
        )

    if detect_spec_review_intent(message):
        asyncio.create_task(
            _run_spec_review_and_store(project_id_str, message)
        )
        return ChatResponse(
            status="accepted",
            project_id=project_id_str,
            message="Spec review pipeline started. Watch the SSE stream for progress.",
            mode="spec_review",
        )

    if detect_brainstorm_intent(message):
        asyncio.create_task(
            _run_brainstorm_and_store(project_id_str, message)
        )
        return ChatResponse(
            status="accepted",
            project_id=project_id_str,
            message="Brainstorm pipeline started. Watch the SSE stream for progress.",
            mode="brainstorm",
        )

    # Generic message — no pipeline triggered (deferred to Story 4.1+)
    return ChatResponse(
        status="received",
        project_id=project_id_str,
        message="Message received.",
        mode="generic",
    )


async def _run_spec_review_and_store(project_id: str, spec_input: str) -> None:
    """Background task: run spec review pipeline and store validated spec."""
    result = await run_spec_review_pipeline(project_id, spec_input)

    if result.get("complete") and result.get("exit_code") == 0:
        spec_content = result.get("spec_content", "")
        if spec_content:
            stored = await spec_store.update_project_spec(project_id, spec_content)
            if stored:
                # Emit spec_stored event with preview
                preview = spec_content[:200] + ("..." if len(spec_content) > 200 else "")
                await publish_event(project_id, "spec_stored", {"preview": preview})
            else:
                await publish_event(
                    project_id,
                    "spec_store_error",
                    {"error": "Failed to save validated spec to database"},
                )
        else:
            await publish_event(
                project_id,
                "spec_store_error",
                {"error": "Spec review completed but produced no spec content"},
            )
    else:
        error_msg = result.get("error", "Unknown error")
        await publish_event(
            project_id,
            "bmad_error",
            {"exit_code": result.get("exit_code", -1), "error": error_msg},
        )


async def _run_brainstorm_and_store(project_id: str, user_input: str) -> None:
    """Background task: run brainstorm pipeline and store resulting spec."""
    result = await run_brainstorm_pipeline(project_id, user_input)

    if result.get("complete") and result.get("exit_code") == 0:
        spec_content = result.get("spec_content", "")
        if spec_content:
            stored = await spec_store.update_project_spec(project_id, spec_content)
            if stored:
                preview = spec_content[:200] + ("..." if len(spec_content) > 200 else "")
                await publish_event(project_id, "spec_stored", {"preview": preview})
            else:
                await publish_event(
                    project_id,
                    "spec_store_error",
                    {"error": "Failed to save brainstorm spec to database"},
                )
        else:
            await publish_event(
                project_id,
                "spec_store_error",
                {"error": "Brainstorm completed but produced no spec content"},
            )
    else:
        error_msg = result.get("error", "Unknown error")
        await publish_event(
            project_id,
            "bmad_error",
            {"exit_code": result.get("exit_code", -1), "error": error_msg},
        )


async def _run_direct_implementation_and_store(project_id: str, message: str) -> None:
    """Background task: store the spec for direct implementation."""
    # Extract the spec by removing the keyword trigger line if it exists at the start
    lines = message.split('\n')
    spec_content = message
    if lines and detect_direct_implementation_intent(lines[0]):
        spec_content = '\n'.join(lines[1:]).lstrip()
    
    if spec_content:
        stored = await spec_store.update_project_spec(project_id, spec_content)
        if stored:
            preview = spec_content[:200] + ("..." if len(spec_content) > 200 else "")
            await publish_event(project_id, "spec_stored", {"preview": preview})
        else:
            await publish_event(
                project_id,
                "spec_store_error",
                {"error": "Failed to save direct implementation spec to database"},
            )
    else:
        await publish_event(
            project_id,
            "spec_store_error",
            {"error": "No spec content found after extracting from message"},
        )
