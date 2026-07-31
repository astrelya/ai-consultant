---
id: SPEC-spec-driven-dev-app
companions:
  - _bmad-output/project-context.md
sources:
  - _bmad-output/brainstorming/brainstorm-spec-driven-dev-app-2026-07-08/brainstorm-intent.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability only — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Spec-Driven AI Development Team Simulator

## Why

Solo developers and team contributors want to delegate implementation work to a coordinated AI agent team while retaining PM-level control. Current AI coding tools are stateless (no cross-session memory), opaque (no live reasoning trace), and isolated (no shared context across tickets), making them untrustworthy for any multi-ticket project. The opportunity: with spec-as-contract entry, agent specialization, and persistent memory, an AI dev team can execute tickets sequentially with accumulated codebase knowledge — making autonomous development trustworthy, transparent, and exception-driven rather than black-box.

## Capabilities

- **CAP-1**
  - **intent:** User provides a spec and engages a clarifying dialogue; the system produces a structured set of user stories and Jira tickets with project name embedded in ticket titles; tickets are written to Jira via MCP and can also be read from an existing Jira backlog.
  - **success:** Given a spec input, the system outputs a complete, PM-reviewable ticket set in Jira; the user can read, create, update status, and manage sprints through the same MCP integration without leaving the app.

- **CAP-2**
  - **intent:** Agents implement tickets one at a time, each with access to accumulated codebase context and all prior ticket outcomes.
  - **success:** No ticket is implemented without awareness of prior ticket context; parallel execution never occurs; no merge conflicts from agent concurrency.

- **CAP-3**
  - **intent:** A live thought log streams agent reasoning to the UI in real time throughout every execution phase.
  - **success:** User can read every reasoning step as it happens; no silent gap exceeds what is expected for a single operation; execution never ends with only a bare "success" message.

- **CAP-4**
  - **intent:** Project configuration, codebase knowledge, prior decisions, and ticket history persist across agents and across sessions.
  - **success:** A second session opens with full project knowledge intact; no information provided in a prior session is re-requested; new agents inherit accumulated context without re-discovery.

- **CAP-5**
  - **intent:** When an agent is uncertain about how to proceed, it pauses and surfaces a structured question to the user via the chat interface; the user answers in chat and the agent resumes.
  - **success:** No agent proceeds blindly past a genuine ambiguity; every agent question contains enough context for the user to give a concrete answer; chat responses unblock the agent without requiring a full new generation cycle.

- **CAP-6**
  - **intent:** No ticket is marked complete without actual test execution and a linked verifiable test artifact; regressions caught pre-merge are handled autonomously by the agent; regressions or merge conflicts that surface post-merge are escalated to the user.
  - **success:** Ghost validation is a hard system failure detectable at infrastructure level; every closed ticket has an associated test artifact; a pre-merge regression is fixed before merge without user intervention; a post-merge regression or merge conflict produces a user-actionable exception.

- **CAP-7**
  - **intent:** The UI presents as a lightweight PM dashboard — live activity stream, progressive disclosure (summary default, drill-down on demand), and PM-style controls (approve, reject, intervene, re-run).
  - **success:** A non-technical PM can operate the full workflow — from spec entry through ticket closure — without CLI access or code knowledge.

- **CAP-8**
  - **intent:** All code generation is actively grounded against current library and framework documentation via Context7 before output.
  - **success:** No generated code references hallucinated APIs or patterns deprecated in the current version of the target library or framework.

- **CAP-9**
  - **intent:** Two UI views are available in the same session via an in-session toggle — a dev view (IDE-like workspace file tree with real-time code stream, available in local mode only) and a PM/user view (chat, execution status, elapsed time, and key execution signals); switching views does not interrupt agent execution.
  - **success:** A developer and a non-technical stakeholder can each use the view suited to them in the same session; the PM view never requires code literacy to interpret; toggling between views is immediate and non-destructive.

- **CAP-10**
  - **intent:** Milestone approval gates are configurable; ticket creation is a mandatory default gate; at each gate the user can approve, reject, or edit the artifact in a simple text area without triggering a new LLM call; user cannot edit generated code directly — code changes are requested through chat.
  - **success:** User modifies a ticket title, description, or acceptance criterion in the text area and confirms; the change takes effect without an additional generation round-trip; no code editor is exposed in the approval UI.

- **CAP-11**
  - **intent:** In local development mode the agent clones the target branch into a workspace folder; the UI presents a live file tree of that workspace so the user can see files being created, modified, or deleted as the agent works.
  - **success:** User can open any file in the workspace view and read its current state in real time while the agent is actively editing it; the workspace view reflects changes within the same interaction cycle as the agent's write.

- **CAP-12**
  - **intent:** In remote development mode the agent manages code via GitHub MCP without a local clone; the UI shows execution logs only — no file tree is presented.
  - **success:** Agent completes a ticket in remote mode using GitHub MCP and the user can follow all progress through the log stream alone; no local file system access is required.

## Constraints

- Tickets execute sequentially, never in parallel — parallel execution causes merge conflicts and context isolation failures.
- No ticket may be marked complete without actual test execution and a verifiable artifact; ghost validation is a hard failure.
- Pre-merge regressions are handled autonomously by the agent; post-merge regressions and merge conflicts are surfaced to the user as exceptions.
- Project configuration is captured once and persists for the project lifetime — never re-requested within the same project.
- The interface must be operable without technical depth; all complexity is opt-in.
- All code generation must be grounded via Context7 against current library and framework docs before output.
- No agent uncertainty or failure may be silent — every such state surfaces to the user via the chat interface.
- User cannot edit generated code directly in the UI; all code change requests go through chat.
- All agent logic must be implemented using BMad framework patterns and conventions — governs agent structure, tool definitions, and orchestration.

## Non-goals

- Parallel ticket execution.
- Full zero-interaction autonomy (exception-driven human intervention is a feature, not a failure).
- Stateless, per-session agents with no persistent memory.
- UI that surfaces all information at once (information overload is an explicit failure mode).
- Re-asking for project configuration already provided in any prior session.
- Direct code editing in the UI — the agent owns code; the user owns direction via chat.

## Success signal

A solo developer provides a spec, edits the generated Jira tickets in the approval text area, then steps away while the agent team implements and tests each ticket sequentially — with pre-merge regressions caught and fixed autonomously, live logs visible throughout, and the dev-view file tree reflecting every change in real time. The user intervenes only when the agent surfaces a question in chat or a post-merge exception. The session ends with a committed, test-verified implementation the user did not write line by line.

## Assumptions

- Python + LangGraph is the implementation stack (derived from `project-context.md`).

## Open Questions

- **Agent uncertainty model:** the original design included a configurable "confidence threshold" per agent and ticket type — agents would pause below a numeric threshold. User questioned this concept. Decision needed: keep as-is, simplify to a non-configurable "agent pauses whenever it is genuinely uncertain" model, or drop the concept entirely?
