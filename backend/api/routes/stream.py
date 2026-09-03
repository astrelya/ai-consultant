import asyncio
import json
import os
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.api.sse import SSEManager
from backend.api.workspace_watcher import start_watcher, stop_watcher
from backend.store import project_store

router = APIRouter()

@router.get("/stream/{project_id}")
async def stream_project(project_id: str, request: Request):
    project = await project_store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    queue = asyncio.Queue()
    manager = SSEManager.get_instance()
    manager.register(project_id, queue)

    # Story 6.3 AC-5: start filesystem watcher for local-mode projects whose
    # workspace_path has been persisted by a prior ticket run (AC-6).
    agent_mode = os.environ.get("AGENT_MODE", "remote").lower()
    agent_memory = project.get("agent_memory") or {}
    workspace_path = agent_memory.get("workspace_path") if isinstance(agent_memory, dict) else None
    if agent_mode == "local" and workspace_path and os.path.isdir(workspace_path):
        try:
            loop = asyncio.get_running_loop()
            start_watcher(project_id, workspace_path, loop)
        except Exception:
            pass

    async def event_generator():
        try:
            connected_data = {"project_id": project_id}
            yield f"event: connected\ndata: {json.dumps(connected_data)}\n\n"
            
            while True:
                if await request.is_disconnected():
                    break
                    
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield message
                except asyncio.TimeoutError:
                    continue
        finally:
            manager.unregister(project_id, queue)
            if project_id not in manager.queues:
                stop_watcher(project_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
