import asyncio
import json
from typing import Dict, Set

class SSEManager:
    _instance = None
    
    def __init__(self):
        # Maps project_id to a set of queues
        self.queues: Dict[str, Set[asyncio.Queue]] = {}
        
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SSEManager()
        return cls._instance
        
    def register(self, project_id: str, queue: asyncio.Queue):
        if project_id not in self.queues:
            self.queues[project_id] = set()
        self.queues[project_id].add(queue)
        
    def unregister(self, project_id: str, queue: asyncio.Queue):
        if project_id in self.queues:
            self.queues[project_id].discard(queue)
            if not self.queues[project_id]:
                del self.queues[project_id]

async def publish_event(project_id: str, event_type: str, data: dict):
    manager = SSEManager.get_instance()
    if project_id not in manager.queues:
        return
        
    event_str = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    
    for queue in list(manager.queues[project_id]):
        try:
            queue.put_nowait(event_str)
        except asyncio.QueueFull:
            pass
