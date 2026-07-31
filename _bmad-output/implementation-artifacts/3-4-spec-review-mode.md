---
baseline_commit: d23c04e3a202c28cbef352651d6ba638fcc60f7c
---

# Story 3.4: Spec Review Mode

Status: review

## Story

As a user,
I want to paste an existing spec into chat and have the agent analyze it for gaps and guide me through refinement,
So that I can harden an incomplete or rough spec into a validated one before implementation begins.

## Acceptance Criteria

1. **Given** I paste a spec document into the Chat View
   **When** the backend detects spec review intent
   **Then** the Chat View header highlights the Spec Review mode button
   **And** the BMad validation subprocess is invoked and streams its analysis output via SSE
   **And** the analysis produces at least one structured gap or clarifying question before accepting the spec

2. **Given** I respond to the clarifying questions
   **When** the dialogue reaches a validated state
   **Then** the refined Spec is saved via dual-location storage (Story 3.2)
   **And** the Chat View shows a confirmation that the Spec is validated and ready

3. **Given** I paste a spec and the validation finds no gaps
   **When** the pipeline completes
   **Then** the Spec is saved as-is with a message confirming it is complete

## Tasks / Subtasks

- [x] Task 1: Implement spec review intent detection in backend
  - [x] Create or extend `backend/chat/intent_detector.py` to detect spec review intent.
  - [x] Returns `True` if message contains keywords like "review this spec", "analyze this spec".
  - [x] Uses simple string matching (case-insensitive) — not an LLM call.

- [x] Task 2: Implement BMad validation subprocess invocation in backend
  - [x] Extend `backend/chat/subprocess_runner.py` with `async def run_spec_review_pipeline(project_id: str, spec_input: str) -> dict`.
  - [x] Launches the BMad validate subprocess with appropriate command.
  - [x] Streams subprocess stdout to SSE channel via `publish_event(project_id, "bmad_output", line)`.

- [x] Task 3: Implement spec review chat endpoint
  - [x] Extend `backend/api/routes/chat.py` to handle spec review intent.
  - [x] Call `run_spec_review_pipeline` to launch subprocess.
  - [x] Handle responses to clarifying questions.

- [x] Task 4: Frontend intent detection and button highlight
  - [x] Modify `frontend/components/ChatView.tsx` to highlight Spec Review button.

- [x] Task 5: Capture and parse BMad validation output
  - [x] Capture the gaps, clarifying questions, and final refined spec from the subprocess output.

- [x] Task 6: Invoke spec storage after successful validation
  - [x] Call `POST /projects/{id}/spec` (Story 3.2 endpoint) to save the validated spec.

- [x] Task 7: Handling clarifying questions UI
  - [x] Modify `frontend/components/ChatView.tsx` to display questions and allow the user to answer them.
  
- [x] Task 8: Handle validation errors gracefully
  - [x] Emit `bmad_error` and handle it in the frontend.

- [x] Task 9: Tests
  - [x] Write integration tests for spec review mode in `tests/test_spec_review_mode.py`.

- [x] Task 10: Frontend hook for handling gap questions via SSE
  - [x] Extend `frontend/lib/sse/useStream.ts` to handle validation-specific SSE events.

## Dev Notes

### What This Story Builds
Story 3.4 implements the **Spec Review Mode** — the second of three Spec pipelines. When a user pastes a spec, the system:
1. **Detects intent** — keyword-based.
2. **Launches BMad validate subprocess** — streaming output to chat.
3. **Conducts gap analysis** — asking the user clarifying questions.
4. **Captures and stores the validated spec**.

### Architecture Constraints (MUST FOLLOW)
**AD-7 — Streaming over polling:** BMad pipelines stream their stdout via SSE.
**AD-9 — Async throughout:** All backend routes are `async def`. Subprocess invocation is non-blocking.
**AD-11 — BMad pipelines via subprocess, output bridged to SSE:** Validation is invoked as Python subprocesses.

### Integration with Later Stories
- **Story 3.5 (Direct Implementation Mode):** User provides spec + requests implementation without review.
- **Story 4.1 (Ticket Generation):** After validation completes, user can request ticket generation.

## Dev Agent Record

### Agent Model Used
Gemini 3.1 Pro (High)

### Debug Log References
N/A

### Completion Notes List
- [x] All AC passing
- [x] Spec review intent detection verified
- [x] Validation subprocess output streaming verified
- [x] Gap analysis UI flow verified
- [x] Spec storage integration verified
- [x] No regressions

### File List
```
backend/chat/intent_detector.py — updated
backend/chat/subprocess_runner.py — updated
backend/api/routes/chat.py — created
backend/main.py — updated
frontend/app/projects/[id]/ChatInterface.tsx — updated
frontend/lib/sse/useStream.ts — updated
tests/test_spec_review_mode.py — created
```
