# Story 5.2: SupervisorAgent Wired to Backend & Project Store

Status: ready-for-dev

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

## Completion Notes
Ultimate context engine analysis completed - comprehensive developer guide created.
