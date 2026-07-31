---
baseline_commit: HEAD
---

# Story 3.5: Direct Implementation Mode

Status: review

## Story

As a user,
I want to provide a Spec and explicitly request implementation without any review dialogue,
So that I can skip validation and proceed directly to execution when I already have a complete spec.

## Acceptance Criteria

1. **Given** I send a message such as "implement this spec: <spec content>" or "use this spec and build it"
   **When** the backend detects direct implementation intent
   **Then** the Chat View header highlights the Implement mode button
   **And** no validation prompts or gap analysis are shown
   **And** the Spec is saved immediately via dual-location storage (Story 3.2)
   **And** the app confirms the Spec is stored and asks which path to take next: generate tickets or execute directly

2. **Given** Jira is not configured
   **When** the direct path is confirmed
   **Then** execution can begin from spec confirmation — no approval gate is required

## Tasks / Subtasks

- [x] Task 1: Implement direct implementation intent detection in backend
  - [x] Extend `backend/chat/intent_detector.py` to detect direct implementation intent (e.g. keywords like "implement this spec", "build this spec").
  - [x] Must be keyword-based matching (case-insensitive), NO LLM calls (AD-4).

- [x] Task 2: Implement direct implementation chat endpoint
  - [x] Extend `backend/api/routes/chat.py` to handle direct implementation intent.
  - [x] Immediately extract the spec content from the user's message.
  - [x] Call the internal dual-location spec storage logic (used in `POST /projects/{id}/spec` from Story 3.2) to save the spec.
  - [x] Return a confirmation message prompting the user to either "generate tickets" or "execute directly".

- [x] Task 3: Frontend intent detection and button highlight
  - [x] Modify `frontend/app/projects/[id]/ChatInterface.tsx` (and/or relevant components) to highlight the Implement mode button when this path is taken.
  - [x] Ensure the confirmation prompt and action buttons (Generate Tickets, Execute Directly) are displayed.

- [x] Task 4: Tests
  - [x] Add integration tests for direct implementation mode in `tests/test_direct_implementation.py` or extend existing chat tests.

## Dev Notes

### What This Story Builds
This story implements the **Direct Implementation Mode**, providing a fast-path for users who already have a complete spec. Unlike the Spec Review Mode (Story 3.4), this path skips BMad validation subprocesses entirely, directly saving the spec and prompting for the next phase (Ticket Generation or Execution).

### Architecture Constraints (MUST FOLLOW)
- **AD-4 — LLM-as-last-resort:** Intent detection MUST use simple string/regex matching, not an LLM.
- **AD-9 — Async throughout:** All backend routes are `async def`. Storage operations must be awaited.
- **AD-10 — Frontend-backend boundary:** The frontend only interacts via REST/SSE.

### Previous Story Intelligence (from Story 3.4)
- **Intent Detection Pattern:** `backend/chat/intent_detector.py` was introduced in Story 3.4. Follow the same simple keyword matching pattern established there.
- **Storage Logic:** You can likely reuse or abstract the storage logic already present in `POST /projects/{id}/spec` (Story 3.2).
- **Frontend Changes:** Follow the same button highlighting pattern added to `ChatInterface.tsx` in Story 3.4.

### Project Context Rules
- **All route handlers are async def**.
- **Use `os.environ.get()`** everywhere.
- **MCPManager is a singleton**, though not directly needed for this UI transition, ensure no new event loops or sync blocking calls are introduced.

## File List
- `backend/chat/intent_detector.py`
- `backend/api/routes/chat.py`
- `frontend/app/projects/[id]/ChatInterface.tsx`
- `tests/test_direct_implementation.py`

## Change Log
- Date: 2026-07-31 - Task 1 complete. Added detect_direct_implementation_intent function and unit tests.
- Date: 2026-07-31 - Task 2 complete. Implemented direct implementation logic in backend chat endpoint and added tests.
- Date: 2026-07-31 - Task 3 complete. Added client-side direct implementation mode detection and UI components.
- Date: 2026-07-31 - Task 4 complete. Integration tests passing for the new implementation mode.

## Dev Agent Record

### Agent Model Used
Gemini 3.1 Pro (High)

### Debug Log References
N/A

### Completion Notes List
- [x] Intent detection implemented (no LLM)
- [x] Spec extracted and saved via dual-location storage
- [x] Confirmation message asks for next step
- [x] All AC passing
- [x] Frontend highlights Implement mode button
- [x] Jira approval gate skipped if Jira not configured
- [x] Tests passing

Ultimate context engine analysis completed - comprehensive developer guide created
