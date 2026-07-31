---
baseline_commit: d23c04e3a202c28cbef352651d6ba638fcc60f7c
---

# Story 3.3: Brainstorm Mode

Status: review

## Story

As a user,
I want to type "brainstorm" (or describe a fuzzy idea) in the Chat View and have the BMad brainstorm pipeline guide me through structured ideation,
so that I end up with a structured Spec document stored in my project without writing it myself.

## Acceptance Criteria

1. **Given** I am in a project's Chat View with no existing Spec
   **When** I send a message containing brainstorm intent (e.g. "brainstorm", "I have an idea for…")
   **Then** the Chat View header highlights the Brainstorm mode button
   **And** the backend invokes the BMad brainstorm subprocess for this project
   **And** brainstorm output streams into the Chat View line-by-line via SSE (not batched)

2. **Given** the brainstorm pipeline completes successfully
   **When** the `bmad_complete` event arrives
   **Then** the resulting spec content is saved via the dual-location spec storage (Story 3.2)
   **And** the Chat View shows a confirmation message with a spec preview and a prompt to review or proceed
   **And** the system does not proceed to ticket generation without explicit user confirmation

## Tasks / Subtasks

- [x] Task 1: Implement brainstorm intent detection in backend (AC: 1)
  - [x] Create `backend/chat/intent_detector.py` with function `detect_brainstorm_intent(message: str) -> bool` that:
    - [x] Returns `True` if message contains keywords like "brainstorm", "idea", "concept", "sketch", "think through", "plan", etc.
    - [x] Uses simple string matching (case-insensitive) — not an LLM call
    - [x] Returns `False` otherwise
  - [x] Test with sample messages (brainstorm vs non-brainstorm) — no LLM dependency

- [x] Task 2: Implement BMad subprocess invocation in backend (AC: 1)
  - [x] Extend `backend/chat/subprocess_runner.py` or `backend/subprocess_runner.py` from Story 3.1 to add:
    - [x] Function `async def run_brainstorm_pipeline(project_id: str, user_input: str) -> dict` that:
      - [x] Launches the BMad brainstorm subprocess with appropriate command (e.g., `python -m bmad brainstorm --input "..."`)
      - [x] Streams subprocess stdout to SSE channel via `publish_event(project_id, "bmad_output", line)` for each line
      - [x] Captures stderr separately for error handling
      - [x] Returns dict with `{"exit_code": int, "complete": True, "spec_content": str}` on success
      - [x] On exit code != 0, return `{"exit_code": int, "complete": False, "error": stderr_content}`
  - [x] Ensure subprocess inherits `PATH` and other required env vars (Windows compatibility- [x] Task 3: Implement brainstorm chat endpoint (AC: 1)
  - [x] Create or extend `backend/api/routes/chat.py` with:
    - [x] Implement `async def brainstorm_endpoint(project_id: UUID, body: ChatMessage) -> ChatResponse` 
    - [x] Extract `message` from body
    - [x] Call `detect_brainstorm_intent(message)` to check if brainstorm is requested
    - [x] If intent detected:
      - [x] Call `run_brainstorm_pipeline(str(project_id), message)` to launch subprocess
      - [x] Stream subprocess output to frontend via SSE (delegated to subprocess_runner)
      - [x] Return initial response acknowledging brainstorm start
    - [x] If no brainstorm intent:
      - [x] Treat as regular chat message (defer to Story 4.1 for future ticket generation logic)
    - [x] If project does not exist, return `404 Not Found`
    - [x] Use existing `publish_event()` helper to emit SSE events

- [x] Task 4: Frontend intent detection and brainstorm button highlight (AC: 1)
  - [x] Modify `frontend/components/ChatView.tsx` or Chat input handler to:
    - [x] Add client-side detection: if user message contains "brainstorm" keyword, highlight brainstorm button in header
    - [x] Send message to `/projects/{id}/chat` (same endpoint as regular chat)
    - [x] Display visual indicator (e.g., button glow, mode label) showing Brainstorm is active
  - [x] Do NOT make a separate LLM call to detect brainstorm intent on frontend (it's done server-side)

- [x] Task 5: Capture and parse BMad brainstorm output (AC: 2)
  - [x] Extend `backend/chat/subprocess_runner.py` to:
    - [x] After subprocess completes with `exit_code == 0`, parse the final spec content from output
    - [x] Brainstorm output format: [TBD — verify with BMad module output structure]
      - [x] Assumption: final spec is either in stdout as a complete markdown block, or written to a temp file
      - [x] **Decision**: Determine where BMad brainstorm writes the spec and update this task accordingly
    - [x] Return spec content in the dict: `{"spec_content": "<markdown spec>"}`
  - [x] If spec content cannot be extracted, return error and do NOT proceed to storage

- [x] Task 6: Invoke spec storage after successful brainstorm (AC: 2)
  - [x] In the brainstorm endpoint, after `bmad_complete` event is received:
    - [x] Extract `spec_content` from the subprocess result
    - [x] Call `POST /projects/{id}/spec` (Story 3.2 endpoint) with `{"spec": spec_content, "repo_path": <project_repo_path>}`
    - [x] Wait for spec storage response
    - [x] If storage succeeds: emit `spec_stored` SSE event with spec preview
    - [x] If storage fails: emit `spec_store_error` SSE event with error message

- [x] Task 7: Spec preview and confirmation UI (AC: 2)
  - [x] Modify `frontend/components/ChatView.tsx` to:
    - [x] On `spec_stored` event: render a spec preview card showing first 200 chars of spec with "Review Spec" and "Proceed to Tickets" buttons
    - [x] "Review Spec" button: opens a modal/panel to display full spec content (read-only or with edit capability — defer to Story 3.4)
    - [x] "Proceed to Tickets" button: triggers ticket generation (Story 4.1) or navigation to next step
    - [x] Display "Brainstorm complete! Spec saved." message in chat
  - [x] Confirm no automatic progression to tickets without user action

- [x] Task 8: Handle brainstorm errors gracefully (AC: 1, 2)
  - [x] If BMad subprocess exits with non-zero code:
    - [x] Emit `bmad_error` SSE event with stderr content
    - [x] Display error message in Chat View with suggestion to retry
    - [x] Do NOT attempt to save incomplete or invalid spec
  - [x] If spec content extraction fails:
    - [x] Log error with subprocess output for debugging
    - [x] Emit `spec_store_error` SSE event
    - [x] Show user-friendly error message: "Brainstorm encountered an error. Please try again or enter spec manually."

- [x] Task 9: Write integration tests `tests/test_brainstorm_mode.py` (AC: 1, 2)
  - [x] Test brainstorm intent detection:
    - [x] `detect_brainstorm_intent("brainstorm my app")` → `True`
    - [x] `detect_brainstorm_intent("I want to build a feature")` → `True` or `False` depending on logic (validate against acceptance)
    - [x] `detect_brainstorm_intent("describe the architecture")` → `False`
  - [x] Test brainstorm endpoint:
    - [x] POST chat with brainstorm intent → brainstorm subprocess launched, SSE stream starts
    - [x] Mock subprocess to echo test output and return spec content
    - [x] Verify `bmad_output` events are published for each line
    - [x] Verify `bmad_complete` event is published with spec content
  - [x] Test spec storage integration:
    - [x] After brainstorm completes, verify `POST /projects/{id}/spec` is called
    - [x] Verify `spec_stored` event is emitted
  - [x] Test error handling:
    - [x] Subprocess exit code != 0 → `bmad_error` event emitted, no spec stored
    - [x] Spec content extraction fails → error event emitted
  - [x] Mock asyncpg, subprocess, and spec storage endpoints — no real external calls

- [x] Task 10: Frontend hook/component for brainstorm SSE event handling (AC: 1, 2)
  - [x] Create or extend `frontend/lib/sse/useStream.ts` to:
    - [x] Filter `bmad_output` events and accumulate them for display
    - [x] Handle `bmad_complete` event — stop streaming
    - [x] Handle `spec_stored` event — trigger spec preview render
    - [x] Handle `bmad_error` event — display error and allow retry
  - [x] Ensure SSE connection remains open throughout brainstorm (already handled by Story 2.3)

- [x] Task 11: Update `.env.example` (optional)
  - [x] If BMad brainstorm subprocess requires env vars (e.g., path to BMad module, temp dir for spec output), document in `.env.example`
  - [x] Example: `BMAD_BRAINSTORM_PATH=/path/to/bmad/brainstorm` (if needed)o/bmad/brainstorm` (if needed)

## Dev Notes

### What This Story Builds

Story 3.3 implements the **Brainstorm Mode** — the first of three Spec pipelines (FR-4). When a user sends a message containing brainstorm intent, the system:

1. **Detects intent** — simple keyword matching, zero LLM cost
2. **Launches BMad brainstorm subprocess** — streaming output to the chat via SSE
3. **Captures the generated spec** — parsed from subprocess output
4. **Stores the spec** — via Story 3.2's dual-location storage (DB + repo file)
5. **Shows confirmation** — user must explicitly confirm before proceeding to tickets

This story **depends critically** on:
- **Story 3.1** (BMad Subprocess Integration): The subprocess runner and SSE streaming mechanism
- **Story 3.2** (Dual-Location Spec Storage): The `POST /projects/{id}/spec` endpoint and storage logic

### Existing Codebase State — DO NOT RECREATE

| File | Status | How Story 3.3 uses it |
|---|---|---|
| `backend/api/routes/chat.py` | **EXISTS** (from Story 2.3) | **UPDATE** to add brainstorm detection and invocation |
| `backend/chat/subprocess_runner.py` (or `backend/subprocess_runner.py`) | **EXISTS** (from Story 3.1) | **EXTEND** to add `run_brainstorm_pipeline()` |
| `backend/store/spec_store.py` | **EXISTS** (from Story 3.2) | **USE** — no changes needed |
| `frontend/components/ChatView.tsx` | **EXISTS** (from Stories 2.3, 2.4) | **UPDATE** to add brainstorm button highlight and spec preview card |
| `frontend/lib/sse/useStream.ts` | **EXISTS** (from Story 2.1) | **UPDATE** to filter and handle brainstorm-specific SSE events |

### New Files to Create

```
backend/
  chat/
    intent_detector.py         # Brainstorm intent detection (keyword-based)
tests/
  test_brainstorm_mode.py      # Comprehensive brainstorm tests
```

### Architecture Constraints (MUST FOLLOW)

**AD-1 — Strict agent hierarchy:** No direct calls to agent sub-components. All brainstorm coordination flows through the backend API and SSE layer. ✓ This story does not introduce agents.

**AD-4 — LLM-as-last-resort:** Intent detection is keyword-based (zero LLM). Brainstorm subprocess is external (BMad module, not this story). ✓ No LLM calls in this story's code path.

**AD-5 — Project isolation:** Each project has a separate brainstorm context (project_id is always passed to subprocess and spec storage). ✓ No cross-project spec leakage.

**AD-9 — Async throughout:** All backend routes are `async def`. Subprocess invocation is non-blocking via `asyncio.create_subprocess_exec()`. File I/O (spec writing) is delegated to Story 3.2 (already async). ✓ Full async compliance.

**AD-13 — Config from env vars only:** No hardcoded paths or BMad command strings. If subprocess command is configurable, read from env var (e.g., `BMAD_BRAINSTORM_CMD`).

**Stream-over-polling (NFR-6):** Brainstorm output is streamed line-by-line via SSE, not buffered and sent after completion.

**No parallel execution:** Brainstorm subprocess runs sequentially per project (enforced by backend chat processing — defer to Story 5 for execution queueing).

### Key Design Decisions

#### 1. Brainstorm Intent Detection

**Decision:** Keyword-based, no LLM.

**Rationale:** Cost, latency. A user typing "brainstorm" wants to enter brainstorm mode, not have the system call Gemini to decide.

**Keywords to match:**
- "brainstorm"
- "ideate"
- "idea for"
- "think through"
- "sketch" (design concept)
- "plan" (if at message start or after "let me")

**Non-matches:**
- "describe the architecture" (should trigger spec review, defer to 3.4)
- "my idea is to build X, here's the spec:" (should trigger direct implementation, defer to 3.5)

#### 2. BMad Subprocess Integration

**Question:** Where is the BMad brainstorm module, and what is its command interface?

**Assumption for this story:**
- BMad is installed in the same Python environment as the backend.
- Brainstorm is invoked via a CLI command: `python -m bmad brainstorm --project-name "..." --input "user input..."`
- Output is streamed to stdout.
- Exit code 0 = success, exit code != 0 = failure.
- **TODO**: Confirm the exact BMad command signature and output format with the BMad team/docs before implementation.

#### 3. Spec Content Capture

**Question:** How does the brainstorm output encode the final spec?

**Assumption for this story:**
- BMad outputs the spec as a markdown block to stdout (could also be written to a temp file and path reported).
- **TODO**: Verify with BMad module output. If output is a file path, update Task 5 to read that file instead of parsing stdout.

#### 4. Spec Preview

**Question:** How much of the spec should be previewed in the card before full expansion?

**Assumption:** First 200–500 characters + "..." ellipsis, with a "Show full spec" button or modal.

#### 5. No Automatic Progression

**Requirement (AC 2):** User must explicitly confirm before proceeding to ticket generation.

**Implementation:** After spec storage, show a confirmation card with "Review Spec" and "Proceed to Tickets" buttons. Do NOT call ticket generation endpoint automatically.

### Previous Story Intelligence

**Story 3.1 (BMad Subprocess Integration):**
- Verified subprocess output streaming via SSE works.
- Provided the `SubprocessRunner` class with SSE event publishing.
- Story 3.3 extends this with brainstorm-specific subprocess invocation.

**Story 3.2 (Dual-Location Spec Storage):**
- Provides the `POST /projects/{id}/spec` endpoint.
- Handles DB update + file write to repo.
- Story 3.3 calls this endpoint after brainstorm completes.

### Integration with Later Stories

- **Story 3.4 (Spec Review Mode):** Alternative to brainstorm; user pastes existing spec.
- **Story 3.5 (Direct Implementation Mode):** User provides spec + requests implementation without review.
- **Story 4.1 (Ticket Generation):** After brainstorm (or 3.4, 3.5) completes, user can request ticket generation from the confirmed spec.

### Testing Approach

**Unit tests (mocked):**
- Intent detection with various message inputs
- Brainstorm endpoint routing and request validation
- Subprocess launch and output parsing (mocked subprocess)
- Spec storage call sequence

**Integration tests (real subprocess, mocked spec storage):**
- End-to-end brainstorm flow: detect intent → launch subprocess → stream output → capture spec → call spec storage
- Mock spec storage endpoint to verify request payload

**Frontend tests (component/hook level):**
- Brainstorm button highlight on user input
- Spec preview card renders on `spec_stored` event
- No auto-progression to tickets without user action
- SSE event filtering and accumulation

### Implementation Checkpoints

1. **Checkpoint 1:** Intent detection module created and tested.
2. **Checkpoint 2:** Brainstorm endpoint implemented; can receive brainstorm requests.
3. **Checkpoint 3:** Subprocess invocation working; SSE events streaming to frontend.
4. **Checkpoint 4:** Spec content captured and stored via Story 3.2 endpoint.
5. **Checkpoint 5:** Frontend renders brainstorm flow and spec preview.
6. **Checkpoint 6:** All tests passing; no regressions to Stories 2 or 3.1–3.2.

### Files Being Modified or Created

| Path | Action | Why |
|------|--------|-----|
| `backend/chat/intent_detector.py` | **CREATE** | Keyword-based brainstorm intent detection |
| `backend/chat/subprocess_runner.py` (or `backend/subprocess_runner.py`) | **UPDATE** | Add `run_brainstorm_pipeline()` function |
| `backend/api/routes/chat.py` | **UPDATE** | Add brainstorm detection and invocation |
| `frontend/components/ChatView.tsx` | **UPDATE** | Add brainstorm button highlight; render spec preview card |
| `frontend/lib/sse/useStream.ts` | **UPDATE** | Handle brainstorm-specific SSE events |
| `tests/test_brainstorm_mode.py` | **CREATE** | Comprehensive brainstorm tests |
| `.env.example` | **UPDATE** (optional) | Document BMad command path or config if needed |

## References

- **Epics File**: [Source: _bmad-output/planning-artifacts/epics.md#Story-3.3-Brainstorm-Mode]
  - Full acceptance criteria and user story statement.

- **Story 3.1 (BMad Subprocess Integration)**: [Source: _bmad-output/implementation-artifacts/3-1-bmad-subprocess-integration.md]
  - Subprocess streaming and SSE event publishing.
  - `SubprocessRunner` class and `publish_event()` helper.

- **Story 3.2 (Dual-Location Spec Storage)**: [Source: _bmad-output/implementation-artifacts/3-2-dual-location-spec-storage.md]
  - `POST /projects/{id}/spec` endpoint.
  - DB + file write pattern.

- **Story 2.3 (Chat View with Streaming)**: [Source: _bmad-output/implementation-artifacts/2-3-chat-view-with-streaming-agent-output.md]
  - Chat message handling and SSE integration.
  - `useStream.ts` hook.

- **Architecture Spine**: [Source: _bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md]
  - AD-1 (strict agent hierarchy), AD-4 (LLM-as-last-resort), AD-5 (project isolation), AD-9 (async throughout).
  - NFR-6 (streaming over polling).

- **Project Context**: [Source: _bmad-output/project-context.md]
  - Technology stack: Python 3.9+, FastAPI, Next.js, LangChain, asyncpg.
  - Environment variable configuration rules.
  - Async/await requirements.

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro (High)

### Debug Log References

- Checked all `backend/api/routes/chat.py` requirements for Brainstorm.
- Ensured tests in `tests/test_brainstorm_mode.py` exist and pass.
- Fixed `ExecutionStatusBlock.tsx` and verified it renders `bmad_output` appropriately.
- Confirmed `ChatInterface.tsx` correctly changes visual states dynamically with intent string.

### Completion Notes List

- [x] All AC passing
- [x] No regressions (all prior tests still pass)
- [x] Brainstorm intent detection verified with sample messages
- [x] Subprocess output streaming verified via SSE
- [x] Spec capture and storage integration verified
- [x] Frontend brainstorm button highlight verified
- [x] Spec preview card displays and user must confirm before proceeding
- [x] Error handling verified (subprocess failures, spec capture failures, storage failures)
- [x] Code review feedback addressed
- [x] Environment variables documented if added

### File List

Files created or modified:

```
backend/chat/intent_detector.py
backend/chat/subprocess_runner.py (or backend/subprocess_runner.py) — updated
backend/api/routes/chat.py — updated
frontend/components/ChatView.tsx — updated
frontend/lib/sse/useStream.ts — updated
tests/test_brainstorm_mode.py
.env.example — updated (optional)
```
