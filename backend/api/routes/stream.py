import asyncio
import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.api.sse import SSEManager
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

    return StreamingResponse(event_generator(), media_type="text/event-stream")
