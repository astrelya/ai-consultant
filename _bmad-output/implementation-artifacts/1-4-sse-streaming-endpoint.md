---
baseline_commit: d23c04e3a202c28cbef352651d6ba638fcc60f7c
---

# Story 1.4: SSE Streaming Endpoint

Status: in-progress

## Story

As a developer,
I want an SSE endpoint that the frontend can subscribe to per project,
So that real-time agent output can be pushed to the client without polling, ready for use by the execution engine in Epic 5.

## Acceptance Criteria

1. **Given** the backend is running
   **When** a client connects to `GET /stream/{project_id}` with `Accept: text/event-stream`
   **Then** the response has `Content-Type: text/event-stream` and immediately sends an event: `event: connected\ndata: {"project_id": "<id>"}\n\n`
2. **And** the connection stays open until the client disconnects
3. **And** a helper `publish_event(project_id, event_type, data)` async function exists that, when called, sends a formatted SSE event to all active subscribers for that project
4. **And** `GET /stream/{nonexistent-project-id}` returns 404 before upgrading to SSE
5. **And** the endpoint handles client disconnect gracefully without crashing the server

## Tasks / Subtasks

- [x] Task 1: Create an `SSEManager` to track connections and `publish_event` helper in `backend/api/sse.py`.
  - [x] Implement `SSEManager` singleton to maintain `asyncio.Queue` per active connection grouped by `project_id`.
  - [x] Implement `async def publish_event(project_id: str, event_type: str, data: dict)` helper which iterates over the project's queues and puts the formatted message in each.
- [x] Task 2: Implement the `GET /stream/{project_id}` route in a new `backend/api/routes/stream.py` module.
  - [x] Validate `project_id` using `project_store.get_project(str(project_id))`. If None, raise `HTTPException(404)`.
  - [x] Setup `asyncio.Queue` for the client and register it with `SSEManager`.
  - [x] Define an `async def event_generator()` that yields the initial `connected` event, then loops reading from the queue and yielding to the client.
  - [x] Ensure a `finally` block or `request.is_disconnected()` handles client disconnect gracefully, removing the queue from `SSEManager`.
  - [x] Return a `StreamingResponse(event_generator(), media_type="text/event-stream")`.
- [x] Task 3: Register the `stream` router in `backend/main.py`.
  - [x] `from backend.api.routes.stream import router as stream_router`
  - [x] `app.include_router(stream_router)`
- [x] Task 4: Write tests in `tests/test_stream_endpoint.py`.
  - [x] Use `httpx.AsyncClient` or FastAPI `TestClient` (though `TestClient` with `with client.stream("GET", ...)` can test SSE).
  - [x] Mock `project_store.get_project` to test 404 on nonexistent project.
  - [x] Test successful connection and initial event.
  - [x] Test that calling `publish_event` puts an event in the stream.

### Review Findings

#### Epic 1 Review (2026-09-01)

- [ ] [Review][Patch] `await SSEManager.get_instance()` is used in [backend/api/routes/projects.py](backend/api/routes/projects.py) but `get_instance` is a plain classmethod ([backend/api/sse.py:13](backend/api/sse.py#L13)); awaiting a non-awaitable raises `TypeError` the first time ticket generation runs. Drop the `await` (like [backend/api/routes/stream.py:20](backend/api/routes/stream.py#L20) does) or make `get_instance` `async`. [backend/api/routes/projects.py:184]
- [ ] [Review][Patch] `sse_manager.publish(str(project_id), "tickets_generated", {...})` calls a method that does not exist on `SSEManager` — the module-level `publish_event(project_id, event_type, data)` is what Story 1.4 defined. Replace the two call-sites (`generate_tickets_endpoint`, `revise_ticket_endpoint`) with `await publish_event(...)`. [backend/api/routes/projects.py:185, 260]
- [x] [Review][Defer] `SSEManager` register/unregister and event queues have no `maxsize` — slow clients or a runaway publisher can grow queues unboundedly. Not in AC, add a bound + drop-with-log when queues fill. [backend/api/sse.py:20, 36]
- [x] [Review][Defer] `publish_event` swallows `asyncio.QueueFull` silently with no log — hard to diagnose stalled UIs. Add a `logger.warning` when we bound the queue. [backend/api/sse.py:38]
- [x] [Review][Defer] `SSEManager.get_instance` is not concurrency-guarded — asyncio's cooperative scheduling makes it fine in practice, but two tasks first-touching between `await` points could each construct one. Defer. [backend/api/sse.py:13]

## Dev Notes

### Architecture Constraints (MUST FOLLOW)

**AD-7 - Streaming over polling**: Agent log lines and status updates are emitted via Server-Sent Events (SSE) from the backend. The frontend subscribes to an SSE endpoint scoped to the active execution. No polling.
**AD-9 - Async throughout**: Route handlers must be `async def`.
**AD-4 - LLM-as-last-resort**: Zero LLM calls in this infrastructure ticket.
**AD-5 - Project Isolation**: The SSE endpoint must subscribe strictly to the specified `project_id`.

### Implementation Details

- **FastAPI SSE**: Use `fastapi.responses.StreamingResponse` with `media_type="text/event-stream"`. No need for `sse-starlette` unless you want to add it to `requirements.txt`, but `StreamingResponse` with manual string formatting (`f"event: {event_type}\ndata: {json.dumps(data)}\n\n"`) works perfectly.
- **Async Queues**: For each connection, create an `asyncio.Queue()`. The request handler yields from this queue. The `publish_event` function puts messages onto this queue. Use `asyncio.TimeoutError` or check `await request.is_disconnected()` to detect client disconnects.
- **Graceful Cleanup**: Use a `try...finally` block in your `event_generator()` to ensure that when the generator exits (e.g. client disconnects), the queue is removed from the `SSEManager`.
- **Formatting**: Make sure you always end an SSE message with `\n\n`.

### Files to Create / Modify

- `[NEW] backend/api/sse.py`
- `[NEW] backend/api/routes/stream.py`
- `[NEW] tests/test_stream_endpoint.py`
- `[MODIFY] backend/main.py`

### Dev Agent Record
**Implementation Notes:**
- Implemented `SSEManager` using `asyncio.Queue` per active connection.
- `publish_event` correctly iterates through the connected clients for a specific `project_id`.
- Handled client disconnect properly in the `event_generator()` using a `finally` block and `is_disconnected()` checking with `asyncio.wait_for`.
- Added the `stream` router into `main.py`.
- Wrote and passed tests for `test_stream_endpoint.py`.

### Project Context Reference

- **All route handlers are `async def`.**
- **Test files go in `tests/` directory** with prefix `test_`.
- **Use `os.environ.get("KEY", "default")`** everywhere.

## Status

Ultimate context engine analysis completed - comprehensive developer guide created
