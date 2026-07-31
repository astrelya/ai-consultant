---
title: ai-consultant
status: draft
created: 2026-07-08
updated: 2026-07-08
---

# PRD: ai-consultant

## 0. Document Purpose

This PRD defines the requirements for ai-consultant, an open-source, project-scoped AI development team. It is structured for the developer/contributor audience: capabilities are organized as feature groups with globally-numbered functional requirements (FR-1 through FR-N). Downstream workflows — epics, stories, architecture — use these FR IDs as stable references. The companion SPEC at `_bmad-output/specs/spec-spec-driven-dev-app/SPEC.md` and the brainstorm output at `_bmad-output/brainstorming/brainstorm-spec-driven-dev-app-2026-07-08/` are source documents for traceability; this PRD is the authoritative contract.

---

## 1. Vision

ai-consultant is an open-source, project-scoped AI development team. A user names a project, describes what they want to build — even roughly — and a coordinated team of specialized agents implements it ticket by ticket, with a full memory of every prior decision, every file touched, and every outcome, across sessions. The next session opens exactly where the last one ended: no re-explaining, no re-configuring, no context re-loading.

The core problem it solves is not speed — it is continuity. Current AI coding tools are stateless: each new chat session starts blind, and a fuzzy or changing spec causes the AI to overwrite or break what already exists. ai-consultant treats each project as a named, persistent entity whose knowledge accumulates. The agents always know what has been built, which decisions were made, and why — making autonomous development safe on a living, evolving spec.

The interface is a chat-first web application (Next.js / React) with an opt-in developer file-tree view. Complexity is opt-in. A solo developer can go from a fuzzy idea to a committed, test-passing codebase without writing a single line of code.

---

## 2. Target User

### 2.1 Jobs To Be Done

- Validate a product idea quickly without spending days writing code
- Resume work on a project after days or weeks without re-explaining context to the AI
- Delegate implementation of a defined spec to an agent team while retaining PM-level control
- Catch regressions and broken builds before they reach the main branch, without manually running CI
- Follow what the agent team is doing at any moment without reading source code

### 2.2 Non-Users (v1)

- Teams requiring multi-user collaborative project access (single-user context per project in v1)
- Users seeking a hosted SaaS — self-hosted only

### 2.3 Key User Journey

**UJ-1. Alex goes from a fuzzy idea to a working project in one session.**
Alex, a solo developer with a new side-project idea, opens ai-consultant, creates a project named "my-idea," and asks to brainstorm. The app guides Alex through the BMad brainstorm pipeline, producing a structured spec document stored in the project. Alex reviews it in chat and approves it. The agents generate implementation tasks; Alex selects which ones to implement using a checkbox view. The agents execute them sequentially, logging activity in the chat in real time. Alex closes the app mid-way. The next day, Alex returns, selects the same project from the project list, and the agents resume with full context — no re-explaining required. The session ends with a committed, test-verified branch.

---

## 3. Glossary

- **Project** — A named, persistent workspace created by the user. Stores the spec, agent memory, implementation history, token usage, and all artifacts for a single development effort. Multiple Projects can exist and run concurrently.
- **Spec** — A structured specification document that describes what a Project must build. May be generated via the BMad brainstorm pipeline, refined via spec review, or provided directly by the user. Stored in both the app's Project store and the project repository.
- **Ticket** — A discrete unit of implementation work derived from the Spec. May exist only in the app (no-Jira path) or be synchronized to Jira.
- **Agent Team** — The set of specialized agents (Supervisor, Developer, Tester, Environment) that collaborate to implement Tickets sequentially.
- **Session** — A single run of the app. Agent memory persists across Sessions within the same Project.
- **Execution Queue** — The ordered list of Tickets to be implemented in the current run, resolved by dependency (blocking/blocked-by) relationships.
- **Agent Pause** — The state in which an agent determines it cannot proceed safely (genuine uncertainty about how to implement or what the user intends), halts execution, posts a structured message to chat explaining why, and waits for user input before resuming.
- **Mode** — The active workflow context within a Project: **Brainstorm** (idea exploration via BMad pipeline), **Spec Review** (validation and refinement of a provided spec), or **Implement** (agent execution). Displayed as explicit buttons in the Chat View header; the LLM may also suggest a mode switch based on conversation context.
- **Chat View** — The default interface: a hybrid of streaming chat messages and embedded structured UI components (cards, buttons, checkboxes). The primary surface for all interaction.
- **Dev View** — An opt-in view available in local mode that shows a live file tree of the workspace alongside the Chat View.
- **Local Mode** — Execution mode in which the agent clones the target repository to a local workspace and operates on local files.
- **Remote Mode** — Execution mode in which the agent operates entirely via GitHub MCP without a local clone.
- **Ghost Validation** — The anti-pattern of marking a Ticket complete without actually executing tests. A hard system failure in this product.
- **LLM-as-last-resort** — Design principle: UI actions that do not require language understanding or judgment (accept, select, edit fields) call APIs directly. The LLM is invoked only when reasoning or generation is needed.

---

## 4. Features

### 4.1 Project Management

**Description:** When a user opens ai-consultant, they land on a project list. They create a new Project by naming it, or resume an existing one. Multiple Projects can be active simultaneously. Each Project is a persistent, isolated workspace with its own Spec, agent memory, Ticket history, and token usage record. Switching Projects changes the active context in the chat; no data is mixed between Projects.

**Functional Requirements:**

#### FR-1: Project Creation
The user can create a new Project by providing a name. The system initializes a persistent Project store (agent memory, Spec slot, Ticket history, cost ledger) and presents the Chat View.

**Consequences (testable):**
- A new Project with a unique name appears in the project list immediately after creation.
- The Project store is initialized with empty agent memory, no Spec, no Tickets.
- The Chat View is presented with an empty state and an onboarding prompt.

#### FR-2: Project List and Resumption
The user can view all Projects and switch to any one at any time. Switching loads the full agent memory, Spec, and Ticket history for the selected Project.

**Consequences (testable):**
- All Projects created by the user appear in the project list on app open.
- Switching to a Project within a session loads its context without requiring re-input from the user.
- Closing and reopening the app preserves all Projects and their state.

#### FR-3: Spec Persistence
The Spec for a Project is stored in two locations: within the app's Project store (for agent access) and written to the project repository (for the user). Both copies remain in sync after every Spec update.

**Consequences (testable):**
- After a Spec is generated or updated, a file exists in both the app store and the project repository reflecting the latest version.
- An agent in a new Session can read the Spec from the app store without user re-input.

---

### 4.2 Spec Pipeline (BMad-Powered)

**Description:** Before implementation, every Project needs a Spec. The app supports three entry paths into implementation, all converging on a validated Spec stored in the Project. The BMad framework's brainstorm and validation pipelines are invoked directly by the app. Realizes UJ-1.

**Functional Requirements:**

#### FR-4: Brainstorm Path
When the user asks to brainstorm or describes a fuzzy idea, the system invokes the BMad brainstorm pipeline. The pipeline guides the user through structured ideation in the Chat View and produces a structured Spec document stored in the Project.

**Consequences (testable):**
- After completing the brainstorm flow, a Spec document is present in the Project store and in the project repository.
- The brainstorm output matches the BMad brainstorm artifact format (`brainstorm-intent.md` + structured spec).
- The system does not proceed to ticket generation or implementation until a Spec is confirmed.

#### FR-5: Spec Review Path
When the user provides an existing spec document (pasted into chat or file path), the system analyzes it using the BMad validation method, identifies gaps or ambiguities, and guides the user through refinement in the Chat View until a validated Spec is confirmed.

**Consequences (testable):**
- The system responds to a provided spec with a structured gap analysis and at least one clarifying question before accepting it as complete.
- A refined Spec is stored in the Project after the user confirms it.

#### FR-6: Direct Implementation Path
When the user provides a Spec and explicitly requests implementation without review, the system accepts the Spec as-is and proceeds to ticket generation or execution without validation dialogue.

**Consequences (testable):**
- A user stating "implement this spec" with a Spec document triggers no validation prompts.
- The Spec is stored and execution begins within one interaction turn.

---

### 4.3 Ticket Management

**Description:** Once a Spec is confirmed, the user may optionally generate Tickets. Ticket generation is not required for implementation — the agent team can work directly from the Spec. When Tickets are generated, they are presented as a structured card view in the Chat View for review and editing before any execution begins. Jira integration is optional; if configured, Tickets are synchronized to Jira. The Execution Queue is ordered by dependency resolution, not arrival order. The Chat View header shows three Mode buttons — **Brainstorm**, **Spec Review**, **Implement** — so the user can switch workflow context explicitly; the LLM may also suggest a mode switch when the conversation signals a transition (e.g., user says "ok let's build it"). BMad pipelines are invoked as subprocess calls from the backend.

**Functional Requirements:**

#### FR-7: Ticket Generation from Spec
The system generates a set of Tickets from the Spec via an LLM call and presents them as a structured card view in the Chat View. Each card displays: ticket title, description, acceptance criteria, and dependency relationships (blocking/blocked-by).

**Consequences (testable):**
- Generated Tickets appear as structured cards in the Chat View, not as plain text.
- Each card shows title, description, acceptance criteria, and dependency fields.
- The LLM is called exactly once for ticket generation; subsequent edits do not trigger additional LLM calls unless the user types in the revision field.

#### FR-8: Ticket Review and Edit (LLM-as-Last-Resort)
In the ticket card view, the user can edit any field directly in the card. Two controls are available: an **Accept** button that commits the Tickets (to Jira if configured, or to the Project store if not) without an LLM call; and a **text field** that sends a revision instruction to the LLM and regenerates the affected Tickets.

**Consequences (testable):**
- Editing a card field and clicking Accept does not produce an LLM call.
- Typing in the revision text field and submitting produces exactly one LLM call.
- After Accept, Tickets are written to Jira (if configured) via direct API call, not via LLM.

#### FR-9: Implementation Selection and Dependency Ordering
Before execution begins, the system presents all confirmed Tickets as a card view with checkboxes. The user selects which Tickets to include in the current run. The system resolves the Execution Queue order based on blocking/blocked-by relationships; the user-selected subset is reordered to respect dependencies automatically.

**Consequences (testable):**
- A Ticket marked as blocked by another is never placed before its blocker in the Execution Queue.
- The user can deselect any Ticket and it is excluded from the current Execution Queue.
- Dependency order is computed without an LLM call.

#### FR-10: Optional Jira Integration
Jira integration is optional. When not configured, Tickets exist only in the Project store. The implementation workflow functions identically with or without Jira. When Jira is configured, Ticket status transitions (In Progress, Done, Error) are synchronized to Jira throughout execution.

**Consequences (testable):**
- An implementation run completes successfully with Jira credentials absent from `.env`.
- With Jira configured, each Ticket status change is reflected in Jira within the same interaction cycle as the agent's action.

---

### 4.4 Agent Execution Engine

**Description:** The Agent Team implements Tickets sequentially — one at a time, never in parallel. Only one active agent execution runs at a time across all Projects. Each agent has access to the full accumulated context: the Spec, prior Ticket outcomes, codebase knowledge, and all decisions made in prior Sessions. All code generation is grounded against current library and framework documentation via Context7 before output. When an agent encounters genuine uncertainty — not enough information to proceed safely — it enters an Agent Pause rather than proceeding blindly.

**Functional Requirements:**

#### FR-11: Sequential Ticket Execution
Tickets in the Execution Queue are implemented one at a time. No new Ticket begins before the current one is fully closed (test-verified, committed, and status updated).

**Consequences (testable):**
- At no point are two Tickets in an "In Progress" state simultaneously.
- A Ticket is not marked complete until its test artifact is confirmed (see FR-17).

#### FR-12: Accumulated Cross-Ticket Context
Each agent has access to the outputs and decisions from all previously completed Tickets in the current run. No agent starts a Ticket without awareness of what was built in prior Tickets.

**Consequences (testable):**
- An agent implementing Ticket N can reference code, decisions, or file paths established in Tickets 1 through N-1 without the user re-providing that information.

#### FR-13: Persistent Cross-Session Project Memory
All Project knowledge — Spec, codebase state, Ticket history, agent decisions, and prior Session outcomes — persists between Sessions. A new Session opens with complete context for the selected Project.

**Consequences (testable):**
- A Session started after closing and reopening the app does not prompt the user for any information already provided in a prior Session for the same Project.
- The agent references prior Ticket outcomes correctly without user re-input.

#### FR-14: Context7 Grounding
Before generating any code, the executing agent queries Context7 for current documentation on the target library or framework. Generated code must conform to the current version of the library, not a cached or hallucinated version.

**Consequences (testable):**
- No generated code references an API that does not exist in the current documented version of the target library.
- A Context7 query is made for every code generation step; the result is incorporated into the generation prompt.

#### FR-15: Agent Pause on Genuine Uncertainty
When an agent determines it cannot proceed safely — due to ambiguous requirements, missing context, or an unresolvable decision point — it halts execution and posts a structured Agent Pause message to the Chat View. The message states: what the agent was attempting, why it cannot proceed, and three explicit options: **Continue** (agent attempts with best-effort), **Clarify** (user provides additional information), **Abandon** (this Ticket is skipped and flagged).

**Consequences (testable):**
- No agent proceeds past a genuine ambiguity without surfacing a message to the user.
- The Agent Pause message includes all three action options.
- Selecting Abandon marks the Ticket with an "Agent Blocked" status and moves to the next Ticket in the queue.

#### FR-16: Auto-Resume After Clarification
After the user responds to an Agent Pause, the agent evaluates whether the response resolves the blocker. If sufficient, execution resumes automatically without user re-triggering. If insufficient, the agent re-prompts with a refined clarification request.

**Consequences (testable):**
- A clarification response that fully resolves the agent's uncertainty results in automatic resumption — no button press required.
- A clarification response that does not resolve the uncertainty produces a follow-up Agent Pause, not silent continuation.

---

### 4.5 Quality and Safety

**Description:** No Ticket is marked complete without actual test execution and a verifiable artifact. Pre-merge regressions are handled autonomously. When an agent cannot resolve an error, it gathers complete diagnostic information before escalating. All code generated for a user's Project includes structured logging configured by default so the user can trace errors when running or testing the output.

**Functional Requirements:**

#### FR-17: Mandatory Test Artifact
A Ticket may only transition to "Done" after a test suite has been executed and a verifiable test artifact (log file, report, or assertion result) has been produced and linked to the Ticket.

**Consequences (testable):**
- Ghost Validation (marking a Ticket Done without test execution) is detectable: the Ticket record always contains a test artifact reference; a missing reference is a system error, not a silent pass.
- The test artifact is stored in the Project store and accessible to the user.

#### FR-18: Autonomous Pre-Merge Regression Handling
If the Tester agent detects a regression before merge, the Developer agent attempts to fix it autonomously. The fix is re-tested before merge proceeds. The user is not interrupted unless the autonomous fix fails.

**Consequences (testable):**
- A pre-merge regression caught by the Tester results in an autonomous fix attempt, not an immediate escalation to the user.
- If the fix passes re-test, the Ticket proceeds to merge with no user intervention.

#### FR-19: Diagnostic Logging Before Escalation
When an agent encounters an error with insufficient log information to diagnose the root cause, it adds logging instrumentation to the code and re-runs before attempting a fix or escalating.

**Consequences (testable):**
- An agent does not attempt a fix or escalate an error unless it has complete log output covering the failure path.
- The added logging instrumentation is committed as part of the Project's codebase, not discarded after diagnosis.

#### FR-20: Error Report and Flagged Commit on Unresolvable Failure
When an agent cannot resolve an error after diagnostic logging and at least one fix attempt, it produces a full error report (error description, complete logs, attempted fixes) and pushes the branch with a commit message that explicitly flags the error state.

**Consequences (testable):**
- The pushed branch commit message contains a machine-readable error flag (e.g., `[ERROR]` prefix) readable by the user and CI systems.
- The error report is stored in the Project store and surfaced in the Chat View.
- The Ticket is transitioned to an "Error" status (reflected in Jira if configured).

#### FR-21: Default Logging in Generated Projects
Every project generated by ai-consultant includes a structured logging setup (e.g., Python `logging` module with configurable levels, or equivalent for the target stack) configured from the first implementation Ticket. Users can trace errors in the output project without adding logging themselves.

**Consequences (testable):**
- The first Ticket implemented for any Project produces a codebase with a functioning logger configured at `INFO` level by default.
- The logger is importable and usable by all subsequent generated modules without additional configuration.

---

### 4.6 Interface and Controls

**Description:** The primary surface is the Chat View: a hybrid of streaming chat messages and embedded structured UI components (cards, buttons, checkboxes). The LLM-as-last-resort principle governs all UI design decisions — actions that do not require language understanding call APIs directly. An opt-in Dev View adds a live file tree for local mode. Token consumption and estimated cost are tracked and displayed per Project and per Session.

**Functional Requirements:**

#### FR-22: Hybrid Chat + Structured Components
The Chat View renders both streaming text messages and embedded structured components (Ticket cards, spec previews, checkbox lists, action buttons) within the same scrollable surface. Components are rendered inline with chat messages in chronological order.

**Consequences (testable):**
- Ticket cards appear inline in the chat flow, not in a separate panel.
- Action buttons on components (Accept, checkboxes) do not produce chat messages unless the action triggers an LLM call.

#### FR-23: Execution Status Stream
During agent execution, the Chat View displays a live execution status block showing: the current Ticket name, elapsed time for the current Ticket, the Execution Queue (completed, in progress, pending), and streaming agent log output.

**Consequences (testable):**
- A user can read the current Ticket name and elapsed time without scrolling.
- The Execution Queue shows all Tickets with their status (done, active, pending) updated in real time.
- Agent log lines appear in the chat as they are produced, not batched after completion.

#### FR-24: Opt-in Dev View (Local Mode)
In Local Mode, the user can toggle a Dev View that adds a live file tree panel showing the workspace. The file tree updates as the agent creates, modifies, or deletes files. The user can open any file in the tree and read its current state while the agent is actively editing it. Toggling the Dev View does not interrupt execution.

**Consequences (testable):**
- A file created by an agent appears in the Dev View file tree within the same interaction cycle as the write.
- Toggling Dev View on or off during active execution does not pause, restart, or interrupt the agent.
- Dev View is absent in Remote Mode; the interface shows execution logs only.

#### FR-25: Token Consumption and Cost Display
The system tracks token consumption for every LLM call within a Session and accumulates it per Project. A visible indicator (e.g., a status bar or collapsible panel) shows: tokens used in the current Session, estimated cost in USD for the current Session, and cumulative tokens and cost for the Project.

**Consequences (testable):**
- Token count and cost update after every LLM call.
- Project-level cumulative cost persists across Sessions and is visible when the Project is selected.
- Cost estimation uses the current published price for the configured model.

#### FR-26: Approval Gate (Jira Path Only)
When Jira is configured, the user must review and accept the generated Ticket card view before any agent begins implementation. Accepting commits Tickets to Jira via direct API call (no LLM). Without Jira, no approval gate exists: brainstorm completion or a direct implementation request is sufficient to begin execution.

**Consequences (testable):**
- In Jira mode, no implementation Ticket begins before the user clicks Accept on the Ticket card view.
- In no-Jira mode, the Ticket card view is optional; the user may proceed directly from spec confirmation to execution.
- The Accept action does not produce an LLM call.

---

## 5. Non-Goals (Explicit)

- **Parallel ticket execution** — sequential execution is a hard constraint; parallel execution causes merge conflicts and cross-ticket context corruption.
- **Full zero-interaction autonomy** — exception-driven human intervention is a feature, not a failure mode.
- **Hosted / SaaS deployment** — self-hosted only in v1.
- **Multi-user collaborative projects** — single-user project context in v1.
- **Direct code editing in the UI** — the user directs via chat; agents own the code.
- **Configurable agent uncertainty threshold** — agents pause when genuinely uncertain; no user-tunable numeric threshold exists.
- **Re-asking for project configuration already provided** — any config provided once persists for the Project lifetime.
- **Information overload UI** — everything is progressive disclosure; all complexity is opt-in.
- **Parallel agent execution across Projects** — only one active agent execution runs at a time; multiple Projects can exist but do not execute concurrently.

---

## 6. MVP Scope

### 6.1 In Scope

- Project creation, list, and resumption with persistent memory
- Three Spec entry paths: brainstorm (BMad pipeline), spec review, direct
- Optional Jira integration (ticket sync, status transitions)
- Ticket generation, card review with inline edit, Accept/revise controls
- Implementation selection via checkbox + dependency ordering
- Sequential agent execution: Supervisor, Developer, Tester, Environment agents
- Context7 grounding for all code generation
- Fixed-threshold Agent Pause with continue/clarify/abandon options
- Auto-resume after user clarification
- Mandatory test artifacts; pre-merge autonomous regression fix
- Diagnostic logging instrumentation before escalation; error report + flagged commit on failure
- Default logging in all generated projects
- Next.js / React Chat View with hybrid chat + structured components
- Execution status stream (current ticket, elapsed time, queue, logs)
- Opt-in Dev View with live file tree (local mode)
- Remote mode (GitHub MCP, logs only)
- Token consumption and estimated cost display per session and project
- Local Mode and Remote Mode
- Deployment: `git clone` + `uv`/`pip` + Docker

### 6.2 Out of Scope for MVP

- Hosted / SaaS option `[NOTE FOR PM: revisit if community demand emerges post-launch]`
- Multi-user project collaboration
- Configurable confidence threshold
- Non-Gemini LLM backends `[NOTE FOR PM: abstraction layer to support this is low-cost; consider in v2]`
- Web-based code editor in Dev View (read-only file tree only in v1)
- Billing / payment integration (open source, user brings own API keys)

---

## 7. Success Metrics

**Primary**

- **SM-1: Full path completion** — A user completes the path from fuzzy idea to committed, test-passing codebase in a single Session without writing any code manually. Validates FR-4, FR-11, FR-17.
- **SM-2: Session continuity** — A user returns to a named Project in a new Session with zero re-configuration or re-explanation required. Validates FR-13.
- **SM-3: Generated project quality** — Every Project generated by ai-consultant installs and produces useful output on first run by the user. Validates FR-21, FR-17.

**Counter-metrics (do not optimize)**

- **SM-C1: LLM call count** — Do not optimize toward minimizing LLM calls at the cost of output quality. The LLM-as-last-resort principle governs UI actions (FR-8, FR-9, FR-26), not agent reasoning steps. Counterbalances any pressure to reduce cost by skipping Context7 grounding (FR-14) or shortcutting test execution (FR-17).

---

## 8. Open Questions

1. **Project memory backend** — Deployment resolved: Docker image includes the DB; uv/pip users supply their own DB instance. Architecture decision (schema, engine choice) deferred to the architect.
2. **BMad subprocess integration with Gemini** — BMad is in the project and will be invoked as a subprocess. The exact wiring between subprocess output and the Gemini-backed agent response stream is not yet defined; needs an architecture spike.
3. **Agent pause heuristic** — The "genuine uncertainty" trigger (FR-15) has no defined heuristic. The architect or implementer needs to decide: LLM self-assessment prompt, tool call failure count, or both.

---

## 9. Assumptions Index

- **§1** — Python + LangGraph is the implementation stack, confirmed by `project-context.md`.
- **§4.2** — BMad framework is already present in the project; pipelines (brainstorm, validation) are invoked as subprocess calls from the Python backend.
- **§4.4** — Context7 MCP integration (`tools/context7_mcp.py`) is functional and can be invoked per code-generation step without prohibitive latency.
- **§4.4** — Only one agent execution runs at a time across all Projects; the system does not need to manage concurrent agent processes.
- **§4.6** — Next.js / React is the chosen frontend framework; Python backend (FastAPI or equivalent) serves the API.
- **§4.3** — Ticket dependency data (blocking/blocked-by) is available from Jira or computed from the Spec when Jira is not used.
- **§6** — Docker image bundles the DB; uv/pip install requires the user to provision their own DB instance.
- **§6** — Docker packaging does not require a hosted environment; the image runs fully locally.
