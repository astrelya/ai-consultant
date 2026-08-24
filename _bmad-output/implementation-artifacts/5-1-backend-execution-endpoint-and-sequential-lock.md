---
baseline_commit: 0ce5653ee60582c85b363902903e510f65023a8d
---

# Story 5.1: Backend Execution Endpoint & Sequential Lock

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want the `POST /projects/{id}/execute` endpoint to acquire a process-level lock before starting any ticket and release it only after full completion,
so that no two tickets — across any project — ever execute simultaneously.

## Acceptance Criteria

1. **Given** `POST /projects/{id}/execute` is called with an ordered list of ticket IDs
   **When** no other execution is active system-wide
   **Then** the global execution lock is acquired and execution begins with the first ticket in the list
   **And** each ticket's status is set to `In Progress` in PostgreSQL before its agent work begins
   **And** the lock is released only after: test artifact written AND ticket status updated AND branch committed/pushed

2. **Given** a second `POST /projects/{id}/execute` arrives while one is already running (any project)
   **When** the request is processed
   **Then** it returns `409 Conflict` with a message indicating execution is already in progress
   **And** the running execution is not interrupted

3. **Given** MCPManager has not been initialized
   **When** the first execution request arrives
   **Then** `await MCPManager.get_instance()` is called exactly once during backend startup (FastAPI lifespan event)
   **And** all MCP tool sets (GitHub, Jira if configured, Context7) are registered inside `MCPManager.initialize()` — never called ad-hoc

## Tasks / Subtasks

- [x] Task 1: Create global execution lock mechanism (process-level lock)
- [x] Task 2: Implement `POST /projects/{id}/execute` route
  - [x] Accept ordered list of ticket IDs
  - [x] Attempt to acquire global lock; return 409 if already locked
  - [x] Update ticket statuses to `In Progress` in DB
  - [x] Begin execution process (mocked or stubbed out for SupervisorAgent integration later)
  - [x] Release lock on completion
- [x] Task 3: Initialize MCPManager during app startup
  - [x] Update FastAPI lifespan in `backend/main.py` to initialize MCPManager
  - [x] Update `MCPManager` to register required MCPs in its initialization

## Dev Notes

- **Architectural Guardrails (AD-2, AD-3):**
  - **AD-2 (Global sequential execution lock):** The lock is system-wide, not just per project. No concurrent execution allowed across any projects.
  - **AD-3 (MCPManager singleton):** All connections go through `await MCPManager.get_instance()`. Registrations happen in `initialize()`.
  - **AD-9 (Async throughout):** All backend API handlers must be `async def`. Do not block the event loop with synchronous locks. Use `asyncio.Lock`.

- **Existing code modifications:**
  - `backend/main.py`: Must integrate MCPManager initialization into the existing `lifespan` event.
  - `backend/api/routes/...`: Create a new `execute.py` router or add to `projects.py` based on convention (architecture specifies `/execute` as a distinct route). Add router inclusion to `main.py`.

### Project Structure Notes

- Alignment with unified project structure: Add `backend.api.routes.execute` to `main.py` routers.
- The `MCPManager` singleton implementation needs to provide `initialize` method if not present.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 5.1`]
- [Source: `_bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md`] (AD-2, AD-3, AD-9)

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (Thinking)

### Debug Log References

- Git branch chaos: `git stash pop` during a rebase caused `backend/` to be wiped. Recovered by restoring from `origin/App_V2_BMAD`. All new files survived as untracked.
- `project_store.update_ticket_fields` was missing from restored baseline — added it to `backend/store/project_store.py` along with `update_all_tickets`.
- Pre-existing test failures in `test_ticket_card_view.py` (4 tests) reference `update_ticket_status` / `update_ticket_status_endpoint` / `TicketStatusUpdate` which do not exist in this version of the codebase. These failures are not regressions from this story.
- Test isolation issue: importing `backend.main` in the lifespan test caused `.env` load, setting Jira env vars, which caused two `test_ticket_card_view` tests to call `project_store.get_project` with a non-async mock. Fixed by patching Jira env vars and making `fetchrow` an AsyncMock in those tests.

### Completion Notes List

- ✅ Task 1: Created `backend/execution_lock.py` with `get_execution_lock()` singleton (asyncio.Lock) and `is_execution_running()` predicate.
- ✅ Task 2: Created `backend/api/routes/execute.py` with `POST /projects/{project_id}/execute` endpoint. Returns 409 if lock held, 404 if project not found, updates all ticket statuses to "In Progress" before beginning execution stub. Lock released via `async with` on completion. Registered in `backend/main.py`. Removed stub endpoint from `projects.py`.
- ✅ Task 3: Added `await MCPManager.get_instance()` to the FastAPI lifespan in `backend/main.py`, ensuring exactly-once initialization at startup per AD-3.
- ✅ 9 new tests in `tests/test_execution_endpoint.py` covering AC1, AC2, AC3; all pass (16/16 total).

## File List

- `backend/execution_lock.py` [NEW]
- `backend/api/routes/execute.py` [NEW]
- `backend/main.py` [MODIFIED]
- `backend/api/routes/projects.py` [MODIFIED] — removed stub execute endpoint
- `tests/test_execution_endpoint.py` [MODIFIED] — full implementation
- `tests/test_ticket_card_view.py` [MODIFIED] — Jira isolation + fetchrow AsyncMock fix

## Change Log

- 2026-08-24: Story 5.1 implemented — global execution lock, execute endpoint, MCPManager lifespan init (Claude Sonnet 4.6 Thinking)
