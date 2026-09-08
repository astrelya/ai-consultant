from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import SessionLocal, get_db
from ..deps import get_effective_model_config, get_project_or_404
from ..queue import queue
from ..services.agents.brainstorm import brainstorm_stream
from ..services.agents.ticket_drafter import draft_tickets

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/projects/{project_id}/chat-sessions", response_model=schemas.ChatSessionOut)
def create_session(project_id: str, payload: schemas.ChatSessionCreate, db: Session = Depends(get_db)):
    get_project_or_404(db, project_id)
    s = models.ChatSession(project_id=project_id, title=payload.title)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.get("/projects/{project_id}/chat-sessions", response_model=list[schemas.ChatSessionOut])
def list_sessions(project_id: str, db: Session = Depends(get_db)):
    return (
        db.query(models.ChatSession)
        .filter_by(project_id=project_id)
        .order_by(models.ChatSession.created_at.desc())
        .all()
    )


@router.get("/chat-sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db)):
    s = db.get(models.ChatSession, session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    return {
        "session": schemas.ChatSessionOut.model_validate(s).model_dump(),
        "messages": [schemas.ChatMessageOut.model_validate(m).model_dump() for m in s.messages],
    }


@router.post("/chat-sessions/{session_id}/messages", response_model=schemas.ChatMessageOut)
def post_message_non_streaming(session_id: str, payload: schemas.ChatMessageIn, db: Session = Depends(get_db)):
    """Non-streaming fallback for clients that can't use WebSocket."""
    s = db.get(models.ChatSession, session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    user_msg = models.ChatMessage(session_id=session_id, role="user", content=payload.content)
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)
    return user_msg


@router.websocket("/ws/chat-sessions/{session_id}")
async def ws_chat(websocket: WebSocket, session_id: str):
    await websocket.accept()
    db = SessionLocal()
    try:
        session = db.get(models.ChatSession, session_id)
        if not session:
            await websocket.send_json({"type": "error", "message": "Session not found"})
            await websocket.close()
            return

        model_cfg = get_effective_model_config(db, session.project_id)
        model_name = model_cfg.chat_model
        params = model_cfg.chat_model_params or {}

        while True:
            data = await websocket.receive_json()
            user_content = data.get("content", "").strip()
            if not user_content:
                continue

            # Persist user message
            um = models.ChatMessage(session_id=session_id, role="user", content=user_content)
            db.add(um)
            db.commit()
            db.refresh(um)
            await websocket.send_json({"type": "user_message", "id": um.id, "content": um.content})

            # Build gemini history from previous messages (excluding the one we just added).
            history = []
            prior = (
                db.query(models.ChatMessage)
                .filter(models.ChatMessage.session_id == session_id, models.ChatMessage.id != um.id)
                .order_by(models.ChatMessage.created_at.asc())
                .all()
            )
            for m in prior:
                role = "user" if m.role == "user" else "model"
                history.append({"role": role, "parts": [m.content]})

            # Stream assistant reply
            await websocket.send_json({"type": "assistant_start"})
            assistant_text_parts: list[str] = []
            usage: dict = {}
            try:
                async for chunk in brainstorm_stream(model_name, history, user_content, usage_out=usage, **params):
                    assistant_text_parts.append(chunk)
                    await websocket.send_json({"type": "assistant_delta", "delta": chunk})
            except Exception as e:
                await websocket.send_json({"type": "error", "message": str(e)})
                continue

            full_reply = "".join(assistant_text_parts)
            am = models.ChatMessage(
                session_id=session_id,
                role="assistant",
                content=full_reply,
                model_used=model_name,
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
            )
            db.add(am)
            db.commit()
            db.refresh(am)
            await websocket.send_json({
                "type": "assistant_end",
                "id": am.id,
                "content": full_reply,
                "usage": {
                    "input_tokens": am.input_tokens,
                    "output_tokens": am.output_tokens,
                    "model": model_name,
                },
            })
    except WebSocketDisconnect:
        pass
    finally:
        db.close()


@router.post("/chat-sessions/{session_id}/generate-tickets", response_model=schemas.AgentRunOut)
def generate_tickets(session_id: str, db: Session = Depends(get_db)):
    session = db.get(models.ChatSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    model_cfg = get_effective_model_config(db, session.project_id)
    model_name = model_cfg.chat_model
    params = model_cfg.chat_model_params or {}

    run = models.AgentRun(
        project_id=session.project_id,
        run_type="draft_tickets",
        related_id=session_id,
        model_used=model_name,
        input_summary=f"chat_session={session_id}",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    async def job(sdb, run_id: str):
        s = sdb.get(models.ChatSession, session_id)
        msgs = [{"role": m.role, "content": m.content} for m in s.messages]
        usage: dict = {}
        tickets = draft_tickets(model_name, msgs, usage_out=usage, **params)

        for i, t in enumerate(tickets):
            draft = models.TicketDraft(
                project_id=s.project_id,
                chat_session_id=s.id,
                title=t.get("title", "Untitled"),
                description=t.get("description", ""),
                acceptance_criteria=t.get("acceptance_criteria", []) or [],
                issue_type=t.get("issue_type", "Story"),
                priority=t.get("priority", "Medium"),
                labels=t.get("labels", []) or [],
                epic_link=t.get("suggested_epic_group"),
                order_index=i,
            )
            sdb.add(draft)

        s.status = "ready_for_tickets"
        r = sdb.get(models.AgentRun, run_id)
        r.output_summary = f"Created {len(tickets)} draft(s)"
        r.input_tokens = usage.get("input_tokens")
        r.output_tokens = usage.get("output_tokens")
        sdb.commit()

    queue.submit(run.id, job)
    return run
