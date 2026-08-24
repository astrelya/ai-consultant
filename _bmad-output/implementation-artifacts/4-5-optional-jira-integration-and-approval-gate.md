# Story 4.5: Optional Jira Integration and Approval Gate

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want ticket status transitions synced to Jira when configured, and an approval gate in the Chat View before execution begins,
So that my Jira board stays current and I retain explicit control before the agent team starts writing code.

## Acceptance Criteria

1. **Given** `JIRA_URL`, `JIRA_USER`, and `JIRA_API_TOKEN` are set in `.env`
   **When** tickets are accepted
   **Then** each ticket is created in Jira via the Jira MCP (through MCPManager) — not via direct HTTP calls
   **And** as each ticket transitions state (`In Progress`, `Done`, `Error`), the corresponding Jira issue is updated within the same interaction cycle

2. **Given** Jira is configured and tickets are accepted
   **When** the ticket card view is displayed
   **Then** an Approve & Begin button is visible and execution does not start until it is clicked
   **And** clicking Approve & Begin calls `POST /projects/{id}/execute` directly — no LLM call

3. **Given** Jira is not configured
   **When** tickets are accepted
   **Then** no approval gate is shown — execution can proceed immediately after ticket selection
   **And** no Jira API calls are attempted — the workflow is identical to the Jira path minus sync

## Tasks / Subtasks

- [ ] Task 1: Check Jira Configuration and Update UI (AC: 2, 3)
  - [ ] On the backend, expose whether Jira is configured (via `env` or an endpoint) so the frontend knows if it should display the approval gate.
  - [ ] On the frontend, if Jira is configured, render an "Approve & Begin" button that must be clicked before starting execution.
  - [ ] If Jira is not configured, either show a standard "Begin" button or proceed immediately after selection (as per AC 3).
- [ ] Task 2: Create Jira Issues on Acceptance (AC: 1)
  - [ ] When tickets are accepted (or when "Approve & Begin" is clicked), intercept or handle the backend action to create corresponding Jira issues.
  - [ ] Ensure the Jira issues are created via Jira MCP (through `MCPManager`), not direct HTTP.
- [ ] Task 3: Sync Ticket Status Transitions to Jira (AC: 1)
  - [ ] In the ticket state machine (where statuses change to `In Progress`, `Done`, `Error`), check if Jira is configured.
  - [ ] If configured, use Jira MCP to update the corresponding Jira issue status.
- [ ] Task 4: Ensure LLM-Free Path (AC: 2)
  - [ ] Verify that clicking "Approve & Begin" calls `POST /projects/{id}/execute` directly with no LLM involvement.

## Dev Notes

### Backend: MCPManager Integration
- Use `MCPManager.get_instance()` to access the Jira MCP tools.
- Do not instantiate a new connection for each update; the MCP is a singleton.
- Only attempt Jira sync if `JIRA_URL`, `JIRA_USER`, and `JIRA_API_TOKEN` are available in `os.environ`. Check this gracefully so the system doesn't crash if Jira is omitted.

### Frontend: Approval Gate
- The Approval Gate is a UX hurdle for Jira users to ensure they've confirmed the sync before execution starts.
- Make the backend state of Jira configuration accessible to the frontend, perhaps as a flag on the `GET /projects/{id}` or a dedicated config endpoint.

### Architectural Constraints (Non-Negotiable)
- **AD-3 (MCPManager singleton):** Ensure Jira operations go through `MCPManager`.
- **AD-4 (LLM-as-last-resort):** The "Approve & Begin" button calls the backend directly.
- **AD-10 (Frontend-backend boundary):** The frontend relies on the backend to tell it whether Jira is configured, rather than checking env vars itself.

## Previous Story Intelligence (4.4 Context)
- Story 4.4 implemented selection and topological sorting. The Approval Gate will sit at the end of this flow—after tickets are checked and sorted, the user must approve (if Jira is on) to start the `POST /projects/{id}/execute`.

## Git Intelligence
- Recent commits indicate Jira MCP was recently added (`7a50f41 feat: add actual Jira MCP`). You should be able to leverage existing Jira MCP tools.

## Project Context Reference
- **Framework Rules:** FastApi backend, Next.js frontend.
- **Environment Rules:** Use `os.environ.get("KEY")` to check for Jira config.

## References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.5]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md]
- [Source: _bmad-output/project-context.md]

## Dev Agent Record
### Agent Model Used
Gemini 3.1 Pro (Low)
### Debug Log References
None
### Completion Notes List
Ultimate context engine analysis completed - comprehensive developer guide created.
### File List
- _bmad-output/implementation-artifacts/4-5-optional-jira-integration-and-approval-gate.md
