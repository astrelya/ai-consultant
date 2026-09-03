---
baseline_commit: b873c0bec72ac891aa89d1b0fcf39a979992fbc7
---

# Story 5.3: Cross-Ticket Accumulated Context

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want each agent to have full access to the outputs, decisions, and file paths established in all previously completed tickets in the current run,
So that the agent never asks me to re-explain what was already built.

## Acceptance Criteria

1. **Given** Ticket N-1 has been completed
   **When** the agent begins Ticket N
   **Then** the agent's invocation prompt includes a summary of all prior ticket outcomes (titles, key decisions, created file paths) from the project's `ticket_history` in PostgreSQL
2. **And** the agent can reference code paths or decisions from prior tickets without the user providing that information again
3. **And** adding context from prior tickets does not trigger additional LLM calls beyond the ticket implementation call itself

## Tasks / Subtasks

- [x] 1. Build `_build_accumulated_context()` helper in `agents/supervisor_agent.py` (AC: 1, 2, 3)
  - [x] 1.1 Extract all `ticket_history` entries whose `status` is `Done` or `In Review` and whose `id` precedes the current ticket in the execution queue
  - [x] 1.2 Format them into a compact, human-readable markdown block: ticket title, key decisions, created/modified file paths (from `completion_notes` and `file_list` fields if present, else gracefully omit)
  - [x] 1.3 Keep formatting deterministic — no LLM call to produce this summary
- [x] 2. Inject accumulated context into the developer sub-agent invocation prompt (AC: 1, 2)
  - [x] 2.1 Modify `_execute_ticket()` in `SupervisorAgent` to call `_build_accumulated_context()` before delegating to the developer
  - [x] 2.2 Prepend the context block to the `prompt` argument passed to `LocalDeveloperAgent.implement_feature()` and `RemoteDeveloperAgent.implement_feature()`
  - [x] 2.3 When no prior completed tickets exist (first ticket or no history), pass an empty/absent context block — must not crash
- [x] 3. Update unit tests in `tests/test_supervisor_agent.py` (AC: 1, 2, 3)
  - [x] 3.1 Test that `_build_accumulated_context()` returns an empty string when `ticket_history` has no completed predecessors
  - [x] 3.2 Test that it returns a formatted block containing title and file paths of a prior `In Review` ticket
  - [x] 3.3 Test that the context block is included verbatim in the prompt received by the mocked developer sub-agent
  - [x] 3.4 Test that no extra `project_store.get_project()` calls occur beyond the one already made in `_execute_ticket()`

## Dev Notes

### What Story 5.2 Built (Must Not Break)

Story 5.2 implemented:
- `agents/supervisor_agent.py` — `SupervisorAgent` class with `run_tickets()` and `_execute_ticket()`.
- `_execute_ticket()` flow: `publish_event` → `project_store.get_project()` → `_find_ticket()` → `EnvironmentAgent.prepare_environment()` → `_delegate_to_developer()` → `TesterAgent.write_and_run_tests()` → `project_store.update_ticket_status("In Review")` → `publish_event`.
- `_delegate_to_developer()` routes to `LocalDeveloperAgent.implement_feature(story_details, workspace_path)` or `RemoteDeveloperAgent.implement_feature(story_details, workspace_path)` based on `AGENT_MODE`.
- `backend/api/routes/execute.py` calls `supervisor.run_tickets(project_id, ticket_ids)` inside the global asyncio lock.
- `tests/test_supervisor_agent.py` — 16 unit tests, all passing.

**Key preservation rule:** Do NOT add a second `project_store.get_project()` call — `_execute_ticket()` already loads the full project (including `ticket_history`). Pass that project dict to `_build_accumulated_context()`. AC-3 explicitly requires zero extra LLM calls and, by extension, minimal extra DB calls.

### Architecture Compliance

- **AD-1 (agent hierarchy):** `_build_accumulated_context()` is a pure Python helper on `SupervisorAgent` — it does not call sub-agents.
- **AD-2 (sequential lock):** Context building happens inside the lock, which is already held — no changes needed to locking.
- **AD-4 (LLM-as-last-resort):** Context building MUST be pure Python string manipulation. No LLM call to summarize prior tickets. AC-3 mandates this explicitly.
- **AD-9 (async):** `_build_accumulated_context()` is synchronous (pure data processing — no I/O). Calling it from the `async` `_execute_ticket()` is fine.

### `ticket_history` Schema (from `project_store.py` / DB)

`ticket_history` is a JSONB array on the `projects` table. Each element is a dict. Fields set by upstream stories:

```python
{
    "id": "TICKET-1",               # string ticket ID
    "title": "Implement login",     # string
    "description": "...",           # string (may be large)
    "status": "In Review",          # "Pending" | "In Progress" | "In Review" | "Done" | "Error" | "Failed"
    # Optional fields written by dev agents / TesterAgent:
    "completion_notes": "...",      # free-form string — key decisions, caveats
    "file_list": ["src/login.py"],  # list of str paths created/modified
}
```

> **Important:** Fields beyond `id`, `title`, `description`, `status` are **optional** — guard all access with `.get()` and provide empty defaults. The codebase has NOT yet standardized `completion_notes` or `file_list` on tickets; this story must gracefully handle their absence.

### Accumulated Context Format

The context block injected into the developer prompt should look like:

```
--- Previously Completed Tickets ---
[TICKET-1] Implement login page
  Files: src/login.py, tests/test_login.py
  Notes: Used bcrypt for password hashing; session token stored in cookie.

[TICKET-2] Add project list API
  Files: backend/api/routes/projects.py
  Notes: (none)
-------------------------------------
```

- Only include tickets with `status` in `{"Done", "In Review"}` and whose `id` appears **before** the current ticket ID in the `ticket_ids` execution queue.
- Keep it compact — title + files + notes only. Do NOT include `description` (too verbose).
- If no prior tickets: omit the block entirely (pass `""` or don't add to prompt).

### `implement_feature()` Prompt Injection Point

Both `LocalDeveloperAgent.implement_feature(story_details, workspace_path)` and `RemoteDeveloperAgent.implement_feature(story_details, workspace_path)` receive `story_details` which already has:

```python
story_details = {
    "id": ticket_id,
    "title": ticket.get("title", ""),
    "description": ticket.get("description", ""),
    "project_id": project_id,
    "agent_memory": project.get("agent_memory"),
    # Added by Story 5.2:
    "repo_full_name": env_result.get("repo_full_name"),
}
```

The cleanest approach: add `"accumulated_context"` to the `story_details` dict before calling `_delegate_to_developer()`. The developer agent already receives `story_details` and builds its prompt from it. This avoids changing the `implement_feature()` signature (which would break existing tests).

> **Do NOT change `implement_feature()` signatures.** Instead, add `story_details["accumulated_context"] = context_block` and let each developer agent include it in its prompt if present (or gracefully ignore if absent — since developer agents were written before this story).

**Alternative if developer agents don't use `accumulated_context` key:** Append the context block to `story_details["description"]`. This is the safest approach if you cannot confirm developer agents read `story_details["accumulated_context"]`. Decide based on reading the current developer agent implementations.

### File Locations to Modify

- `agents/supervisor_agent.py` [MODIFY] — add `_build_accumulated_context()` and update `_execute_ticket()` / `run_tickets()` to pass `ticket_ids` down so the helper can determine ordering
- `tests/test_supervisor_agent.py` [MODIFY] — add ≥4 new tests covering the above (see Tasks section)

**Do NOT modify:**
- `backend/api/routes/execute.py` (no changes needed — passes `ticket_ids` already)
- `backend/store/project_store.py` (no new DB functions needed — `get_project()` already returns full `ticket_history`)
- Developer agent files (interface unchanged)

### Testing Pattern (from Story 5.2)

The 16 existing tests use `unittest.mock` with `patch` decorators to mock `project_store.*`, `publish_event`, and sub-agent methods. New tests should follow the same pattern:

```python
@pytest.mark.asyncio
async def test_accumulated_context_included_in_prompt():
    with patch("agents.supervisor_agent.project_store") as mock_store, \
         patch("agents.supervisor_agent.publish_event", new_callable=AsyncMock), \
         patch.object(EnvironmentAgent, "prepare_environment", return_value=FAKE_ENV_SUCCESS), \
         patch.object(LocalDeveloperAgent, "implement_feature", new_callable=AsyncMock) as mock_dev, \
         patch.object(TesterAgent, "write_and_run_tests", return_value=FAKE_TEST_RESULT):
        mock_store.get_project = AsyncMock(return_value=FAKE_PROJECT_WITH_PRIOR_TICKET)
        mock_store.update_ticket_status = AsyncMock()
        mock_dev.return_value = FAKE_DEV_SUCCESS
        sv = SupervisorAgent()
        sv.mode = "local"
        await sv.run_tickets(FAKE_PROJECT_ID, ["TICKET-1", "TICKET-2"])
        # Assert TICKET-2's implement_feature call received a story_details
        # containing accumulated context referencing TICKET-1
        call_args = mock_dev.call_args_list[1]  # second call = TICKET-2
        story_details_arg = call_args[0][0]
        assert "TICKET-1" in (story_details_arg.get("accumulated_context", "") or story_details_arg.get("description", ""))
```

### Project Structure Notes

- `agents/supervisor_agent.py` lives at `{project-root}/agents/supervisor_agent.py`
- `tests/test_supervisor_agent.py` lives at `{project-root}/tests/test_supervisor_agent.py`
- No new files needed — this is a targeted enhancement to existing modules
- All imports already present in `supervisor_agent.py`; no new dependencies

### References

- Story 5.2 file: [Source: `_bmad-output/implementation-artifacts/5-2-supervisoragent-wired-to-backend-and-project-store.md`]
- FR-12: "Accumulated Cross-Ticket Context" [Source: `_bmad-output/planning-artifacts/epics.md#FR Coverage Map`]
- Epic 5, Story 5.3 ACs [Source: `_bmad-output/planning-artifacts/epics.md#Story 5.3`]
- Architecture AD-1, AD-4, AD-9 [Source: `_bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md`]
- `ticket_history` schema [Source: `backend/store/project_store.py`, `backend/store/database.py`]
- `story_details` structure [Source: `agents/supervisor_agent.py#_execute_ticket()`]
- Test patterns [Source: `tests/test_supervisor_agent.py`]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (Thinking)

### Debug Log References

- Baseline: 16 pre-existing `tests/test_supervisor_agent.py` tests green before edits (venv Python 3.12).
- Full `tests/` suite green after implementation: 24 passed.
- Note: repo-root `test_sse.py` exits at import time due to missing backend env — pre-existing, unrelated to this story.

### Completion Notes List

- Added `SupervisorAgent._build_accumulated_context(project, ticket_ids, current_ticket_id)` as a pure static helper. No LLM, no DB.
- Ordering source of truth is the execution queue (`ticket_ids`), not `ticket_history` position. Only tickets appearing strictly before `current_ticket_id` in the queue are considered.
- Eligibility filter: `status ∈ {"Done", "In Review"}` — matches the story's AC-1 wording and existing lifecycle (5.2 sets tickets to `In Review` after success).
- Optional fields (`file_list`, `completion_notes`) are guarded with `.get()` and default cleanly to absent/`(none)`.
- Injection strategy: set `story_details["accumulated_context"]` **and** prepend the block to `story_details["description"]`. Since developer agent files are explicitly out of scope for modification, prepending to `description` guarantees the context reaches the LLM prompt today; the `accumulated_context` key remains available for future consumers.
- `_execute_ticket()` signature extended to receive `ticket_ids` from `run_tickets()`; call site updated. No public API change.
- AC-3 (no extra LLM calls) is enforced structurally — the helper is synchronous, pure Python string manipulation, and reuses the single `project` dict already loaded by `_execute_ticket()`. New test `test_no_extra_get_project_calls_beyond_execute_ticket` locks this in at 1 `get_project` call per ticket.

### File List

- `agents/supervisor_agent.py` [MODIFIED]
- `tests/test_supervisor_agent.py` [MODIFIED]

### Change Log

- 2026-08-31: Story 5.3 implemented. Added `_build_accumulated_context()` and wired it into `_execute_ticket()`. Added 8 new unit tests. All 24 supervisor-agent tests green.
