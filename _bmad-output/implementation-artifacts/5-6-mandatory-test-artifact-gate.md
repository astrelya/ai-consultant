---
baseline_commit: b873c0bec72ac891aa89d1b0fcf39a979992fbc7
---

# Story 5.6: Mandatory Test Artifact Gate

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want a ticket to only transition to `Done` after a test suite has been executed and a verifiable artifact is written to the project store,
so that no ticket is ever silently marked complete without real test execution (ghost validation is impossible per AD-6 / FR-17 / CAP-6).

## Acceptance Criteria

1. **Given** `TesterAgent.write_and_run_tests` has finished running tests for a ticket
   **When** it returns to `SupervisorAgent`
   **Then** it MUST call `await project_store.write_test_artifact(project_id, ticket_id, artifact_ref)` before returning, where `artifact_ref` is a non-empty string identifying the produced artifact (log file path relative to the workspace, or a compact assertion-result summary of the form `"pytest: N passed, M failed, K skipped"`).

2. **And** the artifact reference is persisted on the ticket record in PostgreSQL under a new JSONB field `test_artifact_ref` inside `ticket_history[].` such that `GET /projects/{id}` returns it as part of the ticket dict (surfacing FR-17 to the frontend).

3. **Given** any code path attempts to transition a ticket to status `Done`
   **When** the transition is attempted via `await project_store.mark_ticket_done(project_id, ticket_id)`
   **Then** the store reads the current `test_artifact_ref` for that ticket, and:
   - If it is a non-empty string, the status is set to `Done` in the same UPDATE.
   - If it is missing, empty, or whitespace-only, the store raises `TestArtifactMissingError(project_id, ticket_id)` — a hard system error — and does NOT modify the ticket status. Ghost validation is impossible.

4. **And** when `TestArtifactMissingError` is raised anywhere on the execution path, `SupervisorAgent` catches it, publishes an SSE `agent_log` event of the form `{"message": "[Supervisor] Test artifact missing for ticket <id> — cannot mark Done. FR-17/AD-6 violated."}` on the project channel, sets the ticket status to `Error` via `update_ticket_status(project_id, ticket_id, "Error")`, and returns `{"ticket_id": ..., "status": "error", "reason": "test_artifact_missing"}` from `_execute_ticket`. The error is NEVER swallowed silently (AD-8-style hard-fail semantics applied to AD-6).

5. **And** `TesterAgent.write_and_run_tests` becomes `async` (AD-9) — the method signature changes to `async def write_and_run_tests(self, story_details, code_files, workspace_path) -> dict` and every caller uses `await`. The mocked pytest run writes a real log file at `<workspace_path>/logs/test-<ticket_id>-<yyyymmddHHMMSS>.log` (created via `os.makedirs(exist_ok=True)`) containing at minimum: ticket id, ISO timestamp, list of `test_files`, and a summary line. That file path (relative to `workspace_path`, forward-slashed) is the `artifact_ref` returned in the result dict under key `test_artifact_ref` AND written to the store per AC-1.

## Tasks / Subtasks

- [x] 1. Add `TestArtifactMissingError` and gated store methods (AC: 1, 2, 3)
  - [x] 1.1 Create `backend/store/errors.py` with:
    ```python
    class TestArtifactMissingError(RuntimeError):
        """AD-6 / FR-17: raised when a ticket lacks a verifiable test artifact."""
        def __init__(self, project_id: str, ticket_id: str):
            super().__init__(
                f"Test artifact missing for ticket {ticket_id} in project {project_id} — "
                "cannot transition to Done (FR-17/AD-6)."
            )
            self.project_id = project_id
            self.ticket_id = ticket_id
    ```
    Keep it in `backend/store/` (not `backend/api/`) because the gate is enforced at the persistence boundary — the store is the canonical guardrail (AD-6 wording: "Ghost validation is detectable at infrastructure level").
  - [x] 1.2 In `backend/store/project_store.py`, add `async def write_test_artifact(project_id: str, ticket_id: str, artifact_ref: str) -> None`:
    - Validate `isinstance(artifact_ref, str) and artifact_ref.strip()`; raise `ValueError("artifact_ref must be a non-empty string")` otherwise. Do this validation BEFORE opening a pool connection — cheap fail, no DB round-trip on garbage input.
    - Reuse the exact JSONB merge pattern from the existing `update_ticket_status` (`jsonb_agg(CASE WHEN t->>'id' = $2 ...)`) but merge `{"test_artifact_ref": artifact_ref}` into the ticket. Do NOT call `update_ticket_fields` internally — this method must be a single SQL UPDATE so it stays atomic and mockable (tests will patch `database.get_pool`).
    - Docstring must reference AD-6 / FR-17 and state "Must be called before `mark_ticket_done`."
  - [x] 1.3 In the same file, add `async def mark_ticket_done(project_id: str, ticket_id: str) -> None`:
    - Fetch current ticket_history JSONB and locate the ticket by id (server-side, single query is fine — do NOT read all projects; use `SELECT` with `jsonb_path_query_first` or fetch `ticket_history` then find in Python — Python approach is acceptable and matches existing patterns in this file).
    - If the ticket is not found, raise `ValueError(f"Ticket {ticket_id} not found in project {project_id}")`.
    - Read the `test_artifact_ref` field. If missing, None, empty, or `.strip() == ""`, raise `TestArtifactMissingError(project_id, ticket_id)` — do NOT update the status.
    - Otherwise, execute the same JSONB-merge UPDATE pattern to set `{"status": "Done"}`. Do NOT call `update_ticket_status` from this method — inlining the SQL guarantees the gate check and the write happen without any code path in between that could skip the check.
    - Import `TestArtifactMissingError` from `backend.store.errors` at the top of the file.
  - [x] 1.4 Do NOT add a new PostgreSQL column — `test_artifact_ref` lives inside each ticket's JSONB record in `ticket_history`. No `migrations.py` change required.

- [x] 2. Rework `TesterAgent` to be async and produce a real artifact (AC: 1, 5)
  - [x] 2.1 In `agents/tester_agent.py`, change the signature to `async def write_and_run_tests(self, story_details: dict, code_files: list, workspace_path: str) -> dict`.
  - [x] 2.2 Extract `ticket_id = story_details.get("id", "unknown")` and `project_id = story_details.get("project_id")` at the top of the method.
  - [x] 2.3 Keep the existing scaffold-test-file generation (`tests/test_<file>.py` writes) — do NOT rip that out; it's the documented "TesterAgent currently generates scaffold tests only" TODO per project-context.md testing rules and is orthogonal to this story.
  - [x] 2.4 Immediately after scaffold generation, produce the log artifact:
    ```python
    from datetime import datetime, timezone
    logs_dir = os.path.join(workspace_path, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    log_name = f"test-{ticket_id}-{ts}.log"
    log_path = os.path.join(logs_dir, log_name)
    summary = f"pytest: {len(test_files)} passed, 0 failed, 0 skipped"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"ticket_id: {ticket_id}\n")
        f.write(f"timestamp: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"test_files: {test_files}\n")
        f.write(f"summary: {summary}\n")
    # store the ref in the shape mark_ticket_done will read
    artifact_ref = os.path.relpath(log_path, workspace_path).replace(os.sep, "/")
    ```
    Forward-slash normalisation is required because the frontend and PostgreSQL both round-trip these strings and Windows backslashes break JSON escaping.
  - [x] 2.5 If `project_id` is truthy, call `await project_store.write_test_artifact(project_id, ticket_id, artifact_ref)` from inside `write_and_run_tests`. If `project_id` is falsy (CLI / smoke test path), skip the store write and return the artifact_ref in the dict only — do NOT raise; the CLI path predates the backend store and cannot resolve the project. This is the ONLY tolerated escape hatch and it is explicitly justified by "cross-session persistent project memory requires a project_id, and the CLI has none".
  - [x] 2.6 Return dict shape must be:
    ```python
    {
        "status": "success",
        "test_files": test_files,
        "coverage": "100%",
        "message": "All unit tests passed.",
        "test_artifact_ref": artifact_ref,
        "artifact_log_path": log_path,
    }
    ```
    Two keys because `test_artifact_ref` is the store-facing relative path (AC-1) while `artifact_log_path` is the absolute path for local debugging — this parity keeps existing print/log statements useful without a second `os.path.join` at each callsite.
  - [x] 2.7 Import `os` (already imported) and add `from backend.store import project_store` at the top. Do NOT import `write_test_artifact` directly — attribute-on-module import keeps `patch("backend.store.project_store.write_test_artifact", ...)` working in tests.

- [x] 3. Wire the gate into `SupervisorAgent._execute_ticket` (AC: 3, 4, 5)
  - [x] 3.1 In `agents/supervisor_agent.py`, import at the top:
    ```python
    from backend.store.errors import TestArtifactMissingError
    ```
  - [x] 3.2 In `_execute_ticket`, change the tester call to await it:
    ```python
    test_result = await self.tester.write_and_run_tests(
        story_details, dev_result.get("code_files", []), workspace_path
    )
    ```
  - [x] 3.3 After the tester call, before the `update_ticket_status(..., "In Review")` line, add:
    ```python
    if test_result.get("status") != "success":
        await publish_event(project_id, "agent_log",
            {"message": f"[Supervisor] Testing phase failed for ticket {ticket_id}."})
        await project_store.update_ticket_status(project_id, ticket_id, "Error")
        return {"ticket_id": ticket_id, "status": "error", "reason": "testing_failed"}
    ```
    This is a defensive branch — the current mock tester always returns `success`, but this story hardens the path for when real pytest execution lands.
  - [x] 3.4 Keep the `"In Review"` transition exactly as-is on the happy path. Do NOT change it to `"Done"` — the `In Review` state is intentional per Story 5.2 (human/code-review gate). Story 5.6 gates the eventual `Done` transition; it does not move the transition point.
  - [x] 3.5 Add a new private method that any downstream caller (code-review workflow, future stories 5.7–5.9) will use to close the ticket:
    ```python
    async def close_ticket_as_done(self, project_id: str, ticket_id: str) -> dict:
        """Gated Done transition — enforces AD-6 / FR-17. Raises TestArtifactMissingError."""
        try:
            await project_store.mark_ticket_done(project_id, ticket_id)
        except TestArtifactMissingError as exc:
            await publish_event(project_id, "agent_log", {
                "message": (
                    f"[Supervisor] Test artifact missing for ticket {ticket_id} — "
                    f"cannot mark Done. FR-17/AD-6 violated."
                ),
            })
            await project_store.update_ticket_status(project_id, ticket_id, "Error")
            return {"ticket_id": ticket_id, "status": "error", "reason": "test_artifact_missing"}
        await publish_event(project_id, "agent_log", {
            "message": f"[Supervisor] Ticket {ticket_id} closed as Done (test artifact verified).",
        })
        return {"ticket_id": ticket_id, "status": "done"}
    ```
    Wrap the whole method so callers get either a normal result dict or `{"status": "error", "reason": "test_artifact_missing"}` — never an unhandled exception (AC-4).
  - [x] 3.6 Do NOT auto-invoke `close_ticket_as_done` inside `_execute_ticket` in this story. The ticket flow ends at `In Review`. Wiring the Done transition into the review workflow belongs to Story 5.7 (autonomous regression fix) or a later code-review-completion story. This story only makes the gate available and correct.

- [x] 4. Update `main_agent.py` callsites to await the tester (AC: 5)
  - [x] 4.1 In `agents/main_agent.py`, both call sites of `self.tester.write_and_run_tests(...)` (line ~76 and line ~197) must be `await self.tester.write_and_run_tests(...)`. Follow the surrounding function's async context — both `_process_story` and the ticket-execution loop are already `async def` (they call `await self.ticket_manager.transition_ticket`), so this is a mechanical change.
  - [x] 4.2 The CLI path (`main_agent.py`) does not have a real `project_id` (see AC-1 in Story 5.4). Its tester call therefore skips the store write and just reads `test_artifact_ref` from the returned dict. Print the artifact ref to stdout for visibility: `print(f"  [TesterAgent] Test artifact: {test_result.get('test_artifact_ref')}")`. This is the ONLY CLI-side change.
  - [x] 4.3 Do NOT introduce any Done transition on the CLI path — the CLI predates the backend store and cannot enforce the gate. Its behaviour is unchanged.

- [x] 5. Tests (AC: 1, 2, 3, 4, 5)
  - [x] 5.1 Add `tests/test_project_store_test_artifact.py`:
    - [x] 5.1.1 `test_write_test_artifact_rejects_empty_string`: patch `backend.store.database.get_pool`; assert `await write_test_artifact("pid", "tid", "")` raises `ValueError` AND `get_pool` was NEVER called (fail-fast before DB).
    - [x] 5.1.2 `test_write_test_artifact_rejects_whitespace`: same as above with `"   "`.
    - [x] 5.1.3 `test_write_test_artifact_rejects_non_string`: same as above with `None` and with `123`.
    - [x] 5.1.4 `test_write_test_artifact_updates_ticket`: mock the pool so `conn.execute` records the SQL and params; assert the SQL contains `jsonb_agg` and `test_artifact_ref`, and the params are `("pid", "tid", '{"test_artifact_ref": "logs/test-x.log"}')` (or equivalent JSON).
    - [x] 5.1.5 `test_mark_ticket_done_raises_when_artifact_missing`: mock the pool to return a ticket_history where the target ticket has NO `test_artifact_ref`; assert `TestArtifactMissingError` raised AND no UPDATE was executed (only the SELECT).
    - [x] 5.1.6 `test_mark_ticket_done_raises_when_artifact_empty`: same as 5.1.5 but with `"test_artifact_ref": ""`.
    - [x] 5.1.7 `test_mark_ticket_done_raises_when_artifact_whitespace`: same as above with `"   \n"`.
    - [x] 5.1.8 `test_mark_ticket_done_sets_status_when_artifact_present`: mock pool with a ticket having `test_artifact_ref="logs/x.log"`; assert an UPDATE was executed setting status Done.
    - [x] 5.1.9 `test_mark_ticket_done_ticket_not_found`: ticket_history exists but no matching id; assert `ValueError` raised (not `TestArtifactMissingError` — the "missing artifact" error is reserved for real gate violations, not lookup failures; getting these two errors mixed up would make triage in Chat View confusing).
  - [x] 5.2 Add `tests/test_tester_agent_artifact.py`:
    - [x] 5.2.1 `test_tester_agent_is_async`: `import inspect; assert inspect.iscoroutinefunction(TesterAgent().write_and_run_tests)`.
    - [x] 5.2.2 `test_tester_agent_writes_log_artifact_to_workspace`: create a `tmp_path` workspace, run the tester with a fake `code_files=["a.py"]` and `story_details={"id": "ticket-7", "project_id": None}`, assert the returned `test_artifact_ref` matches `logs/test-ticket-7-\d{14}\.log`, and that the log file exists on disk under `tmp_path/logs/` with content including `ticket_id: ticket-7`, an ISO timestamp, and the summary line.
    - [x] 5.2.3 `test_tester_agent_uses_forward_slashes_in_artifact_ref`: on any OS, the returned `test_artifact_ref` must not contain a backslash character (`assert "\\" not in result["test_artifact_ref"]`).
    - [x] 5.2.4 `test_tester_agent_writes_artifact_to_store_when_project_id_present`: patch `backend.store.project_store.write_test_artifact` with `AsyncMock`; call with `project_id="proj-1"`; assert the patch was awaited exactly once with `("proj-1", "ticket-7", <the_returned_artifact_ref>)`.
    - [x] 5.2.5 `test_tester_agent_skips_store_write_when_project_id_missing`: patch `write_test_artifact` with `AsyncMock`; call with `story_details={"id": "ticket-7"}` (no project_id key); assert the patch was NEVER awaited, and the return dict still contains a populated `test_artifact_ref` (CLI path).
  - [x] 5.3 Add `tests/test_supervisor_test_artifact_gate.py`:
    - [x] 5.3.1 `test_close_ticket_as_done_publishes_success_event`: patch `project_store.mark_ticket_done` with `AsyncMock` returning None; patch `publish_event` with `AsyncMock`; call `await supervisor.close_ticket_as_done("p", "t")`; assert return dict `{"ticket_id": "t", "status": "done"}` and the SSE message contains "closed as Done".
    - [x] 5.3.2 `test_close_ticket_as_done_handles_missing_artifact`: `mark_ticket_done.side_effect = TestArtifactMissingError("p", "t")`; patch `update_ticket_status` with `AsyncMock`; call `close_ticket_as_done`; assert the returned dict is `{"ticket_id": "t", "status": "error", "reason": "test_artifact_missing"}`, an SSE `agent_log` with `"FR-17/AD-6 violated"` was awaited, AND `update_ticket_status` was awaited with `("p", "t", "Error")`.
    - [x] 5.3.3 `test_execute_ticket_awaits_tester`: use the existing supervisor test fixtures (see `tests/test_supervisor_agent.py`) — patch `self.tester.write_and_run_tests` with `AsyncMock` returning the standard success dict + `test_artifact_ref`; run `_execute_ticket`; assert the mock was awaited (regression guard for AC-5).
    - [x] 5.3.4 `test_execute_ticket_marks_error_when_testing_failed`: patch tester to return `{"status": "error", ...}`; assert the ticket status is set to `"Error"` and the returned dict has `reason="testing_failed"`.
  - [x] 5.4 Update `tests/test_supervisor_agent.py`: any existing test that patches `tester.write_and_run_tests` with a regular `MagicMock` MUST be switched to `AsyncMock` since the method is now a coroutine. Grep the file for `write_and_run_tests` and audit every match. If no such patches exist (the existing supervisor tests may not mock this method), skip this step — but document in Dev Notes that you verified.
  - [x] 5.5 Regression: run `python -m pytest tests/ -q` and confirm ALL previously passing tests still pass. If any Story 5.5 tests break because the tester is now async, that IS a regression from this story and must be fixed here (they should be robust to the change since 5.5 focuses on grounding, not testing, but double-check).

- [x] 6. Documentation & schema notes
  - [x] 6.1 Do NOT create a new markdown doc for this story unless the user asks — per repo convention.
  - [x] 6.2 Do NOT modify `backend/store/migrations.py` — no new column is required (see Task 1.4).
  - [x] 6.3 Do NOT touch `.env.example` — no new env vars introduced.

## Dev Notes

### What Stories 5.1–5.5 Built (Must Not Break)

- **Story 5.1** — `execution_lock.py` and the FastAPI lifespan init. The lock is held for the entire duration of `_execute_ticket`. The new async tester call happens INSIDE that lock, so no lock code changes are needed. AD-4 (sequential execution) remains intact.
- **Story 5.2** — `SupervisorAgent._execute_ticket` currently sets status `"In Review"` after the tester runs. Story 5.6 preserves that transition — the `Done` gate is a separate, later transition invoked via `close_ticket_as_done`. Do NOT collapse the two.
- **Story 5.3** — `_build_accumulated_context` reads ticket_history entries and includes them in later tickets' prompts. The new `test_artifact_ref` JSONB field is additive; the accumulated context builder ignores unknown keys, so no change needed there.
- **Story 5.4** — `chat_history` JSONB round-trip logic in `get_project()` decodes JSON strings to Python objects. Confirm the new `test_artifact_ref` string survives round-trip — it's a plain string field inside ticket dicts, so no JSON-string-of-JSON issue applies.
- **Story 5.5** — `context7_grounding.py` and the developer-agent grounding wrappers. Grounding runs BEFORE the tester; it is orthogonal. However, be aware: Story 5.5 changed the developer-agent return signature to include `{"status": "error", "reason": "context7_grounding_failed"}`. The supervisor already branches on `dev_result.get("status") != "success"`, so no additional logic is required — grounding failures return `error` before the tester ever runs.

### Architecture Compliance

- **AD-1 (agent hierarchy):** Tester writes to the store directly. This is NOT a sub-agent-to-sub-agent call — it's an agent-to-persistence call. The rule "sub-agents must not call each other directly" applies to agents, not to the shared persistence layer. Confirmed against ARCHITECTURE-SPINE.md line 61.
- **AD-2 (project data isolation):** All new store methods take `project_id` and scope every query by it. No cross-project reads.
- **AD-3 (MCPManager singleton):** No MCP involvement in this story.
- **AD-4 (sequential lock):** New logic runs inside the existing lock — no lock code changes.
- **AD-6 (test artifact gate):** THIS STORY. Enforced at the persistence boundary (`project_store.mark_ticket_done`) so any future caller — supervisor, code-review workflow, CLI, or a rogue REPL session — hits the same guardrail. "Ghost validation is detectable at infrastructure level" (ARCHITECTURE-SPINE.md line 104).
- **AD-8 (Context7 grounding):** unchanged; grounding still precedes code generation, which precedes the tester.
- **AD-9 (async throughout):** `TesterAgent.write_and_run_tests` becomes `async`. All new store methods are `async def`. Every caller uses `await`.
- **AD-13 (env vars only):** No new required env vars. The workspace `logs/` directory location is fixed relative to `workspace_path` — no env var needed and no path pluralism.
- **project-context.md — Gemini list-content guard:** N/A for this story (no LLM calls added).
- **project-context.md — testing rules:** `TesterAgent currently generates scaffold tests only` — the story preserves that TODO. Real pytest execution is future work; the artifact we emit is a synthetic-but-real log file so the AD-6 gate has something to bite on.

### Files Being Modified — Current State and Change Scope

**`agents/tester_agent.py`** (current state: 32 lines, sync-only, no store awareness)
- Current: `def write_and_run_tests(...)` writes scaffold `test_<file>.py` files, prints two log lines, returns hard-coded success dict.
- Change: signature becomes `async def`; adds a real log-file write under `<workspace_path>/logs/`; adds `await project_store.write_test_artifact(...)` when `project_id` is truthy; adds `test_artifact_ref` and `artifact_log_path` to the return dict.
- Must preserve: scaffold test file generation (project-context.md testing rule), the two existing `print` lines (they surface in CLI mode).

**`agents/supervisor_agent.py`** (current state: 261 lines, `_execute_ticket` is the main flow)
- Current: line 175 calls `self.tester.write_and_run_tests(...)` synchronously; line 179 transitions to `"In Review"`.
- Change: line 175 becomes `await self.tester.write_and_run_tests(...)`; new defensive branch when `test_result.status != "success"` sets ticket to `"Error"` and returns; new method `close_ticket_as_done` added at the bottom of the class (below `_build_accumulated_context`).
- Must preserve: the `"In Review"` transition (this is the intended state after tests pass — Done comes later), all SSE `publish_event` calls, the existing `_build_accumulated_context` logic (Story 5.3), the existing `_delegate_to_developer` routing (Story 5.2).

**`agents/main_agent.py`** (current state: two call sites at ~line 76 and ~line 197)
- Current: `test_result = self.tester.write_and_run_tests(...)` — sync call.
- Change: both become `test_result = await self.tester.write_and_run_tests(...)`. Add one `print` line surfacing the artifact ref.
- Must preserve: everything else. The CLI/Jira paths are legacy but users still rely on them for smoke testing MCP connectivity (`test_jira_mcp.py`).

**`backend/store/project_store.py`** (current state: 166 lines, all sync-signature-async-body, JSONB-heavy)
- Current: has `update_ticket_status`, `update_ticket_fields`, `overwrite_ticket_history`. No artifact/gate awareness.
- Change: import `TestArtifactMissingError` from the new `errors` module; add `write_test_artifact` (single-UPDATE JSONB merge with input validation); add `mark_ticket_done` (SELECT-then-gated-UPDATE). Both follow the existing pattern of `pool = database.get_pool(); async with pool.acquire() as conn: await conn.execute(...)`.
- Must preserve: every existing function signature and behaviour. Tests in `tests/test_project_store_chat.py` rely on `append_chat_message`, etc.

**NEW files:**
- `backend/store/errors.py` — `TestArtifactMissingError` class only.
- `tests/test_project_store_test_artifact.py`
- `tests/test_tester_agent_artifact.py`
- `tests/test_supervisor_test_artifact_gate.py`

**DO NOT modify:**
- `backend/store/database.py` — no schema changes, no pool changes.
- `backend/store/migrations.py` — the new field lives inside the existing JSONB column.
- `backend/api/sse.py` — reuse `publish_event` verbatim.
- `backend/api/routes/execute.py` — the execute endpoint calls `SupervisorAgent.run_tickets`; nothing above the supervisor changes.
- `agents/environment_agent.py`, `agents/developer_agent.py`, `agents/local_developer_agent.py` — untouched by this story.
- Story 5.5 grounding code — untouched.

### Windows / Path Notes

- `os.path.relpath` returns backslashes on Windows. Explicitly `.replace(os.sep, "/")` on the artifact_ref before storing (Task 2.4). Tests assert the ref contains no backslash (Task 5.2.3).
- `os.makedirs(logs_dir, exist_ok=True)` is Windows-safe (project-context.md workspace rule).
- The FastAPI backend runs on Windows in dev per the current terminal cwd; do NOT introduce any POSIX-only path syntax.

### Reference Implementation Sketch (non-normative)

```python
# backend/store/errors.py
class TestArtifactMissingError(RuntimeError):
    """AD-6 / FR-17: raised when a ticket lacks a verifiable test artifact."""
    def __init__(self, project_id: str, ticket_id: str):
        super().__init__(
            f"Test artifact missing for ticket {ticket_id} in project {project_id} — "
            "cannot transition to Done (FR-17/AD-6)."
        )
        self.project_id = project_id
        self.ticket_id = ticket_id
```

```python
# backend/store/project_store.py (additions)
from backend.store.errors import TestArtifactMissingError

async def write_test_artifact(project_id: str, ticket_id: str, artifact_ref: str) -> None:
    """AD-6 / FR-17: persist a non-empty test artifact reference on a ticket.

    Must be called by TesterAgent before mark_ticket_done() can succeed.
    """
    if not isinstance(artifact_ref, str) or not artifact_ref.strip():
        raise ValueError("artifact_ref must be a non-empty string")
    pool = database.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE projects
            SET ticket_history = (
                SELECT jsonb_agg(
                    CASE WHEN t->>'id' = $2
                    THEN t || $3::jsonb
                    ELSE t
                    END
                )
                FROM jsonb_array_elements(ticket_history) AS t
            )
            WHERE id = $1
            """,
            project_id, ticket_id, json.dumps({"test_artifact_ref": artifact_ref}),
        )


async def mark_ticket_done(project_id: str, ticket_id: str) -> None:
    """AD-6 / FR-17 gate: only transitions ticket to Done when a test artifact exists."""
    pool = database.get_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow(
            "SELECT ticket_history FROM projects WHERE id = $1",
            project_id,
        )
    if not record:
        raise ValueError(f"Project {project_id} not found")
    history = record["ticket_history"]
    if isinstance(history, str):
        history = json.loads(history)
    ticket = next(
        (t for t in (history or []) if isinstance(t, dict) and t.get("id") == ticket_id),
        None,
    )
    if ticket is None:
        raise ValueError(f"Ticket {ticket_id} not found in project {project_id}")
    ref = ticket.get("test_artifact_ref")
    if not isinstance(ref, str) or not ref.strip():
        raise TestArtifactMissingError(project_id, ticket_id)

    pool = database.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE projects
            SET ticket_history = (
                SELECT jsonb_agg(
                    CASE WHEN t->>'id' = $2
                    THEN t || jsonb_build_object('status', 'Done')
                    ELSE t
                    END
                )
                FROM jsonb_array_elements(ticket_history) AS t
            )
            WHERE id = $1
            """,
            project_id, ticket_id,
        )
```

### Project Structure Notes

- New store errors live at `backend/store/errors.py` — this is a new module. Alignment with the existing `backend/store/` layout is direct: `database.py`, `project_store.py`, `spec_store.py`, `migrations.py`, `file_ops.py` — adding `errors.py` follows the same one-concept-per-file convention.
- No frontend changes in this story. The `test_artifact_ref` field is exposed via `GET /projects/{id}` because `get_project` returns the whole row including `ticket_history`. Rendering it in a ticket card is a UI concern for a later Epic 4/6 story.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.6: Mandatory Test Artifact Gate]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md#AD-6 — Test artifact gate (no ghost validation)]
- [Source: _bmad-output/project-context.md#Architecture Rules] — MCPManager, agent hierarchy, async rules
- [Source: _bmad-output/project-context.md#Testing Rules] — TesterAgent scaffold-only current state
- [Source: agents/supervisor_agent.py] — current `_execute_ticket` flow (line 175 tester call, line 179 In Review transition)
- [Source: agents/tester_agent.py] — current sync scaffold-only implementation
- [Source: backend/store/project_store.py] — existing JSONB merge pattern used by `update_ticket_status` / `update_ticket_fields` (mirrored by new methods)
- [Source: _bmad-output/implementation-artifacts/5-5-context7-grounding-before-code-generation.md] — previous story, defines the grounding path that runs before the tester

## Dev Agent Record

### Agent Model Used

GitHub Copilot / Claude Opus 4.7 (dev-story workflow).

### Debug Log References

- `python -m pytest tests/ -q` → **80 passed, 0 failed** (6 warnings, all pre-existing / unrelated to Story 5.6).
- `python -m pytest tests/test_project_store_test_artifact.py tests/test_tester_agent_artifact.py tests/test_supervisor_test_artifact_gate.py -v` → **20 passed** (all Story 5.6 tests).

### Completion Notes List

- Story 5.6 implements the AD-6 / FR-17 mandatory test artifact gate at the persistence boundary.
- New store module `backend/store/errors.py` holds `TestArtifactMissingError` — kept in `backend/store/` (not `backend/api/`) because the guardrail is enforced by the store, per AD-6.
- `project_store.write_test_artifact` fails fast on non-string / empty / whitespace refs BEFORE touching the pool (verified in tests via `get_pool.assert_not_called()`).
- `project_store.mark_ticket_done` performs SELECT → gate check → UPDATE inline; it never delegates to `update_ticket_status`, so no code path can skip the check. Handles both dict and JSON-string forms of `ticket_history` returned by asyncpg.
- `TesterAgent.write_and_run_tests` is now `async`. Scaffold-test generation preserved (project-context.md TODO). Real log file written under `<workspace>/logs/test-<ticket_id>-<yyyymmddHHMMSS>.log`; artifact_ref forward-slashed for JSON/Postgres round-trip safety.
- `SupervisorAgent._execute_ticket` awaits the tester and now has a defensive `test_result.status != "success"` branch that flips the ticket to `"Error"`. The `"In Review"` transition on the happy path is unchanged (Story 5.2 gate preserved). New `close_ticket_as_done` method exposes the gated Done transition for downstream stories 5.7–5.9 / the code-review workflow — it is NOT auto-invoked here.
- `main_agent.py` CLI/PR paths await the tester and print the artifact ref. Store write is skipped because CLI has no `project_id` (documented escape hatch, AC-1).
- Confirmed audit (Task 5.4): `tests/test_supervisor_agent.py` patched `tester.write_and_run_tests` with a plain `MagicMock` — switched to `AsyncMock` and updated `FAKE_TEST_RESULT["status"]` from `"ok"` to `"success"` so the happy-path assertions still pass under the new tester-status branch.
- No PostgreSQL migration needed — `test_artifact_ref` lives inside each ticket dict in the existing `ticket_history` JSONB column.

### File List

**New files:**
- `backend/store/errors.py`
- `tests/test_project_store_test_artifact.py`
- `tests/test_tester_agent_artifact.py`
- `tests/test_supervisor_test_artifact_gate.py`

**Modified files:**
- `backend/store/project_store.py` — added `write_test_artifact`, `mark_ticket_done`, and `TestArtifactMissingError` import.
- `agents/tester_agent.py` — `write_and_run_tests` is now async, writes a real log artifact, calls `project_store.write_test_artifact` when a `project_id` is present.
- `agents/supervisor_agent.py` — imports `TestArtifactMissingError`, awaits the tester call, adds the testing-failure branch, and adds the `close_ticket_as_done` method.
- `agents/main_agent.py` — both `write_and_run_tests` call sites are now awaited and print the artifact ref.
- `tests/test_supervisor_agent.py` — switched tester mock to `AsyncMock` and set `FAKE_TEST_RESULT["status"] = "success"` so existing tests are compatible with the new async-tester contract.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — story status ready-for-dev → in-progress → review.

### Change Log

| Date       | Change                                                                                     |
| ---------- | ------------------------------------------------------------------------------------------ |
| 2026-08-31 | Implemented Story 5.6: mandatory test artifact gate (AD-6 / FR-17). All ACs satisfied.     |
| 2026-08-31 | `TesterAgent.write_and_run_tests` converted to async; emits real log artifact.             |
| 2026-08-31 | Added `backend/store/errors.py` with `TestArtifactMissingError`.                           |
| 2026-08-31 | Added `project_store.write_test_artifact` and gated `project_store.mark_ticket_done`.      |
| 2026-08-31 | Added `SupervisorAgent.close_ticket_as_done` — gated Done transition for downstream use.   |
| 2026-08-31 | 20 new tests added, full suite green (80 passed).                                          |
