---
baseline_commit: b873c0bec72ac891aa89d1b0fcf39a979992fbc7
---
# Story 5.2: SupervisorAgent Wired to Backend & Project Store

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want `SupervisorAgent` to receive ticket context from the project store and delegate to the appropriate sub-agent, publishing progress events to the SSE stream as it works,
So that the frontend can display live execution state and the agent hierarchy is correctly maintained.

## Acceptance Criteria

1. **Given** execution begins for a ticket
   **When** `SupervisorAgent` is invoked
   **Then** it loads the ticket record and current project state from PostgreSQL via the project store access layer
2. **And** it delegates implementation to `LocalDeveloperAgent` (if `AGENT_MODE=local`) or `RemoteDeveloperAgent` (if `AGENT_MODE=remote`)
3. **And** no sub-agent calls another sub-agent directly — all coordination flows through `SupervisorAgent`
4. **And** after each meaningful action, `publish_event(project_id, "agent_log", message)` is called so the Chat View receives it via SSE
5. **And** all agent invocations use `await agent_executor.ainvoke(...)` — no synchronous calls

## Developer Context

### Technical Requirements
- Implement the `SupervisorAgent` to act as the primary orchestrator.
- Integrate project store access layer to retrieve ticket and project state context from PostgreSQL.
- Handle environmental routing based on `AGENT_MODE` environment variable (`local` vs `remote` defaults).
- Wire in `publish_event` mechanism to stream log output to the SSE endpoint.

### Architecture Compliance
- **Hierarchy Rules**: `SupervisorAgent` is the only component allowed to invoke `EnvironmentAgent`, `LocalDeveloperAgent`, `RemoteDeveloperAgent`, and `TesterAgent`. Sub-agents MUST NOT call each other directly.
- **Async Invocation**: All agent executions must use `await agent_executor.ainvoke({"messages": [("user", prompt)]})`.
- **Environment**: Load configurations exclusively from `os.environ.get(...)` (e.g. `AGENT_MODE`).

### Testing Requirements
- Provide unit tests verifying the routing behavior of `AGENT_MODE` mapping to the correct developer sub-agent.
- Verify that `publish_event` is called asynchronously without blocking the execution loop.

## Previous Story Intelligence
- Story 5.1 established the global execution lock mechanism in `execute.py`. Ensure that `SupervisorAgent` respects and fits correctly inside the locked execution loop established by the previous backend endpoints.
- `asyncio.Lock` and other async mechanisms are standard in the backend layer.

## Project Context Reference
- Consult `project-context.md` for dual-mode development rules and LangGraph invocation formats.
- All new agent logic belongs in `agents/` and must be registered as a sub-agent in `SupervisorAgent.__init__()`.

## Tasks/Subtasks

- [x] 1. Scaffold `SupervisorAgent` class in `agents/supervisor_agent.py` and register sub-agents
- [x] 2. Integrate project store access layer to retrieve ticket and project state in `SupervisorAgent`
- [x] 3. Implement `publish_event` mechanism to stream log output to the SSE endpoint
- [x] 4. Implement environmental routing to delegate to `LocalDeveloperAgent` or `RemoteDeveloperAgent` based on `AGENT_MODE`
- [x] 5. Write unit tests for `AGENT_MODE` routing and `publish_event` async behavior
- [x] 6. Ensure `SupervisorAgent` is integrated correctly into the backend execution loop (Story 5.1 context)

## Dev Notes
- Remember `SupervisorAgent` is the root node of the agent hierarchy.

## Dev Agent Record

### Debug Log

- Sub-agent constructors call `ChatGoogleGenerativeAI` at init time, which fails without credentials. Fixed by patching constructors in `_make_supervisor()` test helper rather than post-init attribute replacement.

### Completion Notes

- Created `agents/supervisor_agent.py` — a clean backend-facing `SupervisorAgent` separated from the chat-interactive `main_agent.py`. It loads project/ticket context from `project_store.get_project()`, delegates to the correct developer sub-agent based on `AGENT_MODE`, calls `publish_event()` after each meaningful action (load, env setup, delegate, complete), and updates ticket status to "In Review" on success.
- Replaced the stub in `backend/api/routes/execute.py` with a real `SupervisorAgent().run_tickets()` call, still inside the existing global execution lock from Story 5.1.
- Created `tests/test_supervisor_agent.py` with 16 unit tests covering: AGENT_MODE routing (local/remote/default), publish_event call count and arguments, error guard paths (project not found, ticket not found, env failure, dev failure), success result structure, multi-ticket execution, and agent hierarchy enforcement via source inspection.
- All 16 tests pass (`pytest tests/test_supervisor_agent.py -v`).

## File List

- `agents/supervisor_agent.py` [NEW]
- `backend/api/routes/execute.py` [MODIFIED]
- `tests/test_supervisor_agent.py` [NEW]

## Change Log

- 2026-08-31: Implemented Story 5.2 — SupervisorAgent wired to backend project store and SSE. Created supervisor_agent.py, updated execute.py stub, added 16 passing unit tests.

## Status Update Notes
Ultimate context engine analysis completed - comprehensive developer guide created.
