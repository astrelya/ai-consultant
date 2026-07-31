---
baseline_commit: d23c04e3a202c28cbef352651d6ba638fcc60f7c
---

# Story 4.1: Ticket Generation from Spec

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the system to generate a set of implementation tickets from my confirmed Spec via a single LLM call,
so that I have a structured, reviewable plan before any code is written.

## Acceptance Criteria

1. **Given** a confirmed Spec exists for the current project
   **When** I request ticket generation (e.g. "generate tickets" or "create a plan")
   **Then** exactly one LLM call is made to generate the full ticket set
   **And** each ticket is stored in the project's `ticket_history` in PostgreSQL with: `id` (UUID), `title`, `description`, `acceptance_criteria`, `status` (`Pending`), `blocking` (list of ticket IDs), `blocked_by` (list of ticket IDs)
   **And** a `tickets_generated` SSE event is published so the frontend can render them
   **And** subsequent requests to view tickets do not trigger additional LLM calls
   **And** if no Spec exists, the backend returns a `400` with a clear message — ticket generation is not started

## Tasks / Subtasks

- [x] Task 1: Create Ticket generation endpoint (AC: 1)
  - [x] Add `POST /projects/{project_id}/tickets/generate` to `backend/api/routes/projects.py`.
  - [x] Ensure it returns 400 if `spec` is empty or None.
- [x] Task 2: Implement LLM ticket generation logic (AC: 1)
  - [x] Use `langchain_google_genai.ChatGoogleGenerativeAI` with `os.environ.get("TICKET_MODEL", "gemini-2.5-flash")`.
  - [x] Use `with_structured_output` or a Pydantic schema to parse the LLM output into a list of tickets.
  - [x] Ensure exactly *one* LLM call is made. Use `await llm.ainvoke(...)`.
  - [x] Handle potential Gemini response list content: `if isinstance(content_raw, list): ...`
- [x] Task 3: Store tickets in Project Store (AC: 1)
  - [x] Create `save_generated_tickets(project_id: str, tickets: list[dict])` in `backend/store/project_store.py`.
  - [x] Generate UUIDs for tickets in Python.
  - [x] Update `ticket_history` JSONB column with the list of tickets.
- [x] Task 4: Publish SSE event (AC: 1)
  - [x] In the endpoint, call `SSEManager.get_instance().publish(project_id, "tickets_generated", json_payload)` (from `backend/api/sse.py`).
- [x] Task 5: Add tests
  - [x] Add `tests/test_ticket_generation.py` using `pytest`.
  - [x] Mock LLM call and ensure route succeeds if spec exists and fails with 400 if not.

## Dev Notes

- **Relevant architecture patterns and constraints:**
  - **AD-4 (LLM-as-last-resort):** Here we explicitly *need* the LLM. But only exactly *one* call.
  - **AD-7 (Streaming over polling):** We must publish a `tickets_generated` SSE event.
  - **AD-9 (Async throughout):** The route handler must be `async def`.
  - **AD-13 (Config from env vars):** The LLM model name comes from `TICKET_MODEL` (default `gemini-2.5-flash`).
  - **Project Context Rules:** LangChain calls must be async (`ainvoke`). "LLM content responses can be a list when using Gemini multimodal responses."
- **Source tree components to touch:**
  - `backend/api/routes/projects.py` (add endpoint)
  - `backend/store/project_store.py` (add store logic)
  - `tests/test_ticket_generation.py` (new test)
- **Testing standards summary:**
  - `pytest` only. Files in `tests/` with `test_` prefix.

### Project Structure Notes

- Use `os.environ.get("TICKET_MODEL", "gemini-2.5-flash")` for the LLM.
- Don't expose `agent_memory` in GET routes.
- `project_store.py` handles DB interactions asynchronously via asyncpg pool (`backend.store.database.get_pool()`). Never call `init_pool()` in `project_store.py`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 4]
- [Source: _bmad-output/project-context.md#Critical Implementation Rules]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md]

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro (High)

### Debug Log References
- `backend/api/routes/projects.py`: implemented `/projects/{project_id}/tickets/generate` with structured LLM output.
- `backend/store/project_store.py`: added `save_generated_tickets` to append tickets to `ticket_history`.
- `tests/test_ticket_generation.py`: added comprehensive test suite with `AsyncMock`s for database, SSE and LLM.

### Completion Notes List
- ✅ Implemented POST `/projects/{project_id}/tickets/generate`.
- ✅ Setup structured generation of tickets via `langchain_google_genai`.
- ✅ Handled missing specs and valid specs gracefully.
- ✅ Successfully pushed `tickets_generated` SSE events.
- ✅ Stored correctly inside the Project database.
- ✅ Tests cover success case and missing spec case, completely passing the suite.

### File List
- `backend/api/routes/projects.py`
- `backend/store/project_store.py`
- `tests/test_ticket_generation.py`
