"""
SDD Web API routes
Exposes the SDD pipeline to the dashboard: pipeline lifecycle, gate approvals,
live progress (SSE) and ticket listing.
"""
import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.runner import runner
from core.artifacts import read_artifact
from tools.ticket_manager import TicketManager
from tools.mcp_loader import MCPManager

router = APIRouter(prefix="/api")


class StartPipelineRequest(BaseModel):
    ticket_id: str
    mode: str | None = None  # "local" | "remote"; defaults to AGENT_MODE env


class ApproveRequest(BaseModel):
    approved: bool
    feedback: str = ""


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/tickets")
async def list_tickets():
    manager = TicketManager()
    tickets = await manager.get_todo_tickets()
    return {"tickets": tickets}


@router.get("/pipelines")
async def list_pipelines():
    return {"pipelines": await runner.list_pipelines()}


@router.post("/pipelines")
async def start_pipeline(req: StartPipelineRequest):
    thread_id = await runner.start_pipeline(req.ticket_id, req.mode)
    return {"thread_id": thread_id, "status": "started"}


@router.get("/pipelines/{thread_id}")
async def pipeline_detail(thread_id: str):
    info = await runner.get_state(thread_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Pipeline {thread_id} not found")

    state = info["state"]
    repo_name = (state.get("repo_full_name") or "").split("/")[-1]
    ticket_id = state.get("ticket_id", "")
    artifacts = {}
    if repo_name and ticket_id:
        for name in ("spec.md", "plan.md", "tasks.md"):
            content = read_artifact(repo_name, ticket_id, name)
            if content is not None:
                artifacts[name] = content
    info["artifacts"] = artifacts
    return info


@router.post("/pipelines/{thread_id}/approve")
async def approve_pipeline(thread_id: str, req: ApproveRequest):
    info = await runner.get_state(thread_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Pipeline {thread_id} not found")
    if info["running"]:
        raise HTTPException(status_code=409, detail="Pipeline is currently running.")
    if not info["pending_gate"]:
        raise HTTPException(status_code=409, detail="Pipeline has no pending gate approval.")

    await runner.resume_pipeline(thread_id, req.approved, req.feedback)
    return {"thread_id": thread_id, "status": "resuming", "approved": req.approved}


@router.get("/pipelines/{thread_id}/events")
async def pipeline_events(thread_id: str):
    """Server-Sent Events stream of pipeline progress (2s polling)."""

    async def event_stream():
        last = None
        while True:
            info = await runner.get_state(thread_id)
            if info is None:
                yield f"data: {json.dumps({'error': 'pipeline not found'})}\n\n"
                break

            state = info["state"]
            snapshot = {
                "status": state.get("status"),
                "next": info["next"],
                "pending_gate": bool(info["pending_gate"]),
                "running": info["running"],
                "task_index": state.get("current_task_index", 0),
                "tasks_total": len(state.get("tasks", [])),
            }
            if snapshot != last:
                yield f"data: {json.dumps(snapshot)}\n\n"
                last = snapshot

            terminal = state.get("status") in ("completed", "failed")
            if not info["running"] and not info["pending_gate"] and terminal:
                break
            await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
