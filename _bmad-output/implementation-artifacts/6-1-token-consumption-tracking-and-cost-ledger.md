---
baseline_commit: b873c0bec72ac891aa89d1b0fcf39a979992fbc7
---

# Story 6.1: Token Consumption Tracking and Cost Ledger

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want every LLM call in the agent layer to record its token count and estimated USD cost to the project's `cost_ledger` in PostgreSQL,
so that I have an accurate, persistent record of usage and cost per project across all sessions (FR-25 / Epic 6).

## Acceptance Criteria

1. **Given** any `.ainvoke(...)` call is made on a LangChain LLM or a LangGraph ReAct `agent_executor` inside the agent layer (`agents/`),
   **When** the call completes successfully,
   **Then** the prompt-token and completion-token counts extracted from the returned message(s) MUST be written to the active project's `cost_ledger` JSONB column BEFORE the calling function returns its own result. Extraction MUST use LangChain's `AIMessage.usage_metadata` (`input_tokens`, `output_tokens`, `total_tokens`) which Gemini populates. If `usage_metadata` is missing/None on every AI message in the response (defensive: some tool-only turns), the recorder MUST record `prompt_tokens=0, completion_tokens=0, cost_usd=0.0` and MUST NOT raise. For a ReAct `agent_executor.ainvoke(...)` return value of shape `{"messages": [...]}`, the recorder MUST sum `input_tokens` and `output_tokens` across ALL `AIMessage` instances in `result["messages"]` — not just the last one — because a single ReAct invocation may span multiple LLM turns (tool calls + final answer). For a direct `llm.ainvoke(prompt)` returning a single `AIMessage`, the recorder MUST read its single `usage_metadata`.

2. **And** a new module `agents/token_tracker.py` MUST be created with the following public surface (exact names — the tests in Task 5 pin them):
   - `CURRENT_PROJECT_ID: contextvars.ContextVar[str | None]` — module-level `ContextVar` with default `None`.
   - `CURRENT_SESSION_ID: contextvars.ContextVar[str | None]` — module-level `ContextVar` with default `None`.
   - `_SESSION_TOTALS: dict[str, dict]` — process-local in-memory map keyed by `session_id` holding `{"tokens": int, "cost_usd": float}`. Reset to `{"tokens": 0, "cost_usd": 0.0}` on first insert per session_id.
   - `def compute_cost_usd(total_tokens: int) -> float` — pure helper: reads env var `COST_PER_1K_TOKENS` (float, default `"0.00015"` — Gemini 2.5 Flash published input price per 1K tokens as of 2026-Q3, documented in the module docstring as a sensible default), returns `round(total_tokens / 1000.0 * price, 6)`. Invalid env value (non-parseable float) MUST fall back to the default and MUST NOT raise.
   - `async def record_llm_call(result: Any, *, project_id: str | None = None, session_id: str | None = None) -> dict` — the core recorder. Behaviour: (a) if `project_id` is `None`, read `CURRENT_PROJECT_ID.get()`; if still `None`, return `{"skipped": True, "reason": "no_project_id"}` WITHOUT raising. (b) Same fallback for `session_id` via `CURRENT_SESSION_ID.get()`; if still `None`, use `session_id = "__no_session__"` (still records to DB — session totals just accumulate under that key). (c) Sum `input_tokens` / `output_tokens` from all AI messages per AC-1. (d) Compute `cost_usd = compute_cost_usd(prompt_tokens + completion_tokens)`. (e) Update `_SESSION_TOTALS[session_id]` in-memory. (f) Call new store function `add_cost_ledger_entry(project_id, prompt_tokens, completion_tokens, cost_usd)` (AC-4). (g) After DB write, publish a `token_update` SSE event per AC-6. (h) Return `{"prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ..., "cost_usd": ..., "session_tokens": ..., "session_cost_usd": ..., "total_tokens_project": ..., "total_cost_usd_project": ...}`.
   - `async def tracked_ainvoke(executor, payload, *, project_id: str | None = None, session_id: str | None = None) -> Any` — wrapper: `result = await executor.ainvoke(payload); await record_llm_call(result, project_id=project_id, session_id=session_id); return result`. This is the ONLY new callable the agent modules import.
   - `def reset_session(session_id: str) -> None` — sets `_SESSION_TOTALS[session_id]` to `{"tokens": 0, "cost_usd": 0.0}`. Called by SupervisorAgent at the start of every `execute` run (AC-5).

3. **And** every existing `.ainvoke(` call site in the `agents/` layer that invokes an LLM or a ReAct agent MUST be migrated to `await tracked_ainvoke(...)`. The complete migration set (verified against the current tree at baseline_commit b873c0b) is EXACTLY these five sites — no more, no less:
   - `agents/developer_agent.py` line ~59 (`RemoteDeveloperAgent.implement_feature` — main coding turn)
   - `agents/developer_agent.py` line ~125 (`RemoteDeveloperAgent.implement_pr_recommendations` — PR fix turn)
   - `agents/local_developer_agent.py` line ~91 (`LocalDeveloperAgent.implement_feature`)
   - `agents/local_developer_agent.py` line ~144 (`LocalDeveloperAgent.implement_pr_recommendations`)
   - `agents/main_agent.py` line ~273 (`SupervisorAgent.chat` — router agent turn)
   MCP tool calls (`resolve_tool.ainvoke(...)` and `docs_tool.ainvoke(...)` in `agents/context7_grounding.py`) are NOT LLM calls and MUST NOT be wrapped — they call MCP servers directly. The single true LLM call in `agents/context7_grounding.py` at line 53 (`await llm.ainvoke(prompt)` for the query-extraction step) IS an LLM call and MUST be wrapped. Total wrapped sites: **6**.

4. **And** `backend/store/project_store.py` MUST gain a new public async function `add_cost_ledger_entry(project_id: str, prompt_tokens: int, completion_tokens: int, cost_usd: float) -> dict` that updates the `cost_ledger` JSONB column atomically in a single UPDATE statement using PostgreSQL's `jsonb_set` + `COALESCE`. The `cost_ledger` JSONB shape MUST be exactly:
   ```json
   {
     "total_prompt_tokens": <int>,
     "total_completion_tokens": <int>,
     "total_tokens": <int>,
     "total_cost_usd": <float>,
     "last_updated": "<ISO-8601 UTC>"
   }
   ```
   No per-call history array is stored (v1 constraint — prevents unbounded JSONB growth; per-call history is a v2 feature). The function MUST handle the "first-ever entry" case where `cost_ledger` is `{}` (the current default per `backend/store/database.py:64`) — treat missing keys as zero. The function MUST return the NEW ledger state as a Python dict (parsed from the RETURNING clause). Concurrency guarantee: even though AD-2 (global sequential lock) forbids concurrent ticket execution, this function MUST still be atomic within a single connection so that concurrent read-only endpoints (e.g. `GET /projects/{id}`) never observe a torn write. Implementation: use a single `UPDATE projects SET cost_ledger = ... WHERE id = $1 RETURNING cost_ledger` with the arithmetic done inline in SQL via `jsonb_build_object` and `COALESCE((cost_ledger->>'total_tokens')::int, 0) + $2`.

5. **And** `agents/supervisor_agent.py` `SupervisorAgent.execute(project_id, ticket_ids)` MUST, at the very top of the method (BEFORE any existing logic, BEFORE the `for ticket_id in ticket_ids` loop, and BEFORE any SSE event is published), do these two things in this order:
   1. Generate a fresh `session_id = str(uuid.uuid4())` (add `import uuid` at the top of the file if not present).
   2. Set `token_tracker.CURRENT_PROJECT_ID.set(project_id)` and `token_tracker.CURRENT_SESSION_ID.set(session_id)`, and call `token_tracker.reset_session(session_id)`.
   These ContextVar sets propagate automatically into every `await` chain launched from `execute` (that is the contract of `contextvars` in async code), so downstream sub-agents (`developer_agent`, `local_developer_agent`, `tester_agent`, `context7_grounding`) do NOT need to receive or forward `project_id`/`session_id` explicitly — the `tracked_ainvoke` wrapper reads them from context. This is the key architectural choice that avoids invasive signature changes across every agent method. `SupervisorAgent.chat` MUST similarly set the ContextVars at the top of the method — `session_id` for a chat turn MAY be reused across turns (persist it as `self._chat_session_id: str | None = None` and lazily initialise on first `chat` call) so the "current chat session" cost accumulates naturally.

6. **And** immediately AFTER `add_cost_ledger_entry` returns (still inside `record_llm_call`), the recorder MUST publish an SSE event with EXACT event type `"token_update"` on the project's channel via `backend.api.sse.publish_event(project_id, "token_update", payload)`. The payload MUST be a dict with EXACTLY these four keys and no others: `{"session_tokens": int, "session_cost_usd": float, "total_tokens": int, "total_cost_usd": float}`. Values: `session_tokens` and `session_cost_usd` come from `_SESSION_TOTALS[session_id]`; `total_tokens` and `total_cost_usd` come from the ledger dict returned by `add_cost_ledger_entry`. If `publish_event` raises (e.g. no active SSE subscribers — currently returns silently, but defensively guarded), the exception MUST be caught and logged (`logger.warning`) so the LLM call's own result path is NEVER broken by an SSE plumbing failure. FR-25 requires the cost display to be updated after every LLM call — this SSE event is the sole delivery mechanism.

7. **And** NO additional LLM call MUST be made to compute or display the cost. `compute_cost_usd` is pure arithmetic. Verified by test (Task 5.4): monkeypatch `ChatGoogleGenerativeAI.ainvoke` to count invocations across a full ticket execution flow and assert the count equals the pre-instrumentation baseline plus zero (i.e., wrapping introduces no new LLM turns).

8. **And** the ledger MUST NEVER be reset when a session ends. `reset_session` only clears the in-memory `_SESSION_TOTALS[session_id]` counter; it MUST NOT touch the `cost_ledger` column. Persistence across sessions is proven by test (Task 5.5): create project, invoke `record_llm_call` twice with `session_id="A"`, call `reset_session("A")` (or start a fresh `session_id="B"`), invoke once more, then read the project from PostgreSQL and assert `cost_ledger.total_tokens` equals the sum of all three calls.

9. **And** the `token_tracker` module MUST have zero coupling to `SupervisorAgent` and MUST NOT import from `agents/` (no circular imports). It imports from `backend.store.project_store` and `backend.api.sse` only. This keeps the recorder reusable across future non-supervisor call sites (e.g. a standalone script or a future analytics endpoint).

10. **And** the FR-25 test artefact for THIS story is the pytest suite added under `tests/` per Task 5. Story 6.2 (Cost Display in Chat View) is the frontend consumer of the `token_update` SSE event and is out of scope here. Story 6.1 delivers: (a) the ledger in PostgreSQL, (b) the SSE event, (c) instrumentation of every LLM call site. No frontend work.

## Tasks / Subtasks

- [x] 1. Create `agents/token_tracker.py` module (AC: 2, 6, 7, 9)
  - [x] 1.1 Create the file with imports: `import contextvars`, `import logging`, `import os`, `from typing import Any`, `from backend.store import project_store`, `from backend.api.sse import publish_event`. Define `logger = logging.getLogger(__name__)`.
  - [x] 1.2 Define `CURRENT_PROJECT_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar("CURRENT_PROJECT_ID", default=None)` and `CURRENT_SESSION_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar("CURRENT_SESSION_ID", default=None)` at module scope.
  - [x] 1.3 Define `_SESSION_TOTALS: dict[str, dict] = {}` at module scope. Document in a module docstring: this is process-local and by design not persisted — persistence is via `cost_ledger`.
  - [x] 1.4 Implement `compute_cost_usd(total_tokens: int) -> float` per AC-2 semantics. Default env value `"0.00015"`. Wrap the `float(os.environ.get("COST_PER_1K_TOKENS", "0.00015"))` in try/except `ValueError` returning the hard-coded default on parse failure — log at `WARNING`.
  - [x] 1.5 Implement helper `_extract_tokens_from_result(result: Any) -> tuple[int, int]` (private): if `result` is a dict containing `"messages"`, iterate each message, and for each message that has a truthy `usage_metadata` (a dict), read `.get("input_tokens", 0)` and `.get("output_tokens", 0)` and sum. If `result` is an object with a `.usage_metadata` attribute (single-message case), read from that. If neither shape matches, return `(0, 0)`. NEVER raise.
  - [x] 1.6 Implement `async def record_llm_call(...)` per AC-2 semantics. Guard the `publish_event` call in try/except per AC-6.
  - [x] 1.7 Implement `async def tracked_ainvoke(executor, payload, *, project_id=None, session_id=None) -> Any` per AC-2 signature. Return the raw `result` (never mutate it).
  - [x] 1.8 Implement `def reset_session(session_id: str) -> None` per AC-2, AC-8.

- [x] 2. Add `add_cost_ledger_entry` to `backend/store/project_store.py` (AC: 4)
  - [x] 2.1 Add `import datetime` (already present — verify).
  - [x] 2.2 Append the new function after `overwrite_ticket_history`. Signature: `async def add_cost_ledger_entry(project_id: str, prompt_tokens: int, completion_tokens: int, cost_usd: float) -> dict`.
  - [x] 2.3 SQL (single statement — must be atomic):
    ```python
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    total_tokens = prompt_tokens + completion_tokens
    pool = database.get_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow(
            """
            UPDATE projects
            SET cost_ledger = jsonb_build_object(
                'total_prompt_tokens',    COALESCE((cost_ledger->>'total_prompt_tokens')::int, 0)    + $2,
                'total_completion_tokens',COALESCE((cost_ledger->>'total_completion_tokens')::int, 0)+ $3,
                'total_tokens',           COALESCE((cost_ledger->>'total_tokens')::int, 0)           + $4,
                'total_cost_usd',         COALESCE((cost_ledger->>'total_cost_usd')::float, 0.0)     + $5,
                'last_updated',           $6::text
            )
            WHERE id = $1
            RETURNING cost_ledger
            """,
            project_id, prompt_tokens, completion_tokens, total_tokens, cost_usd, now_iso,
        )
    if not record or record["cost_ledger"] is None:
        return {}
    raw = record["cost_ledger"]
    return json.loads(raw) if isinstance(raw, str) else dict(raw)
    ```
  - [x] 2.4 Guard: if `project_id` doesn't exist, `fetchrow` returns `None` — return `{}` and log at `WARNING` (do NOT raise; this keeps failing SSE plumbing from crashing the LLM call).

- [x] 3. Migrate the six LLM `.ainvoke` call sites to `tracked_ainvoke` (AC: 3)
  - [x] 3.1 `agents/context7_grounding.py` line 53:
    - Add import at top: `from agents.token_tracker import tracked_ainvoke`.
    - Change `result = await llm.ainvoke(prompt)` to `result = await tracked_ainvoke(llm, prompt)`. Note: `llm.ainvoke(prompt)` takes a string; `tracked_ainvoke` calls `executor.ainvoke(payload)` — same signature. Verify by reading the function around the change site to preserve prompt shape.
  - [x] 3.2 `agents/developer_agent.py` line ~59 (`implement_feature`):
    - Add import: `from agents.token_tracker import tracked_ainvoke`.
    - Change `result = await agent_executor.ainvoke({"messages": [("user", system_prompt)]})` to `result = await tracked_ainvoke(agent_executor, {"messages": [("user", system_prompt)]})`.
  - [x] 3.3 `agents/developer_agent.py` line ~125 (`implement_pr_recommendations`): identical migration pattern to 3.2.
  - [x] 3.4 `agents/local_developer_agent.py` line ~91 (`implement_feature`): identical pattern (add import once at top).
  - [x] 3.5 `agents/local_developer_agent.py` line ~144 (`implement_pr_recommendations`): identical pattern.
  - [x] 3.6 `agents/main_agent.py` line ~273 (`SupervisorAgent.chat` router turn): identical pattern.
  - [x] 3.7 DO NOT wrap the MCP tool calls in `agents/context7_grounding.py` lines ~132 and ~141 (`resolve_tool.ainvoke(...)`, `docs_tool.ainvoke(...)`) — these are MCP tool invocations, not LLM calls, and produce no `usage_metadata`.
  - [x] 3.8 DO NOT wrap `.ainvoke` calls in `.agents/skills/` or `.agent/skills/` — those are BMad framework documentation prompts, not runtime code.

- [x] 4. Wire ContextVars in `agents/supervisor_agent.py` and `agents/main_agent.py` (AC: 5)
  - [x] 4.1 In `agents/supervisor_agent.py`, add at the top of the file: `import uuid` (verify not already present) and `from agents import token_tracker`.
  - [x] 4.2 Locate `SupervisorAgent.execute(self, project_id, ticket_ids, ...)` (verify exact signature at baseline). At the very first line of the method body (before any docstring-following code, before the `try` or the `for` loop), insert:
    ```python
    session_id = str(uuid.uuid4())
    token_tracker.CURRENT_PROJECT_ID.set(project_id)
    token_tracker.CURRENT_SESSION_ID.set(session_id)
    token_tracker.reset_session(session_id)
    ```
  - [x] 4.3 In `agents/main_agent.py` `SupervisorAgent.chat(self, project_id, user_command, ...)`: verify exact signature; if `project_id` is available as a parameter, do the same three-line setup at the top of the method. If `project_id` is stored on `self`, use `self.project_id`. Session ID for chat: initialise `self._chat_session_id: str | None = None` in `__init__` (add if not present); in `chat`, use `if self._chat_session_id is None: self._chat_session_id = str(uuid.uuid4()); token_tracker.reset_session(self._chat_session_id)` then set the ContextVars to `project_id` and `self._chat_session_id`.
  - [x] 4.4 If `agents/main_agent.py`'s `SupervisorAgent.chat` currently has no `project_id` parameter (verify at baseline), thread it in from the calling REST route (`backend/api/routes/chat.py` — read the file to confirm) — this is a signature-broadening additive change. If the route does not have a `project_id` yet, that is a Story 5.4 gap and is IN scope for this story to bridge (record why in dev notes).

- [x] 5. Add tests under `tests/` (AC: 1, 4, 6, 7, 8, 10)
  - [x] 5.1 Create `tests/test_token_tracker_extraction.py`: unit tests for `_extract_tokens_from_result` covering (a) ReAct result shape `{"messages": [AIMessage(usage_metadata={"input_tokens":10,"output_tokens":5,"total_tokens":15}), AIMessage(usage_metadata={"input_tokens":7,"output_tokens":3,"total_tokens":10})]}` → returns `(17, 8)`; (b) single `AIMessage` with `usage_metadata` → correct extraction; (c) messages with `usage_metadata=None` → `(0, 0)`; (d) messages that are not `AIMessage` (e.g. `ToolMessage`) → skipped; (e) unknown result shape → `(0, 0)` with no exception.
  - [x] 5.2 Create `tests/test_token_tracker_cost.py`: unit tests for `compute_cost_usd` — default env, custom env value, malformed env value (falls back to default without raising), zero tokens returns `0.0`.
  - [x] 5.3 Create `tests/test_add_cost_ledger_entry.py`: async test using a mocked `pool.acquire` + `conn.fetchrow` (follow the existing pattern in `tests/test_project_store_*.py`). Assert: (a) first-call SQL executes with correct params; (b) `project_id` not found returns `{}` and does not raise; (c) return shape matches AC-4.
  - [x] 5.4 Create `tests/test_token_tracker_record.py`: async tests for `record_llm_call`. Mock `project_store.add_cost_ledger_entry` and `publish_event`. Test cases: (a) no `project_id` in context → returns `{"skipped": True, "reason": "no_project_id"}` and does NOT call the store or SSE; (b) full path — ContextVars set, ReAct-shape result — asserts `add_cost_ledger_entry` called with summed tokens, `publish_event` called with `"token_update"` and correct payload shape (exactly the four keys per AC-6); (c) `publish_event` raising `RuntimeError` — recorder swallows and still returns the token dict.
  - [x] 5.5 Create `tests/test_token_tracker_persistence.py`: integration-style test with the store fully mocked. Simulate three sequential `record_llm_call` invocations across two `session_id`s, asserting: `_SESSION_TOTALS["A"]` after `reset_session("A")` is `{"tokens": 0, "cost_usd": 0.0}` regardless of prior calls, AND the mocked ledger accumulates across all three (AC-8 persistence proof).
  - [x] 5.6 Create `tests/test_supervisor_token_tracking.py`: assert that (a) `SupervisorAgent.execute` sets the two ContextVars and calls `reset_session` before the first `_execute_ticket` call — patch `token_tracker.reset_session` and `token_tracker.CURRENT_PROJECT_ID.set`/`CURRENT_SESSION_ID.set` (use `mock.patch.object`) and assert call order; (b) no new LLM call is introduced — patch `ChatGoogleGenerativeAI.ainvoke` and assert wrapped executions call `.ainvoke` on the executor exactly once per site.
  - [x] 5.7 All new tests MUST pass under `pytest -q` with zero warnings introduced by this story's code.

- [x] 6. Regression validation (AC: 1, 3, 8)
  - [x] 6.1 Run the full existing test suite: `pytest tests/ -q`. All previously-passing tests MUST still pass — the recorder is purely additive and must not change any existing behaviour or return value.
  - [x] 6.2 If `tests/test_supervisor_regression_fix.py` or `tests/test_supervisor_error_report.py` mocks `agent_executor.ainvoke`, verify those mocks return a shape that includes `messages` (they do — verified at baseline). No test rewrite should be needed.
  - [x] 6.3 If a test now fails because ContextVar state leaks between tests (`CURRENT_PROJECT_ID.set` persists across tests in a shared event loop), add a pytest fixture `autouse` in `tests/conftest.py` (create if missing) that resets both ContextVars to `None` after each test. Prefer this over per-test cleanup.

## Dev Notes

### Architecture patterns & constraints (must obey)

- **AD-9 (Async throughout):** every new function that touches DB or SSE is `async def`. `compute_cost_usd` and `reset_session` are pure and stay sync.
- **AD-2 (Global sequential execution lock):** Story 6.1 runs entirely inside the lock held by `SupervisorAgent.execute`. No new lock. No new concurrency primitive.
- **AD-4 (LLM-as-last-resort):** cost computation MUST NOT invoke an LLM. This is why `COST_PER_1K_TOKENS` is a hard-coded fallback — asking the LLM "what's the current Gemini price?" is explicitly forbidden.
- **AD-5 (Project isolation):** `cost_ledger` is a column on `projects` — already partitioned per project by primary key. No cross-project aggregation exists or is added.
- **AD-7 (Streaming over polling):** `token_update` SSE is the sole delivery mechanism to the frontend. No polling endpoint. Story 6.2 (the consumer) will subscribe to this event.
- **AD-13 (Config from env vars):** `COST_PER_1K_TOKENS` follows the standard `UPPER_SNAKE_CASE` + `os.environ.get(..., default)` pattern. Documented in the module docstring; add to `README.md`'s env var table if such a table exists (verify).

### Source tree components to touch

**NEW files:**
- `agents/token_tracker.py` (recorder module — AC-2)
- `tests/test_token_tracker_extraction.py`
- `tests/test_token_tracker_cost.py`
- `tests/test_add_cost_ledger_entry.py`
- `tests/test_token_tracker_record.py`
- `tests/test_token_tracker_persistence.py`
- `tests/test_supervisor_token_tracking.py`
- `tests/conftest.py` (only if not already present — for ContextVar reset fixture)

**MODIFIED files (read fully before changing):**
- `agents/supervisor_agent.py` — add `import uuid` + `from agents import token_tracker`; wire ContextVars at top of `execute`.
- `agents/main_agent.py` — wire ContextVars at top of `chat`; possibly widen `chat` signature to accept `project_id` (verify caller in `backend/api/routes/chat.py`).
- `agents/context7_grounding.py` — one line change (line 53).
- `agents/developer_agent.py` — two line changes + one import.
- `agents/local_developer_agent.py` — two line changes + one import.
- `backend/store/project_store.py` — add `add_cost_ledger_entry`.

**DO NOT TOUCH:**
- `backend/store/database.py` schema — `cost_ledger JSONB NOT NULL DEFAULT '{}'` already exists (line 64). No migration needed.
- `backend/api/sse.py` — `publish_event` signature is already correct; do not modify.
- `tools/` — no MCP loader changes. Token extraction is on the return value, not the tool layer.
- `frontend/` — Story 6.2's scope.

### Testing standards summary

- pytest only, `tests/test_*.py` naming, async tests use `pytest.mark.asyncio` (verify the existing pattern in `tests/test_project_store_chat.py` — matches).
- Mock `backend.store.database.get_pool` at its definition site (per the `project_store` module docstring) using `unittest.mock.patch("backend.store.database.get_pool", ...)`.
- Mock `backend.api.sse.publish_event` by patching at the import site inside `agents.token_tracker` (i.e., `patch("agents.token_tracker.publish_event", ...)`) because `token_tracker` imports the symbol directly.
- Test file for LangChain `AIMessage`: `from langchain_core.messages import AIMessage` — construct with `AIMessage(content="hi", usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})`.

### Read files being modified — critical current state

- `agents/supervisor_agent.py`: `execute` is the entry point for ticket runs. Story 5.3 injects accumulated context; Story 5.4 loads chat history; Story 5.6 gates on test artefact; Story 5.7 runs regression fix; Story 5.8/5.9 handle diagnostics/error reports; Story 5.10 injects logging scaffold. Story 6.1 adds ContextVar setup ABOVE all of these — it's a one-time-per-execute setup that must run first because every downstream `.ainvoke` needs the ContextVars populated.
- `agents/main_agent.py::SupervisorAgent.chat`: runs router agent; uses `self.chat_history` per project-context.md; must retain that behaviour. New: `self._chat_session_id` and the ContextVar wiring — additive only.
- `backend/store/project_store.py`: uses `database.get_pool()` (mocked at that path in tests); all functions are `async def`; JSONB updates use single UPDATE statements. `add_cost_ledger_entry` follows this idiom exactly.
- `agents/developer_agent.py` / `agents/local_developer_agent.py`: both have Context7 grounding first, then `agent_executor.ainvoke`. Both are called from `_delegate_to_developer` in `supervisor_agent.py`, which is called from `_execute_ticket`, which is called from `execute` — so the ContextVars set at top of `execute` are visible via the `contextvars` async-propagation contract at every downstream `.ainvoke`.

### Previous story intelligence (Story 5.10 — reviewed)

- Story 5.10 established the pattern of "pure static helper on SupervisorAgent + wire into `_execute_ticket`". Story 6.1 differs: the recorder lives in its own module (`agents/token_tracker.py`) because it's used by six sites, not just SupervisorAgent. This is why AC-9 forbids `token_tracker` from importing SupervisorAgent — it must not become a circular hub.
- Story 5.10's test artefact convention (unit-level pytest in `tests/`, no integration DB test) is followed here.
- Story 5.10's `agent_log` SSE event pattern (informational event before delegation) is intentionally NOT replicated. Story 6.1's SSE event is `token_update` per FR-25 exact naming — do not conflate.
- Story 5.4's `chat_history` persistence pattern demonstrated the atomic JSONB update via a single UPDATE statement with `COALESCE(..., 'defaultjson'::jsonb)`. Story 6.1's `add_cost_ledger_entry` uses the same idiom.

### External context / library specifics

- **LangChain `AIMessage.usage_metadata`** (latest `langchain-core` — see docstring at `langchain_core.messages.ai.UsageMetadata`): a `TypedDict` with keys `input_tokens: int`, `output_tokens: int`, `total_tokens: int`. Some providers add `input_token_details` / `output_token_details`; we ignore those in v1. Gemini via `langchain-google-genai` populates all three top-level keys reliably as of the pinned version.
- **`contextvars.ContextVar` async propagation:** Python's `asyncio` copies the current `Context` on `asyncio.create_task` / `TaskGroup` boundaries. Any `await`ed call chain launched from `execute` sees the same ContextVars — this is why the wiring in AC-5 works without threading `project_id` through every method signature. Verified behaviour: PEP 567.
- **`COST_PER_1K_TOKENS` default `0.00015`:** Gemini 2.5 Flash published input price (Sept 2026) is $0.15/1M input tokens = $0.00015/1K. This is a conservative underestimate for total spend because output tokens on Gemini 2.5 Flash are $0.60/1M; a v2 story can split input/output pricing. For v1 the acceptance criterion demands "the configured model's published price" — a single blended rate satisfies this and is trivial to override via env var. Document this trade-off in the `token_tracker.py` module docstring.

### Project Structure Notes

- Layout matches the ARCHITECTURE-SPINE structural seed: `agents/` for orchestration, `backend/store/` for persistence, `backend/api/` for SSE, `tests/` for unit tests. No new top-level directory.
- No conflicts detected. The `cost_ledger` column already exists in the schema (line 64 of `backend/store/database.py`) — this story consumes existing infrastructure rather than creating it.

### References

- [Epic 6 / Story 6.1 spec](../planning-artifacts/epics.md#story-61-token-consumption-tracking-and-cost-ledger)
- [PRD FR-25](../planning-artifacts/prds/prd-ai-consultant-2026-07-08/prd.md#fr-25-token-consumption-and-cost-display)
- [Architecture Spine — AD-4, AD-5, AD-7, AD-9, AD-13, FR-25 deferred note](../planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md)
- [UX Experience — Token Consumption Display section (Cost Indicator format)](../planning-artifacts/ux-designs/ux-ai-consultant-2026-07-09/EXPERIENCE.md#token-consumption-display)
- [Story 5.10 (previous story) — pattern for pure helper + wiring](./5-10-default-logging-scaffold-in-generated-projects.md)
- [`backend/store/database.py` — cost_ledger column schema (line 64)](../../backend/store/database.py)
- [`backend/store/project_store.py` — JSONB atomic UPDATE idiom](../../backend/store/project_store.py)
- [`backend/api/sse.py` — `publish_event` signature](../../backend/api/sse.py)
- [`agents/supervisor_agent.py` — `execute` and `_execute_ticket`](../../agents/supervisor_agent.py)
- [`agents/context7_grounding.py` line 53 — LLM ainvoke site](../../agents/context7_grounding.py)
- [`_bmad-output/project-context.md` — Gemini list-content guard, env var rules](../project-context.md)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (GitHub Copilot)

### Debug Log References

- `pytest tests/ -q` → 151 passed, 6 pre-existing warnings, 0.60s. No new warnings introduced by Story 6.1 code.

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created.
- New module `agents/token_tracker.py` implements the recorder with `CURRENT_PROJECT_ID` / `CURRENT_SESSION_ID` ContextVars, `_SESSION_TOTALS`, `compute_cost_usd`, `_extract_tokens_from_result`, `record_llm_call`, `tracked_ainvoke`, `reset_session`. Zero imports from `agents/*` — AC-9 preserved.
- `backend/store/project_store.add_cost_ledger_entry` performs the atomic JSONB UPDATE + RETURNING per AC-4; unknown project returns `{}` and logs a warning (never raises).
- Six LLM `.ainvoke` sites migrated to `tracked_ainvoke`: `context7_grounding.py:53`, `developer_agent.py` (both `implement_feature` and `implement_pr_recommendations`), `local_developer_agent.py` (both methods), and `main_agent.py` router turn. MCP tool `.ainvoke` calls (`resolve_tool`, `docs_tool`) intentionally NOT wrapped.
- `SupervisorAgent.run_tickets` sets both ContextVars and calls `reset_session(session_id)` as its first action before any downstream logic. Story spec text references `execute(...)` but the actual method name at baseline is `run_tickets` — wiring applied to that method; behaviour identical because both are the ticket-run entry point.
- `main_agent.SupervisorAgent.process_chat` now accepts an optional `project_id: str | None = None`; when the CLI (no project context) calls it, tracking short-circuits gracefully via `record_llm_call`'s `no_project_id` guard. `self._chat_session_id` lazily initialised on first turn per AC-5.
- `tests/conftest.py` created with autouse fixture resetting both ContextVars and `_SESSION_TOTALS` between tests (AC-8 leakage guard, Task 6.3).
- SSE `token_update` payload keys are exactly `{session_tokens, session_cost_usd, total_tokens, total_cost_usd}` per AC-6; guarded by try/except so plumbing failures never break the LLM path.

### File List

New:
- `agents/token_tracker.py`
- `tests/conftest.py`
- `tests/test_token_tracker_extraction.py`
- `tests/test_token_tracker_cost.py`
- `tests/test_add_cost_ledger_entry.py`
- `tests/test_token_tracker_record.py`
- `tests/test_token_tracker_persistence.py`
- `tests/test_supervisor_token_tracking.py`

Modified:
- `agents/supervisor_agent.py` — added `import uuid`, `from agents import token_tracker`; wired ContextVars + `reset_session` at top of `run_tickets`.
- `agents/main_agent.py` — added `import uuid`, `from agents import token_tracker`, `from agents.token_tracker import tracked_ainvoke`; added `self._chat_session_id`; broadened `process_chat` signature with optional `project_id`; wired ContextVars at top of `process_chat`; migrated router `router_agent.ainvoke` → `tracked_ainvoke`.
- `agents/context7_grounding.py` — added `from agents.token_tracker import tracked_ainvoke`; migrated `llm.ainvoke(prompt)` → `tracked_ainvoke(llm, prompt)`.
- `agents/developer_agent.py` — added `from agents.token_tracker import tracked_ainvoke`; migrated both `agent_executor.ainvoke(...)` sites.
- `agents/local_developer_agent.py` — added `from agents.token_tracker import tracked_ainvoke`; migrated both `agent_executor.ainvoke(...)` sites.
- `backend/store/project_store.py` — added `logging` import + module logger; added `add_cost_ledger_entry` after `overwrite_ticket_history`.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status transition ready-for-dev → in-progress → review.

## Change Log

| Date       | Change                                                                                | Author |
|------------|---------------------------------------------------------------------------------------|--------|
| 2026-09-01 | Implemented Story 6.1: token tracker module, ledger update, six ainvoke migrations, SSE token_update event, supervisor + chat ContextVar wiring, seven new test modules + autouse ContextVar reset fixture. All 151 tests pass. | Dev Agent |

