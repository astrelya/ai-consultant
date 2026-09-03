---
baseline_commit: b873c0bec72ac891aa89d1b0fcf39a979992fbc7
---

# Story 5.5: Context7 Grounding Before Code Generation

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want every code generation step in a developer agent to be preceded by a Context7 MCP query for the target library,
so that all generated code conforms to the current documented API and never references deprecated or hallucinated APIs.

## Acceptance Criteria

1. **Given** a developer agent (`LocalDeveloperAgent` or `RemoteDeveloperAgent`) is about to generate code for a ticket
   **When** `implement_feature()` or `implement_pr_recommendations()` is entered
   **Then** a Context7 MCP query is issued for every target library identified for that ticket **before** the ReAct system prompt is assembled and passed to `create_react_agent(...).ainvoke(...)`.

2. **And** the aggregated Context7 response text (library id + docs snippet, truncated per limits below) is included verbatim in the code-generation prompt under a clearly delimited `--- Context7 Grounding ---` section.

3. **And** skipping the Context7 query for **any** reason is a hard violation: if no library can be identified **or** every Context7 call fails/returns empty, `implement_feature()` / `implement_pr_recommendations()` raise `Context7GroundingError` and **must not** proceed to the code-generation `ainvoke`. `SupervisorAgent` catches this as a normal development failure and marks the ticket `Failed` (existing 5.2 path).

4. **And** every Context7 MCP tool invocation uses `await` (AD-9). No sync fallback anywhere on the grounding path.

5. **And** an SSE `agent_log` event of the form `{"message": "Querying Context7 for <library>…"}` is published via `backend.api.sse.publish_event(project_id, "agent_log", {...})` **before** each per-library Context7 call so the Chat View shows grounding in action live. When grounding fails, an additional `agent_log` event `"Context7 grounding failed for <library>: <reason>"` is published before the exception surfaces.

## Tasks / Subtasks

- [x] 1. Create the grounding helper module `agents/context7_grounding.py` (AC: 1, 2, 3, 4, 5)
  - [x] 1.1 Define `class Context7GroundingError(RuntimeError)` — dedicated exception so `SupervisorAgent._delegate_to_developer` can distinguish grounding failures in logs if desired later.
  - [x] 1.2 Define `async def ground_with_context7(story_details: dict, project_id: str | None) -> str` returning the grounding preamble string (empty string is NEVER a valid successful return — see 1.6).
  - [x] 1.3 Inside the helper:
    - [x] 1.3.1 Call `await MCPManager.get_instance()` (AD-3). Never construct a fresh `MCPManager`. Never call `load_context7_mcp_tools()` directly from this module.
    - [x] 1.3.2 Read `manager.doc_tools`. If the list is empty (Context7 subprocess failed to start, `CONTEXT7_API_KEY` missing, npx unavailable, etc.), raise `Context7GroundingError("Context7 MCP unavailable — CONTEXT7_API_KEY missing or MCP subprocess failed to start")` immediately. Do NOT silently pass — AD-8 forbids it.
    - [x] 1.3.3 Locate the two tools we need by `.name` (exact strings exposed by the `@upstash/context7-mcp` npm package): `resolve-library-id` and `get-library-docs`. If either is missing, raise `Context7GroundingError` with a message naming the missing tool.
  - [x] 1.4 Determine target libraries via `_infer_target_libraries(story_details) -> list[str]`:
    - [x] 1.4.1 Pure-Python heuristic (AD-4 — LLM-as-last-resort): scan `story_details["title"]`, `story_details["description"]`, and `story_details.get("accumulated_context", "")` for **any** case-insensitive substring match against the whitelist derived from env var `CONTEXT7_LIBRARY_WHITELIST` (comma-separated, e.g. `fastapi,react,next.js,langgraph,langchain,pytest,asyncpg,tailwindcss`). Default value when the env var is unset MUST be exactly: `fastapi,langgraph,langchain,pytest,asyncpg,react,next.js,tailwindcss`.
    - [x] 1.4.2 Deduplicate preserving order-of-first-appearance in the text (stable order → reproducible prompts → easier eyeballing in tests).
    - [x] 1.4.3 Cap at `CONTEXT7_MAX_LIBRARIES` env var (int, default `3`) to bound MCP round-trips per ticket.
    - [x] 1.4.4 If the heuristic yields zero hits, fall back to a single `ChatGoogleGenerativeAI(model=os.environ.get("TICKET_MODEL", "gemini-2.5-flash"), temperature=0).ainvoke(...)` call that returns a comma-separated list of library names (parse defensively, strip empties, cap at the same limit). This is the ONLY LLM call allowed on the grounding path. Guard for Gemini's list-content return per project-context.md ("`langchain-google-genai` Gemini responses may return content as a list of dicts").
    - [x] 1.4.5 If both the heuristic and the fallback return an empty list, raise `Context7GroundingError("Could not identify any target library for grounding")`.
  - [x] 1.5 For each library (in order):
    - [x] 1.5.1 `await publish_event(project_id, "agent_log", {"message": f"Querying Context7 for {library}…"})` — but only if `project_id` is truthy. Skipping publish when `project_id is None` keeps the helper usable from CLI paths (`main.py` interactive mode) without SSE.
    - [x] 1.5.2 `resolved = await resolve_tool.ainvoke({"libraryName": library})` — arg name matches the Upstash MCP schema. Wrap in `try/except Exception as e` and, on failure, publish `agent_log` `"Context7 grounding failed for {library}: {e}"` (only if `project_id`), append `(library, None, str(e))` to a `failures` list, and continue to next library.
    - [x] 1.5.3 Parse the resolved id: the Upstash MCP returns a JSON-in-string payload; extract the first `/org/project` style id via a tolerant scan (`re.search(r"[a-zA-Z0-9._-]+/[a-zA-Z0-9._/-]+", str(resolved))`). If nothing matches, treat as failure exactly like 1.5.2.
    - [x] 1.5.4 `docs = await docs_tool.ainvoke({"context7CompatibleLibraryID": resolved_id, "tokens": int(os.environ.get("CONTEXT7_TOKENS_PER_LIB", "2000"))})`. Same exception handling as 1.5.2.
    - [x] 1.5.5 Truncate the docs string to `CONTEXT7_MAX_CHARS_PER_LIB` (env var, default `4000`) and append `(library, resolved_id, docs_truncated)` to a `successes` list.
  - [x] 1.6 After the loop, if `successes` is empty, raise `Context7GroundingError(f"All Context7 grounding queries failed: {failures}")`. Otherwise assemble and return:
    ```
    --- Context7 Grounding ---
    [<library>] (id: <resolved_id>)
    <docs_truncated>

    [<library2>] …
    --------------------------
    ```
    with a trailing newline. This exact block is what AC-2 expects to see prepended to the developer system prompt.
  - [x] 1.7 The helper MUST be pure `async` (AC-4). No `asyncio.run`, no `run_in_executor`, no threads. Every network call is `await`-ed.

- [x] 2. Wire `LocalDeveloperAgent` to the grounding path (AC: 1, 2, 3)
  - [x] 2.1 In `agents/local_developer_agent.py`, import `from agents.context7_grounding import ground_with_context7, Context7GroundingError`.
  - [x] 2.2 In `LocalDeveloperAgent.implement_feature`, **before** the `async with load_context7_mcp_tools()` block, call:
    ```python
    grounding = await ground_with_context7(story_details, story_details.get("project_id"))
    ```
    If it raises `Context7GroundingError`, let it propagate — do NOT catch here. The Supervisor's existing "development phase failed" path (`supervisor_agent.py::_execute_ticket` handles `dev_result["status"] != "success"`); since raising bypasses the return, add a top-level `try/except Context7GroundingError as exc: return {"status": "error", "reason": "context7_grounding_failed", "message": str(exc)}` around the whole `implement_feature` body so Supervisor sees a normal error dict (AC-3 wording: "Supervisor catches this as a normal development failure"). Same treatment in `implement_pr_recommendations`.
  - [x] 2.3 Prepend the grounding block to `system_prompt`:
    ```python
    system_prompt = f"{grounding}\n{system_prompt}"
    ```
    Do NOT put grounding inside the loop of tools; it belongs in the prompt so the LLM cannot skip reading it.
  - [x] 2.4 Keep the existing `async with load_context7_mcp_tools() as doc_tools:` block untouched — the ReAct agent still gets Context7 tools for any additional on-demand lookups it wants to perform mid-generation. (Grounding does not remove tool access.) NOTE: `load_context7_mcp_tools()` opens a **new** stdio subprocess each invocation, which duplicates what `MCPManager` already keeps warm. Do NOT refactor that in this story — see "Deferred" section. This story only guarantees the pre-call grounding step; the tool-time behaviour is unchanged.
  - [x] 2.5 Apply the exact same changes to `implement_pr_recommendations` — both public methods invoke `create_react_agent(self.llm, ...).ainvoke(...)` and both must be grounded per AC-1.

- [x] 3. Wire `RemoteDeveloperAgent` to the grounding path (AC: 1, 2, 3)
  - [x] 3.1 In `agents/developer_agent.py`, import `ground_with_context7` and `Context7GroundingError`.
  - [x] 3.2 In `RemoteDeveloperAgent.implement_feature`, before `async with load_dev_tools() as tools:`, call `grounding = await ground_with_context7(story_details, story_details.get("project_id"))` and wrap the whole method body in the same `try/except Context7GroundingError` returning `{"status": "error", "reason": "context7_grounding_failed", "message": str(exc)}`.
  - [x] 3.3 Prepend the grounding block to `system_prompt` exactly like 2.3.
  - [x] 3.4 Apply the identical change to `implement_pr_recommendations`.

- [x] 4. Ensure `project_id` reaches the developer agents (AC: 5)
  - [x] 4.1 Verify `agents/supervisor_agent.py::_execute_ticket` already sets `story_details["project_id"] = project_id` (it does, at construction of `story_details` — line ~110 in the current file). No change needed, but add a defensive `assert "project_id" in story_details` inside `ground_with_context7` OR fall through to the `if project_id:` guard — the guard approach is preferred (already specified in 1.5.1).
  - [x] 4.2 If either developer agent is ever called from the interactive CLI (`main.py` / `main_agent.py`), `project_id` will be `None` and SSE publishing is silently skipped. This is intentional — the CLI path already exists for pre-backend usage and this story does not add SSE to it.

- [x] 5. Tests (AC: 1, 2, 3, 4, 5)
  - [x] 5.1 Add `tests/test_context7_grounding.py`:
    - [x] 5.1.1 `test_grounding_preamble_matches_expected_format`: mock `MCPManager.get_instance` to return an object whose `doc_tools` are two `AsyncMock`s named `resolve-library-id` and `get-library-docs`. `resolve-library-id.ainvoke` returns `"/upstash/context7-fastapi"`, `get-library-docs.ainvoke` returns `"# FastAPI\nUse `FastAPI()` …"`. Provide `story_details = {"title": "Use fastapi", "description": "add /health", "accumulated_context": ""}` and assert the returned string starts with `--- Context7 Grounding ---`, contains `[fastapi]`, contains the doc snippet, and ends with the closer. Assert both `ainvoke` calls used `await` by checking `AsyncMock.await_count == 1`.
    - [x] 5.1.2 `test_grounding_publishes_sse_event_before_each_call`: same setup + `patch("agents.context7_grounding.publish_event", new_callable=AsyncMock)`. Assert the publish call happens with `event_type="agent_log"` and `data={"message": "Querying Context7 for fastapi…"}` BEFORE the resolve tool `ainvoke` is entered (use `MagicMock.mock_calls` ordering).
    - [x] 5.1.3 `test_grounding_hard_fails_when_doc_tools_empty`: mock `MCPManager.get_instance` with `doc_tools=[]`. Assert `Context7GroundingError` raised with a message mentioning `CONTEXT7_API_KEY`.
    - [x] 5.1.4 `test_grounding_hard_fails_when_no_library_identified`: story_details with title/description containing NO whitelist match; patch the LLM fallback path so it returns an empty content string. Assert `Context7GroundingError` raised.
    - [x] 5.1.5 `test_grounding_hard_fails_when_all_libraries_fail`: whitelist hit for `fastapi`; `resolve-library-id.ainvoke` raises `Exception("boom")`. Assert `Context7GroundingError` raised AND an `agent_log` event was published with `"Context7 grounding failed for fastapi: boom"`.
    - [x] 5.1.6 `test_grounding_partial_success_returns_successful_libraries_only`: two libraries in whitelist (`fastapi`, `react`); `fastapi` resolves+docs succeed, `react` resolve raises. Assert returned string contains `[fastapi]` but not `[react]`, and no exception is raised.
    - [x] 5.1.7 `test_grounding_respects_max_libraries_env`: 5 whitelist hits, `CONTEXT7_MAX_LIBRARIES=2` (use `monkeypatch.setenv`). Assert only 2 `resolve-library-id.ainvoke` calls happen.
    - [x] 5.1.8 `test_grounding_no_publish_when_project_id_none`: `project_id=None`; patch `publish_event`; assert it was NEVER awaited.
  - [x] 5.2 Add `tests/test_local_developer_agent_grounding.py`:
    - [x] 5.2.1 `test_implement_feature_prepends_grounding_before_ainvoke`: `patch("agents.local_developer_agent.ground_with_context7", new_callable=AsyncMock, return_value="--- Context7 Grounding ---\n[fastapi]\n…\n--------------------------\n")`; patch `create_react_agent` to return an object whose `ainvoke` is `AsyncMock`; patch `load_context7_mcp_tools` to yield `[]`. Assert the prompt passed to `ainvoke` starts with the grounding block.
    - [x] 5.2.2 `test_implement_feature_returns_error_dict_on_grounding_failure`: same patches, but `ground_with_context7.side_effect = Context7GroundingError("no lib")`. Assert the return dict equals `{"status": "error", "reason": "context7_grounding_failed", "message": "no lib"}` AND `create_react_agent(...).ainvoke` was NEVER awaited (AC-3: must not proceed).
    - [x] 5.2.3 Same two cases for `implement_pr_recommendations`.
  - [x] 5.3 Add `tests/test_remote_developer_agent_grounding.py` mirroring 5.2 for `RemoteDeveloperAgent` (`patch("agents.developer_agent.ground_with_context7", …)`, `patch("agents.developer_agent.load_dev_tools", …)`).
  - [x] 5.4 Regression: run `pytest tests/ -q` and confirm the pre-existing 44 passing tests still pass. If `tests/test_ticket_card_view.py` fails, that is a pre-existing failure documented in Story 5.1 debug notes — not a regression from this story.

- [x] 6. Config surface documentation (AC: none, but required by project-context.md)
  - [x] 6.1 Update `.env.example` to add the four new optional env vars introduced by this story (with the exact defaults from Task 1) — keep them commented out so existing deployments continue to use defaults:
    ```
    # CONTEXT7_LIBRARY_WHITELIST=fastapi,langgraph,langchain,pytest,asyncpg,react,next.js,tailwindcss
    # CONTEXT7_MAX_LIBRARIES=3
    # CONTEXT7_TOKENS_PER_LIB=2000
    # CONTEXT7_MAX_CHARS_PER_LIB=4000
    ```
  - [x] 6.2 Do NOT add a new required env var — `CONTEXT7_API_KEY` remains the only required Context7 setting, and its absence continues to surface as a hard grounding failure (which is the correct AD-8 behaviour).

## Dev Notes

### What Stories 5.1–5.4 Built (Must Not Break)

- **Story 5.1** (`backend/execution_lock.py`, `backend/api/routes/execute.py`, MCPManager lifespan init in `backend/main.py`): grounding piggybacks on the fact that `await MCPManager.get_instance()` is already called at FastAPI startup — Context7 tools are warm by the time the first `execute` request arrives. **Do not** call `MCPManager.get_instance()` from anywhere else in this story.
- **Story 5.2** (`agents/supervisor_agent.py::_execute_ticket`): the Supervisor already routes `story_details["project_id"] = project_id` into the developer agents (verified line ~112 in the current file). This story consumes that value; no Supervisor-side change is required.
- **Story 5.3** (`supervisor_agent._build_accumulated_context`): the returned preamble is already prepended to `story_details["description"]`. Our library-inference heuristic can piggyback on that description text — accumulated context becomes an additional source of library mentions, which is a feature, not a bug.
- **Story 5.4** (`backend/chat/context.py::build_session_context_preamble`): session-open context is unrelated to code-generation grounding. Do not touch it. Do not merge the two preambles — they live at different lifecycle points (chat entry vs. code-gen entry) and have different truncation policies.

### Current Context7 Landscape (verified by reading the code)

- `tools/context7_mcp.py::load_context7_mcp_tools()` — async context manager that spawns `npx @upstash/context7-mcp` via stdio. Currently invoked in TWO places: (a) `MCPManager.initialize()` (long-lived, via the singleton's `AsyncExitStack`), and (b) directly inside `LocalDeveloperAgent.implement_feature` / `implement_pr_recommendations` (short-lived, per-invocation). The direct calls duplicate the singleton but are wired to give the ReAct agent tool access during generation.
- **Story 5.5 uses the singleton path exclusively for the grounding call** — this is intentional (AD-3). The pre-call grounding queries hit the warm subprocess. The in-agent tool wiring (unchanged) remains for optional mid-generation lookups. The duplicate subprocess spawn in the existing direct calls is a known inefficiency; unifying it is out of scope (see Deferred).
- The Upstash Context7 MCP exposes tools whose exact names are `resolve-library-id` (arg `libraryName: string`) and `get-library-docs` (args `context7CompatibleLibraryID: string`, optional `tokens: int`, optional `topic: string`). These names MUST be matched exactly — LangChain's MCP adapter preserves the hyphenated MCP tool names verbatim in `.name`.

### Architecture Compliance

- **AD-1 (agent hierarchy):** The grounding helper is called by developer agents themselves, not by Supervisor. Supervisor is unchanged. No sub-agent-to-sub-agent calls introduced.
- **AD-2 (sequential lock):** Grounding runs inside the already-locked ticket execution — no lock changes.
- **AD-3 (MCPManager singleton):** Grounding uses `await MCPManager.get_instance()` and reads `manager.doc_tools`. It NEVER opens a new stdio subprocess.
- **AD-4 (LLM-as-last-resort):** The library-inference heuristic runs first. The `TICKET_MODEL` fallback fires only when the heuristic returns zero hits. Grounding never uses `CODING_MODEL` — that model is reserved for the actual generation step.
- **AD-8 (Context7 grounding mandatory):** THIS STORY. The hard-violation semantics are enforced by raising `Context7GroundingError` before any `ainvoke` on the code-generation path.
- **AD-9 (async throughout):** All Context7 tool calls and `publish_event` calls are `await`-ed. No `run_in_executor`, no sync wrappers.
- **AD-13 (env vars only):** All tunables (whitelist, max libraries, per-lib token/char limits) are read via `os.environ.get(..., default)`. No hard-coded model names, no hard-coded API keys.
- **project-context.md — "Gemini responses may return content as a list":** The LLM fallback in Task 1.4.4 MUST apply the `isinstance(content, list)` guard already used elsewhere.
- **project-context.md — "MCPManager is a singleton":** Enforced by Task 1.3.1.
- **project-context.md — "load_dotenv() only at entry point":** The grounding helper reads env vars but never calls `load_dotenv()`.

### File Locations

**MODIFY:**

- `agents/local_developer_agent.py` — import grounding helper, add try/except wrapper to `implement_feature` and `implement_pr_recommendations`, prepend grounding to `system_prompt`. Keep the existing `load_context7_mcp_tools()` block intact.
- `agents/developer_agent.py` — same treatment for `RemoteDeveloperAgent.implement_feature` and `implement_pr_recommendations`.
- `.env.example` — add the four commented-out tuning env vars.

**NEW:**

- `agents/context7_grounding.py` — houses `Context7GroundingError`, `ground_with_context7`, `_infer_target_libraries`. Keep it under `agents/` (not `tools/`) because it is agent-orchestration logic — it composes MCP tool calls with SSE publishing and library inference. `tools/` is reserved for plain-Python helpers per AD-8/AD-3 conventions.
- `tests/test_context7_grounding.py`
- `tests/test_local_developer_agent_grounding.py`
- `tests/test_remote_developer_agent_grounding.py`

**DO NOT modify:**

- `tools/context7_mcp.py` — its long-lived `load_context7_mcp_tools()` context manager is already correct and used by `MCPManager.initialize()`. Refactoring the duplicate short-lived usage inside developer agents is out of scope (see Deferred).
- `tools/mcp_loader.py` — the singleton already registers Context7 in `initialize()`. No change.
- `agents/supervisor_agent.py` — Supervisor already forwards `project_id` into `story_details` (5.2 wiring). No change.
- `agents/main_agent.py` — the CLI chat-oriented Supervisor is not on the ticket-execution path.
- `backend/api/sse.py` — reuse the existing `publish_event` function verbatim.

### Reference Implementation Sketch (non-normative; developer may adapt)

```python
# agents/context7_grounding.py
import os
import re
from typing import Iterable

from langchain_google_genai import ChatGoogleGenerativeAI

from backend.api.sse import publish_event
from tools.mcp_loader import MCPManager


class Context7GroundingError(RuntimeError):
    """Raised when Context7 grounding cannot be completed. AD-8: hard violation."""


_DEFAULT_WHITELIST = "fastapi,langgraph,langchain,pytest,asyncpg,react,next.js,tailwindcss"


def _whitelist() -> list[str]:
    raw = os.environ.get("CONTEXT7_LIBRARY_WHITELIST", _DEFAULT_WHITELIST)
    return [s.strip().lower() for s in raw.split(",") if s.strip()]


def _infer_target_libraries_heuristic(text: str) -> list[str]:
    text_lower = text.lower()
    hits: list[str] = []
    for lib in _whitelist():
        if lib in text_lower and lib not in hits:
            hits.append(lib)
    return hits


async def _infer_target_libraries_llm(text: str) -> list[str]:
    # AD-4 last resort. Small, deterministic call.
    llm = ChatGoogleGenerativeAI(
        model=os.environ.get("TICKET_MODEL", "gemini-2.5-flash"), temperature=0
    )
    prompt = (
        "List up to 3 open-source libraries or frameworks that the following "
        "ticket description is most likely to touch. Return ONLY a comma-separated "
        "list of lowercase names, no prose.\n\n"
        f"{text}"
    )
    result = await llm.ainvoke(prompt)
    content = result.content
    if isinstance(content, list):
        content = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return [s.strip().lower() for s in str(content).split(",") if s.strip()]


async def _infer_target_libraries(story_details: dict) -> list[str]:
    text = " ".join(
        str(story_details.get(k, ""))
        for k in ("title", "description", "accumulated_context")
    )
    hits = _infer_target_libraries_heuristic(text)
    if not hits:
        hits = await _infer_target_libraries_llm(text)
    max_libs = int(os.environ.get("CONTEXT7_MAX_LIBRARIES", "3"))
    return hits[:max_libs]


def _find_tool(tools: Iterable, name: str):
    for t in tools:
        if getattr(t, "name", None) == name:
            return t
    return None


async def ground_with_context7(story_details: dict, project_id: str | None) -> str:
    manager = await MCPManager.get_instance()
    doc_tools = getattr(manager, "doc_tools", []) or []
    if not doc_tools:
        raise Context7GroundingError(
            "Context7 MCP unavailable — CONTEXT7_API_KEY missing or MCP subprocess failed to start"
        )

    resolve_tool = _find_tool(doc_tools, "resolve-library-id")
    docs_tool = _find_tool(doc_tools, "get-library-docs")
    if resolve_tool is None or docs_tool is None:
        missing = "resolve-library-id" if resolve_tool is None else "get-library-docs"
        raise Context7GroundingError(f"Context7 MCP missing required tool: {missing}")

    libraries = await _infer_target_libraries(story_details)
    if not libraries:
        raise Context7GroundingError("Could not identify any target library for grounding")

    max_chars = int(os.environ.get("CONTEXT7_MAX_CHARS_PER_LIB", "4000"))
    tokens = int(os.environ.get("CONTEXT7_TOKENS_PER_LIB", "2000"))

    successes: list[tuple[str, str, str]] = []
    failures: list[tuple[str, str]] = []

    for lib in libraries:
        if project_id:
            await publish_event(project_id, "agent_log", {"message": f"Querying Context7 for {lib}…"})
        try:
            resolved_raw = await resolve_tool.ainvoke({"libraryName": lib})
            match = re.search(r"[a-zA-Z0-9._-]+/[a-zA-Z0-9._/-]+", str(resolved_raw))
            if not match:
                raise ValueError(f"could not parse resolved id from: {resolved_raw!r:.200}")
            resolved_id = match.group(0)
            docs_raw = await docs_tool.ainvoke(
                {"context7CompatibleLibraryID": resolved_id, "tokens": tokens}
            )
            docs = str(docs_raw)[:max_chars]
            successes.append((lib, resolved_id, docs))
        except Exception as exc:  # noqa: BLE001
            failures.append((lib, str(exc)))
            if project_id:
                await publish_event(
                    project_id, "agent_log",
                    {"message": f"Context7 grounding failed for {lib}: {exc}"},
                )

    if not successes:
        raise Context7GroundingError(f"All Context7 grounding queries failed: {failures}")

    blocks = [f"[{lib}] (id: {rid})\n{docs}" for lib, rid, docs in successes]
    return "--- Context7 Grounding ---\n" + "\n\n".join(blocks) + "\n--------------------------\n"
```

The developer agents then look like:

```python
# agents/local_developer_agent.py — inside implement_feature
try:
    grounding = await ground_with_context7(story_details, story_details.get("project_id"))
except Context7GroundingError as exc:
    return {"status": "error", "reason": "context7_grounding_failed", "message": str(exc)}

system_prompt = f"{grounding}\n{system_prompt}"

async with load_context7_mcp_tools() as doc_tools:
    # unchanged from here on
    ...
```

### Edge Cases the Dev Agent Must Handle

- **Context7 tool returns non-string:** LangChain-MCP tools sometimes wrap payloads in `TextContent` objects. Coerce via `str(...)` — the regex tolerates surrounding noise.
- **`resolve-library-id` returns multiple candidate ids:** The regex picks the first `/org/project` match. This is deterministic and adequate — the Upstash docs endpoint accepts the first match reliably for whitelist entries. Do not over-engineer selection logic in this story.
- **`get-library-docs` returns empty string:** Truncation of empty string is empty. Still counts as a "success" per the current spec (a returned response means Context7 was queried, satisfying AD-8). If we later observe empty-doc hits confusing the LLM, tighten in a follow-up story — do NOT add heuristics here.
- **Tool call latency:** The two per-library round-trips add ~1–3 s per library. Capping at `CONTEXT7_MAX_LIBRARIES=3` keeps worst-case grounding at ~10 s per ticket, well within the ticket-execution budget.
- **Non-ASCII in library names:** Whitelist is ASCII by default; the substring scan is `text.lower() → substring in text_lower`, safe for the mixed-case content of ticket descriptions.
- **`project_id` is a UUID object, not a string:** The Supervisor sets `story_details["project_id"] = project_id` where `project_id` is a str-cast UUID at the endpoint boundary (`execute.py`). `publish_event` expects `project_id: str` — pass through as-is; if the value is a `uuid.UUID`, cast inside `ground_with_context7` (`str(project_id)`) before the publish call.
- **Two developer agents share the singleton — no race:** MCP tool invocations are serialised by the single execution lock (AD-2), so concurrent Context7 calls cannot happen. No locking needed inside the helper.
- **`load_context7_mcp_tools()` inside `LocalDeveloperAgent` still runs post-grounding:** This is intentional (tool access during generation). It IS wasteful (duplicate subprocess) but out of scope — see Deferred.

### Deferred (Do NOT do in this story)

1. Unify the two Context7 entry paths (singleton pre-call grounding + short-lived tool access during ReAct). Requires broader refactor of `load_dev_tools` and `LocalDeveloperAgent`'s tool wiring. Track as a tech-debt note in the retrospective, not this story.
2. Enrich grounding by cross-referencing `story_details["accumulated_context"]` for library versions already installed in the workspace. Belongs to a future "smart grounding" story.
3. Cache grounding results per `(library, ticket_id)` to skip repeated identical MCP calls across sub-steps. Not needed at MVP scale.
4. Add SSE events for `"Context7 grounding complete for <library>"` on success — the "Querying" pre-event is sufficient for UX-Story feedback and matches the exact epic wording.

### References

- Story 5.5 acceptance criteria: [_bmad-output/planning-artifacts/epics.md](_bmad-output/planning-artifacts/epics.md#L575-L590)
- FR-14 Context7 Grounding: [_bmad-output/planning-artifacts/epics.md](_bmad-output/planning-artifacts/epics.md#L32)
- NFR-9 Context7 grounding mandatory: [_bmad-output/planning-artifacts/epics.md](_bmad-output/planning-artifacts/epics.md#L56)
- AD-8 (grounding mandatory) and AD-3 (MCPManager singleton), AD-4, AD-9, AD-13: [_bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md](_bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md#L112)
- UX chat log expectation ("Querying Context7 for fastapi…"): [_bmad-output/planning-artifacts/ux-designs/ux-ai-consultant-2026-07-09/EXPERIENCE.md](_bmad-output/planning-artifacts/ux-designs/ux-ai-consultant-2026-07-09/EXPERIENCE.md#L288)
- MCPManager singleton (get_instance + doc_tools attribute): [tools/mcp_loader.py](tools/mcp_loader.py#L11-L60)
- Context7 MCP loader (never call directly from grounding path): [tools/context7_mcp.py](tools/context7_mcp.py#L11-L39)
- LocalDeveloperAgent (both public methods must be grounded): [agents/local_developer_agent.py](agents/local_developer_agent.py#L45-L140)
- RemoteDeveloperAgent (both public methods must be grounded): [agents/developer_agent.py](agents/developer_agent.py#L11-L113)
- SupervisorAgent story_details construction (project_id already forwarded): [agents/supervisor_agent.py](agents/supervisor_agent.py#L107-L120)
- SSE publish_event signature: [backend/api/sse.py](backend/api/sse.py#L29)
- Project rules — Gemini list-content guard, async-only, env vars: [_bmad-output/project-context.md](_bmad-output/project-context.md)
- Story 5.1 (MCPManager lifespan init, execute route): [_bmad-output/implementation-artifacts/5-1-backend-execution-endpoint-and-sequential-lock.md](_bmad-output/implementation-artifacts/5-1-backend-execution-endpoint-and-sequential-lock.md)
- Story 5.2 (Supervisor sets project_id in story_details): [_bmad-output/implementation-artifacts/5-2-supervisoragent-wired-to-backend-and-project-store.md](_bmad-output/implementation-artifacts/5-2-supervisoragent-wired-to-backend-and-project-store.md)

### Project Structure Notes

Aligned with the existing structure — the new grounding module lives in `agents/` alongside its callers (both developer agents), new tests mirror the `test_<subject>_<facet>.py` naming already used (`test_project_store_chat.py`, `test_session_context_preamble.py`). No new top-level directories are introduced. No changes to `frontend/` are required — Story 6.2 will handle the visual surfacing of the `agent_log` events; this story only produces them.

## Dev Agent Record

### Agent Model Used

GitHub Copilot (Claude Opus 4.7) via bmad-dev-story skill.

### Debug Log References

- `pytest tests/ -q` baseline: 44 passed (pre-Story 5.5).
- `pytest tests/ -q` post-implementation: 60 passed (44 baseline + 16 new grounding tests).
- One test iteration adjusted: `test_grounding_preamble_matches_expected_format` initially asserted the resolved id kept a leading `/`, but the tolerant regex specified in Task 1.5.3 (`[a-zA-Z0-9._-]+/[a-zA-Z0-9._/-]+`) does not capture the leading `/`. The assertion was updated to `[fastapi] (id: upstash/context7-fastapi)` to match the spec-driven regex behaviour.

### Completion Notes List

- Added `agents/context7_grounding.py` exporting `Context7GroundingError` and `async ground_with_context7(story_details, project_id)`. Uses `MCPManager.get_instance()` singleton (AD-3), pure `await` (AD-9), heuristic-first library inference with LLM fallback (AD-4), env-var tunables (AD-13).
- Hard-fails with `Context7GroundingError` when: `doc_tools` empty, required MCP tool missing (`resolve-library-id` / `get-library-docs`), no library identifiable, or every per-library call fails. Partial success is preserved.
- Publishes `agent_log` SSE event `"Querying Context7 for <library>…"` before each per-library call and `"Context7 grounding failed for <library>: <reason>"` on per-library failure. Publish is skipped when `project_id` is falsy (CLI path).
- Wired `LocalDeveloperAgent.implement_feature`, `LocalDeveloperAgent.implement_pr_recommendations`, `RemoteDeveloperAgent.implement_feature`, `RemoteDeveloperAgent.implement_pr_recommendations`: each calls `ground_with_context7` before assembling the ReAct system prompt, converts `Context7GroundingError` into `{"status": "error", "reason": "context7_grounding_failed", "message": <exc>}` so `SupervisorAgent._execute_ticket` sees a normal error dict (AC-3).
- Grounding block is prepended to the system prompt in all four sites via `system_prompt = f"{grounding}\n{system_prompt}"`. Existing `load_context7_mcp_tools()` / `load_dev_tools()` blocks were left intact — mid-generation tool access is unchanged (Deferred item 1).
- Added four commented-out tuning env vars to `.env.example`. No required env var added; `CONTEXT7_API_KEY` remains the only Context7 requirement.
- New tests: `tests/test_context7_grounding.py` (8 cases), `tests/test_local_developer_agent_grounding.py` (4 cases), `tests/test_remote_developer_agent_grounding.py` (4 cases). All 16 pass; no regressions (60 total).

### File List

- `agents/context7_grounding.py` — NEW: grounding helper module.
- `agents/local_developer_agent.py` — MODIFIED: import grounding helper; wrap `implement_feature` and `implement_pr_recommendations` with grounding call + `Context7GroundingError` guard; prepend grounding block to system prompt.
- `agents/developer_agent.py` — MODIFIED: same treatment for `RemoteDeveloperAgent.implement_feature` and `implement_pr_recommendations`.
- `.env.example` — MODIFIED: added four commented-out Context7 tuning env vars.
- `tests/test_context7_grounding.py` — NEW: unit tests for `ground_with_context7` (preamble format, SSE ordering, hard-fail paths, partial success, max-libraries cap, project_id=None publish skip).
- `tests/test_local_developer_agent_grounding.py` — NEW: tests for grounding wiring in both `LocalDeveloperAgent` methods.
- `tests/test_remote_developer_agent_grounding.py` — NEW: tests for grounding wiring in both `RemoteDeveloperAgent` methods.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — MODIFIED: story `5-5-context7-grounding-before-code-generation` moved `ready-for-dev → in-progress → review`.

### Change Log

| Date       | Version | Change | Author |
| ---------- | ------- | ------ | ------ |
| 2026-08-31 | 0.1     | Story 5.5 drafted — Context7 grounding helper, developer-agent wiring, hard-violation semantics, SSE agent_log events. | GitHub Copilot |
| 2026-08-31 | 1.0     | Implemented Context7 grounding helper, wired both developer agents, added 16 tests (60 total pass), updated `.env.example`. Story ready for review. | GitHub Copilot (dev-story) |
