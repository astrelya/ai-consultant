import asyncio
from typing import List
from fastapi import WebSocket, WebSocketDisconnect

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WebSocketManager] Connected clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"[WebSocketManager] Connected clients remaining: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        """Broadcast text message to all connected clients."""
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                # Connection might have died, clean up
                self.disconnect(connection)

    async def broadcast_json(self, data: dict):
        """Broadcast JSON data to all connected clients."""
        for connection in list(self.active_connections):
            try:
                await connection.send_json(data)
            except Exception:
                self.disconnect(connection)

# Global manager instance
manager = ConnectionManager()

# Registry of pending async user-input requests.
# Maps job_id -> {"event": asyncio.Event, "value": str}
pending_inputs: dict = {}

async def broadcast_log(message: str, job_id: str = None, level: str = "INFO"):
    """
    Broadcasts log messages in real-time. Logs will be rendered in the frontend.
    """
    payload = {
        "type": "log",
        "job_id": job_id,
        "message": message,
        "level": level
    }
    await manager.broadcast_json(payload)
    print(f"[{level}] {message}")

async def start_heartbeat(job_id: str, interval: int = 8) -> asyncio.Task:
    """
    Starts a background task that broadcasts a 'thinking' pulse every `interval`
    seconds so the frontend chat shows the agent is still alive.
    Cancel the returned task when the job finishes.
    """
    async def _pulse():
        try:
            while True:
                await asyncio.sleep(interval)
                await manager.broadcast_json({
                    "type": "thinking",
                    "job_id": job_id,
                })
        except asyncio.CancelledError:
            pass

    return asyncio.create_task(_pulse())

async def broadcast_input_required(prompt: str, job_id: str, timeout: int = 120) -> str:
    """
    Sends an 'input_required' event to the frontend dashboard and waits for
    the user to submit a value via the /api/jobs/input_response endpoint.
    Falls back to empty string if timeout expires.
    """
    event = asyncio.Event()
    pending_inputs[job_id] = {"event": event, "value": ""}
    
    await manager.broadcast_json({
        "type": "input_required",
        "job_id": job_id,
        "prompt": prompt,
    })
    print(f"[INPUT REQUIRED] Waiting for user input for job {job_id}...")

    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        print(f"[INPUT REQUIRED] Timed out waiting for user input for job {job_id}.")

    result = pending_inputs.pop(job_id, {}).get("value", "")
    return result
