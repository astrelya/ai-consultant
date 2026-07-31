---
stepsCompleted: ["step-01-validate-prerequisites", "step-02-design-epics", "step-03-create-stories", "step-04-final-validation"]
inputDocuments:
  - "_bmad-output/planning-artifacts/prds/prd-ai-consultant-2026-07-08/prd.md"
  - "_bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md"
  - "_bmad-output/project-context.md"
---

# ai-consultant - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for ai-consultant, decomposing the requirements from the PRD and Architecture Spine into implementable stories.

## Requirements Inventory

### Functional Requirements

FR-1: Project Creation — The user can create a new Project by providing a name. The system initializes a persistent Project store (agent memory, Spec slot, Ticket history, cost ledger) and presents the Chat View.
FR-2: Project List and Resumption — The user can view all Projects and switch to any one at any time. Switching loads the full agent memory, Spec, and Ticket history for the selected Project.
FR-3: Spec Persistence — The Spec for a Project is stored in two locations: within the app's Project store (for agent access) and written to the project repository (for the user). Both copies remain in sync after every Spec update.
FR-4: Brainstorm Path — When the user asks to brainstorm or describes a fuzzy idea, the system invokes the BMad brainstorm pipeline. The pipeline guides the user through structured ideation in the Chat View and produces a structured Spec document stored in the Project.
FR-5: Spec Review Path — When the user provides an existing spec document, the system analyzes it using the BMad validation method, identifies gaps or ambiguities, and guides the user through refinement until a validated Spec is confirmed.
FR-6: Direct Implementation Path — When the user provides a Spec and explicitly requests implementation without review, the system accepts the Spec as-is and proceeds to ticket generation or execution without validation dialogue.
FR-7: Ticket Generation from Spec — The system generates a set of Tickets from the Spec via an LLM call and presents them as a structured card view in the Chat View. Each card displays: ticket title, description, acceptance criteria, and dependency relationships.
FR-8: Ticket Review and Edit (LLM-as-Last-Resort) — In the ticket card view, the user can edit any field directly in the card. Accept button commits Tickets without an LLM call; text field sends revision instruction to LLM and regenerates affected Tickets.
FR-9: Implementation Selection and Dependency Ordering — Before execution, the system presents all confirmed Tickets as a card view with checkboxes. The user selects which Tickets to include. The system resolves the Execution Queue order based on blocking/blocked-by relationships automatically.
FR-10: Optional Jira Integration — Jira integration is optional. The implementation workflow functions identically with or without Jira. When configured, Ticket status transitions are synchronized to Jira throughout execution.
FR-11: Sequential Ticket Execution — Tickets in the Execution Queue are implemented one at a time. No new Ticket begins before the current one is fully closed (test-verified, committed, and status updated).
FR-12: Accumulated Cross-Ticket Context — Each agent has access to the outputs and decisions from all previously completed Tickets in the current run.
FR-13: Persistent Cross-Session Project Memory — All Project knowledge persists between Sessions. A new Session opens with complete context for the selected Project.
FR-14: Context7 Grounding — Before generating any code, the executing agent queries Context7 for current documentation on the target library or framework.
FR-15: Agent Pause on Genuine Uncertainty — [DEFERRED — Cut from v1 per Architecture Spine / CAP-5] When an agent cannot proceed safely, it halts and posts a structured Agent Pause message. Not implemented in v1.
FR-16: Auto-Resume After Clarification — [DEFERRED — Cut from v1, dependent on FR-15] After the user responds to an Agent Pause, execution resumes automatically if the response resolves the blocker.
FR-17: Mandatory Test Artifact — A Ticket may only transition to "Done" after a test suite has been executed and a verifiable test artifact has been produced and linked to the Ticket.
FR-18: Autonomous Pre-Merge Regression Handling — If the Tester agent detects a regression before merge, the Developer agent attempts to fix it autonomously. The user is not interrupted unless the fix fails.
FR-19: Diagnostic Logging Before Escalation — When an agent encounters an error with insufficient log information, it adds logging instrumentation and re-runs before attempting a fix or escalating.
FR-20: Error Report and Flagged Commit on Unresolvable Failure — When an agent cannot resolve an error, it produces a full error report and pushes the branch with a commit message that explicitly flags the error state.
FR-21: Default Logging in Generated Projects — Every project generated by ai-consultant includes a structured logging setup configured from the first implementation Ticket.
FR-22: Hybrid Chat + Structured Components — The Chat View renders both streaming text messages and embedded structured components within the same scrollable surface in chronological order.
FR-23: Execution Status Stream — During agent execution, the Chat View displays a live execution status block: current Ticket name, elapsed time, Execution Queue state, and streaming agent log output.
FR-24: Opt-in Dev View (Local Mode) — In Local Mode, the user can toggle a Dev View showing a live file tree of the workspace. The file tree updates as the agent creates, modifies, or deletes files.
FR-25: Token Consumption and Cost Display — The system tracks token consumption for every LLM call and accumulates it per Project. A visible indicator shows current session and cumulative project usage and estimated cost.
FR-26: Approval Gate (Jira Path Only) — When Jira is configured, the user must review and accept the generated Ticket card view before any agent begins implementation. Without Jira, no approval gate exists.

### NonFunctional Requirements

NFR-1: Sequential execution only — no parallel ticket execution at any time across any project (hard constraint, not tunable).
NFR-2: Project data isolation — no shared mutable state between projects at any layer.
NFR-3: Async throughout the agent layer — all agent invocations and MCP tool calls must be non-blocking (await ainvoke).
NFR-4: Config from env vars only — no hardcoded credentials, model names, or paths anywhere in source.
NFR-5: Ghost validation prevention — test artifact reference is mandatory before ticket transitions to Done; missing reference is a hard system error.
NFR-6: Streaming over polling — all agent output delivered via SSE as produced; batch-after-completion is a violation.
NFR-7: LLM-as-last-resort — UI actions not requiring language understanding (Accept, checkbox, field edit) must call REST endpoints directly with zero LLM invocations.
NFR-8: Self-hosted only — no SaaS/hosted path in v1; single-user project context.
NFR-9: Context7 grounding mandatory — every code generation step preceded by a Context7 MCP query; skipping is a violation.
NFR-10: PostgreSQL as the single project store engine — no SQLite fallback for either uv/pip or Docker deployment path.

### Additional Requirements

- **No starter template** — greenfield system; Epic 1 scaffolds the full project structure from scratch.
- FastAPI backend with REST routes (`/projects`, `/tickets`, `/execute`) and SSE stream endpoint (`/stream`).
- Next.js 14+ / React 18+ frontend with Chat View and optional Dev View.
- MCPManager singleton — all MCP connections go through `await MCPManager.get_instance()`; new sources registered in `MCPManager.initialize()` only.
- BMad pipelines invoked as Python subprocesses — stdout bridged to SSE stream (architecture spike OQ-2 must be resolved before FR-4 / FR-5 stories can be implemented).
- Dual execution mode — `AGENT_MODE=local` → `LocalDeveloperAgent`; `AGENT_MODE=remote` (default) → `RemoteDeveloperAgent`.
- Ticket state machine — `Pending → In Progress → Done | Error | Agent Blocked`; transitions only through project store writes.
- PostgreSQL bundled in Docker image; uv/pip users provision their own instance.
- Deployment targets: `git clone` + `uv`/`pip`, and Docker.

### UX Design Requirements

*None — no UX Design document available. UI requirements are fully covered by FR-22 through FR-24 in the PRD.*

### FR Coverage Map

| FR | Epic | Brief |
|---|---|---|
| FR-1 | Epic 1 | Project creation + store initialization |
| FR-2 | Epic 1 | Project list and resumption |
| FR-3 | Epic 3 | Dual-location Spec persistence (app store + repo) |
| FR-4 | Epic 3 | Brainstorm path via BMad subprocess |
| FR-5 | Epic 3 | Spec review + gap analysis path |
| FR-6 | Epic 3 | Direct implementation path (no validation) |
| FR-7 | Epic 4 | Ticket generation via LLM → card view |
| FR-8 | Epic 4 | Inline edit + Accept (zero LLM) / revision (one LLM) |
| FR-9 | Epic 4 | Checkbox selection + dependency-ordered queue |
| FR-10 | Epic 4 | Optional Jira sync (status transitions) |
| FR-11 | Epic 5 | Sequential execution — one ticket at a time |
| FR-12 | Epic 5 | Accumulated cross-ticket context |
| FR-13 | Epic 5 | Persistent cross-session project memory |
| FR-14 | Epic 5 | Context7 grounding before every code-gen step |
| FR-15 | *Deferred* | Agent Pause — cut from v1 (CAP-5) |
| FR-16 | *Deferred* | Auto-Resume — cut from v1 (depends on FR-15) |
| FR-17 | Epic 5 | Mandatory test artifact gate |
| FR-18 | Epic 5 | Autonomous pre-merge regression fix loop |
| FR-19 | Epic 5 | Diagnostic logging instrumentation before escalation |
| FR-20 | Epic 5 | Error report + flagged commit |
| FR-21 | Epic 5 | Default logging scaffold in generated projects |
| FR-22 | Epic 2 | Hybrid Chat + structured components surface |
| FR-23 | Epic 2 | Live execution status stream (SSE) |
| FR-24 | Epic 6 | Opt-in Dev View with live file tree (local mode) |
| FR-25 | Epic 6 | Token consumption and cost display |
| FR-26 | Epic 4 | Jira approval gate before execution |

## Epic List

### Epic 1: Backend Foundation & Project Management
Users can start the app, create a named project, and resume it in a later session with all data persisting in PostgreSQL. All subsequent epics build on this foundation.
**FRs covered:** FR-1, FR-2

### Epic 2: Frontend & Chat Interface
Users can open the web app, see their project list, enter a project, and interact via a working streaming chat surface including the live execution status block.
**FRs covered:** FR-22, FR-23

### Epic 3: Spec Pipeline
Users can define what they want to build — via brainstorming, spec review, or direct import — and end up with a validated Spec stored in both the Project store and the repository.
**FRs covered:** FR-3, FR-4, FR-5, FR-6

### Epic 4: Ticket Management
Users can generate implementation tickets from their Spec, review and edit them inline, select which to run, and (if using Jira) approve them before execution begins.
**FRs covered:** FR-7, FR-8, FR-9, FR-10, FR-26

### Epic 5: Agent Execution Engine & Quality
The agent team implements and tests tickets sequentially with full cross-ticket and cross-session context, mandatory test artifacts, autonomous regression fixing, and diagnostic logging — producing a committed, test-passing branch.
**FRs covered:** FR-11, FR-12, FR-13, FR-14, FR-17, FR-18, FR-19, FR-20, FR-21

### Epic 6: Advanced Visibility & Controls
Users can monitor token consumption and estimated cost per session and project, and (in Local Mode) toggle a live file tree showing exactly what the agent is building.
**FRs covered:** FR-24, FR-25

---

## Epic 1: Backend Foundation & Project Management

Users can start the app, create a named project, and resume it in a later session with all data persisting in PostgreSQL. All subsequent epics build on this foundation.

### Story 1.1: Scaffold FastAPI Backend with PostgreSQL

As a developer,
I want a running FastAPI backend with PostgreSQL connectivity and a health check endpoint,
So that I have a verified working foundation on which all project management APIs can be built.

**Acceptance Criteria:**

**Given** the repository is cloned and `DATABASE_URL` is set in `.env`
**When** `uvicorn backend.main:app --reload` is started
**Then** the server starts on port 8000 and `GET /health` returns `200 {"status": "ok"}`
**And** the backend connects to PostgreSQL using `DATABASE_URL` from `os.environ.get()` — no hardcoded connection string
**And** a `projects` table is created on startup with columns: `id` (UUID PK), `name` (text), `agent_memory` (JSONB), `spec` (text nullable), `ticket_history` (JSONB), `cost_ledger` (JSONB), `created_at` (timestamp)
**And** all route handlers are `async def`
**And** running without `DATABASE_URL` logs a clear error and exits — it does not silently proceed

### Story 1.2: Create a New Project

As a user,
I want to create a new project by providing a name,
So that I have a persistent, isolated workspace with its own memory, spec slot, and ticket history.

**Acceptance Criteria:**

**Given** the backend is running and connected to PostgreSQL
**When** I send `POST /projects` with body `{"name": "my-project"}`
**Then** a new project record is inserted with a unique UUID, empty `agent_memory` (`{}`), null `spec`, empty `ticket_history` (`[]`), and zeroed `cost_ledger`
**And** the response is `201` with `{"id": "<uuid>", "name": "my-project", "created_at": "<timestamp>"}`
**And** sending a second `POST /projects` with the same name creates a separate distinct project — names are not unique keys
**And** sending `POST /projects` with a missing or blank `name` returns `422 Unprocessable Entity`

### Story 1.3: List and Resume Projects

As a user,
I want to list all my projects and retrieve any one by ID,
So that I can resume work on a previous project without re-configuring or re-explaining context.

**Acceptance Criteria:**

**Given** two or more projects exist in the database
**When** I send `GET /projects`
**Then** all projects are returned as a JSON array, each with `id`, `name`, and `created_at`
**And** no `agent_memory` or `spec` data is included in the list response (list is lightweight)

**Given** a project with a known ID exists
**When** I send `GET /projects/{id}`
**Then** the full project record is returned including `agent_memory`, `spec`, `ticket_history`, and `cost_ledger`

**Given** no project with that ID exists
**When** I send `GET /projects/{nonexistent-id}`
**Then** the response is `404 Not Found`

### Story 1.4: SSE Streaming Endpoint

As a developer,
I want an SSE endpoint that the frontend can subscribe to per project,
So that real-time agent output can be pushed to the client without polling, ready for use by the execution engine in Epic 5.

**Acceptance Criteria:**

**Given** the backend is running
**When** a client connects to `GET /stream/{project_id}` with `Accept: text/event-stream`
**Then** the response has `Content-Type: text/event-stream` and immediately sends an event: `event: connected\ndata: {"project_id": "<id>"}\n\n`
**And** the connection stays open until the client disconnects
**And** a helper `publish_event(project_id, event_type, data)` async function exists that, when called, sends a formatted SSE event to all active subscribers for that project
**And** `GET /stream/{nonexistent-project-id}` returns `404` before upgrading to SSE
**And** the endpoint handles client disconnect gracefully without crashing the server

---

## Epic 2: Frontend & Chat Interface

Users can open the web app, see their project list, enter a project, and interact via a working streaming chat surface including the live execution status block.

### Story 2.1: Scaffold Next.js Frontend with API & SSE Clients

As a developer,
I want a running Next.js 14+ frontend with a typed REST client and SSE subscription hook wired to the backend,
So that all subsequent frontend features have a consistent, tested foundation.

**Acceptance Criteria:**

**Given** the backend is running and the frontend is started with `npm run dev`
**When** the app loads in a browser
**Then** it renders without errors and displays a placeholder home page
**And** a `lib/api/client.ts` module exists with typed wrappers for `GET /projects`, `POST /projects`, and `GET /projects/{id}`
**And** a `lib/sse/useStream.ts` React hook exists that subscribes to `GET /stream/{project_id}` and exposes an array of received events
**And** `NEXT_PUBLIC_API_URL` env var controls the backend base URL — no hardcoded localhost in source
**And** TypeScript strict mode is enabled with zero type errors

### Story 2.2: Project List and Creation UI

As a user,
I want to see all my projects on the home screen and create a new one by entering a name,
So that I can start a new project or return to any existing one without touching a command line.

**Acceptance Criteria:**

**Given** the frontend is loaded
**When** the home page renders
**Then** all existing projects are displayed (fetched from `GET /projects`) showing name and creation date
**And** an empty state with a "Create your first project" prompt is shown when no projects exist

**Given** I enter a project name and submit
**When** the create action fires
**Then** `POST /projects` is called directly (no LLM call)
**And** the new project appears in the list immediately
**And** the app navigates to the Chat View for the new project

**Given** I click an existing project
**When** the navigation occurs
**Then** the app loads the Chat View for that project, fetching its data from `GET /projects/{id}`

### Story 2.3: Chat View with Streaming Agent Output

As a user,
I want a Chat View that displays streamed messages from the agent in real time and lets me send messages,
So that I can see the agent working as it happens and communicate with it without page refreshes.

**Acceptance Criteria:**

**Given** I am in a project's Chat View
**When** the view loads
**Then** an empty state is shown with an onboarding prompt ("Describe what you want to build, or type 'brainstorm'")
**And** the SSE hook connects to `GET /stream/{project_id}` and starts receiving events

**Given** the agent emits a text message event
**When** the event arrives via SSE
**Then** the message appears in the chat in chronological order without a page reload
**And** partial / streaming text appends chunk-by-chunk — it is not batched and displayed after completion

**Given** I type a message and press send
**When** the message is submitted
**Then** my message appears in the chat immediately
**And** the message is sent to the backend via `POST /projects/{id}/chat` REST call — no LLM is invoked by the frontend directly

### Story 2.4: Execution Status Block

As a user,
I want a live execution status block in the Chat View showing the current ticket, elapsed time, and the full execution queue state,
So that I always know what the agent is working on without scrolling through log output.

**Acceptance Criteria:**

**Given** an execution is active for the current project
**When** the execution status block renders
**Then** it shows the current ticket name and elapsed time (updated every second)
**And** it shows all tickets in the Execution Queue with their status: done ✓, active ⟳, pending ○
**And** the queue state updates in real time as SSE events arrive — no polling

**Given** no execution is active
**When** the Chat View is open
**Then** the execution status block is hidden (not an empty placeholder)

**Given** a ticket transitions from active to done
**When** the status event arrives
**Then** the queue display updates within the same SSE event cycle — no additional API call required

---

## Epic 3: Spec Pipeline

Users can define what they want to build — via brainstorming, spec review, or direct import — ending with a validated Spec stored in both the Project store and the repository.

### Story 3.1: BMad Subprocess Integration (OQ-2 Architecture Spike)

As a developer,
I want a verified mechanism to invoke a BMad pipeline as a Python subprocess and stream its stdout output to the project's SSE channel in real time,
So that FR-4 and FR-5 can be implemented without a blocking unknown.

**Acceptance Criteria:**

**Given** the backend receives a request to run a BMad pipeline command
**When** `SubprocessRunner.run(cmd, project_id)` is called
**Then** the subprocess is launched asynchronously (non-blocking, no event-loop deadlock)
**And** each line written to the subprocess's stdout is forwarded via `publish_event(project_id, "bmad_output", line)` as it is produced — not buffered until completion
**And** when the subprocess exits, a `bmad_complete` event is published with the exit code
**And** if the subprocess exits with a non-zero code, a `bmad_error` event is published with stderr content
**And** a smoke test invokes `echo "test output"` as the subprocess and confirms the SSE stream receives the output

### Story 3.2: Dual-Location Spec Storage

As a user,
I want my confirmed Spec stored in both the Project database record and written as a file in my project repository,
So that the agent team can always access it from the app store and I can inspect or version it in the repo.

**Acceptance Criteria:**

**Given** a project exists with a known repo path
**When** `POST /projects/{id}/spec` is called with a spec string
**Then** the `spec` field in the project's PostgreSQL record is updated to the provided content
**And** the spec is written to `<repo_path>/spec.md` (creating the file if it doesn't exist, overwriting if it does)
**And** the response confirms both writes succeeded
**And** if the repo path is not set, the spec is saved to the DB only and a warning is logged — execution is not blocked
**And** `GET /projects/{id}` returns the latest spec content from the DB

### Story 3.3: Brainstorm Mode

As a user,
I want to type "brainstorm" (or describe a fuzzy idea) in the Chat View and have the BMad brainstorm pipeline guide me through structured ideation,
So that I end up with a structured Spec document stored in my project without writing it myself.

**Acceptance Criteria:**

**Given** I am in a project's Chat View with no existing Spec
**When** I send a message containing brainstorm intent (e.g. "brainstorm", "I have an idea for…")
**Then** the Chat View header highlights the Brainstorm mode button
**And** the backend invokes the BMad brainstorm subprocess for this project
**And** brainstorm output streams into the Chat View line-by-line via SSE (not batched)

**Given** the brainstorm pipeline completes successfully
**When** the `bmad_complete` event arrives
**Then** the resulting spec content is saved via the dual-location spec storage (Story 3.2)
**And** the Chat View shows a confirmation message with a spec preview and a prompt to review or proceed
**And** the system does not proceed to ticket generation without explicit user confirmation

### Story 3.4: Spec Review Mode

As a user,
I want to paste an existing spec into chat and have the agent analyze it for gaps and guide me through refinement,
So that I can harden an incomplete or rough spec into a validated one before implementation begins.

**Acceptance Criteria:**

**Given** I paste a spec document into the Chat View
**When** the backend detects spec review intent
**Then** the Chat View header highlights the Spec Review mode button
**And** the BMad validation subprocess is invoked and streams its analysis output via SSE
**And** the analysis produces at least one structured gap or clarifying question before accepting the spec

**Given** I respond to the clarifying questions
**When** the dialogue reaches a validated state
**Then** the refined Spec is saved via dual-location storage (Story 3.2)
**And** the Chat View shows a confirmation that the Spec is validated and ready

**Given** I paste a spec and the validation finds no gaps
**When** the pipeline completes
**Then** the Spec is saved as-is with a message confirming it is complete

### Story 3.5: Direct Implementation Mode

As a user,
I want to provide a Spec and explicitly request implementation without any review dialogue,
So that I can skip validation and proceed directly to execution when I already have a complete spec.

**Acceptance Criteria:**

**Given** I send a message such as "implement this spec: <spec content>" or "use this spec and build it"
**When** the backend detects direct implementation intent
**Then** the Chat View header highlights the Implement mode button
**And** no validation prompts or gap analysis are shown
**And** the Spec is saved immediately via dual-location storage (Story 3.2)
**And** the app confirms the Spec is stored and asks which path to take next: generate tickets or execute directly

**Given** Jira is not configured
**When** the direct path is confirmed
**Then** execution can begin from spec confirmation — no approval gate is required

---

## Epic 4: Ticket Management

Users can generate implementation tickets from their Spec, review and edit them inline, select which to run, and (if using Jira) approve them before execution begins.

### Story 4.1: Ticket Generation from Spec

As a user,
I want the system to generate a set of implementation tickets from my confirmed Spec via a single LLM call,
So that I have a structured, reviewable plan before any code is written.

**Acceptance Criteria:**

**Given** a confirmed Spec exists for the current project
**When** I request ticket generation (e.g. "generate tickets" or "create a plan")
**Then** exactly one LLM call is made to generate the full ticket set
**And** each ticket is stored in the project's `ticket_history` in PostgreSQL with: `id` (UUID), `title`, `description`, `acceptance_criteria`, `status` (`Pending`), `blocking` (list of ticket IDs), `blocked_by` (list of ticket IDs)
**And** a `tickets_generated` SSE event is published so the frontend can render them
**And** subsequent requests to view tickets do not trigger additional LLM calls
**And** if no Spec exists, the backend returns a `400` with a clear message — ticket generation is not started

### Story 4.2: Ticket Card View in Chat

As a user,
I want the generated tickets displayed as structured inline cards in the Chat View — each showing title, description, acceptance criteria, and dependencies,
So that I can review the full implementation plan before committing to it.

**Acceptance Criteria:**

**Given** a `tickets_generated` event is received via SSE
**When** the Chat View renders
**Then** each ticket appears as an inline card in the chat flow (not in a separate panel)
**And** each card displays: title, description, acceptance criteria, `blocking` list, and `blocked_by` list
**And** the cards appear in dependency-resolved order (blockers before dependents)
**And** action buttons (Accept, revision text field) are visible on each card
**And** displaying the card view does not trigger any LLM call

### Story 4.3: Inline Ticket Edit and Accept

As a user,
I want to edit any field on a ticket card directly and accept it without an LLM call, or submit a revision instruction that regenerates only the affected tickets,
So that I maintain full control over the plan with minimal AI overhead on simple edits.

**Acceptance Criteria:**

**Given** a ticket card is displayed in the Chat View
**When** I edit any field (title, description, or AC) directly in the card and click Accept
**Then** `PATCH /projects/{id}/tickets/{ticket_id}` is called with the edited fields — no LLM call is made
**And** the card updates in place with the saved values

**Given** I type a revision instruction in the card's text field and submit
**When** the revision is sent
**Then** exactly one LLM call is made to regenerate only the affected ticket(s)
**And** regenerated cards replace the old ones in the chat flow
**And** unaffected tickets are not re-generated

**Given** I click Accept All
**When** the action fires
**Then** all tickets are committed to the project store via direct API calls — zero LLM invocations

### Story 4.4: Implementation Selection and Dependency Ordering

As a user,
I want to select which tickets to include in the current execution run using checkboxes, with the system automatically ordering them to respect blocking relationships,
So that I control scope while the system guarantees a safe execution sequence.

**Acceptance Criteria:**

**Given** all tickets have been accepted
**When** the selection view renders
**Then** each ticket is shown as a card with a checkbox, defaulting to checked
**And** I can uncheck any ticket to exclude it from the current run

**Given** I confirm my selection
**When** the Execution Queue is built
**Then** the queue is ordered by topological sort of the blocking/blocked-by graph — computed without any LLM call
**And** a ticket marked as `blocked_by` another is never placed before its blocker in the queue
**And** a deselected ticket's dependents are also flagged with a warning (their blocker will not run)
**And** `POST /projects/{id}/execute` is called with the ordered ticket ID list to begin execution

### Story 4.5: Optional Jira Integration and Approval Gate

As a user,
I want ticket status transitions synced to Jira when configured, and an approval gate in the Chat View before execution begins,
So that my Jira board stays current and I retain explicit control before the agent team starts writing code.

**Acceptance Criteria:**

**Given** `JIRA_URL`, `JIRA_USER`, and `JIRA_API_TOKEN` are set in `.env`
**When** tickets are accepted
**Then** each ticket is created in Jira via the Jira MCP (through MCPManager) — not via direct HTTP calls
**And** as each ticket transitions state (`In Progress`, `Done`, `Error`), the corresponding Jira issue is updated within the same interaction cycle

**Given** Jira is configured and tickets are accepted
**When** the ticket card view is displayed
**Then** an Approve & Begin button is visible and execution does not start until it is clicked
**And** clicking Approve & Begin calls `POST /projects/{id}/execute` directly — no LLM call

**Given** Jira is not configured
**When** tickets are accepted
**Then** no approval gate is shown — execution can proceed immediately after ticket selection
**And** no Jira API calls are attempted — the workflow is identical to the Jira path minus sync

---

## Epic 5: Agent Execution Engine & Quality

The agent team implements and tests tickets sequentially with full cross-ticket and cross-session context, mandatory test artifacts, autonomous regression fixing, and diagnostic logging — producing a committed, test-passing branch.

### Story 5.1: Backend Execution Endpoint & Sequential Lock

As a developer,
I want the `POST /projects/{id}/execute` endpoint to acquire a process-level lock before starting any ticket and release it only after full completion,
So that no two tickets — across any project — ever execute simultaneously.

**Acceptance Criteria:**

**Given** `POST /projects/{id}/execute` is called with an ordered list of ticket IDs
**When** no other execution is active system-wide
**Then** the global execution lock is acquired and execution begins with the first ticket in the list
**And** each ticket's status is set to `In Progress` in PostgreSQL before its agent work begins
**And** the lock is released only after: test artifact written AND ticket status updated AND branch committed/pushed

**Given** a second `POST /projects/{id}/execute` arrives while one is already running (any project)
**When** the request is processed
**Then** it returns `409 Conflict` with a message indicating execution is already in progress
**And** the running execution is not interrupted

**Given** MCPManager has not been initialized
**When** the first execution request arrives
**Then** `await MCPManager.get_instance()` is called exactly once during backend startup (FastAPI lifespan event)
**And** all MCP tool sets (GitHub, Jira if configured, Context7) are registered inside `MCPManager.initialize()` — never called ad-hoc

### Story 5.2: SupervisorAgent Wired to Backend & Project Store

As a developer,
I want `SupervisorAgent` to receive ticket context from the project store and delegate to the appropriate sub-agent, publishing progress events to the SSE stream as it works,
So that the frontend can display live execution state and the agent hierarchy is correctly maintained.

**Acceptance Criteria:**

**Given** execution begins for a ticket
**When** `SupervisorAgent` is invoked
**Then** it loads the ticket record and current project state from PostgreSQL via the project store access layer
**And** it delegates implementation to `LocalDeveloperAgent` (if `AGENT_MODE=local`) or `RemoteDeveloperAgent` (if `AGENT_MODE=remote`)
**And** no sub-agent calls another sub-agent directly — all coordination flows through `SupervisorAgent`
**And** after each meaningful action, `publish_event(project_id, "agent_log", message)` is called so the Chat View receives it via SSE
**And** all agent invocations use `await agent_executor.ainvoke(...)` — no synchronous calls

### Story 5.3: Cross-Ticket Accumulated Context

As a user,
I want each agent to have full access to the outputs, decisions, and file paths established in all previously completed tickets in the current run,
So that the agent never asks me to re-explain what was already built.

**Acceptance Criteria:**

**Given** Ticket N-1 has been completed
**When** the agent begins Ticket N
**Then** the agent's invocation prompt includes a summary of all prior ticket outcomes (titles, key decisions, created file paths) from the project's `ticket_history` in PostgreSQL
**And** the agent can reference code paths or decisions from prior tickets without the user providing that information again
**And** adding context from prior tickets does not trigger additional LLM calls beyond the ticket implementation call itself

### Story 5.4: Cross-Session Persistent Project Memory

As a user,
I want to close the app and return to a project in a new session with complete context — Spec, ticket history, agent decisions — already loaded,
So that I never re-explain anything already provided to the agent team.

**Acceptance Criteria:**

**Given** a project has completed at least one execution session
**When** I close and reopen the app and navigate to that project
**Then** `GET /projects/{id}` returns the full `agent_memory`, `spec`, and `ticket_history` from PostgreSQL
**And** the Chat View shows prior conversation context without requiring any user input
**And** the agent's first action in the new session does not prompt for any information already in the project store
**And** project memory is fully isolated — loading Project A never reads or blends data from Project B

### Story 5.5: Context7 Grounding Before Code Generation

As a developer,
I want every code generation step in a developer agent to be preceded by a Context7 MCP query for the target library,
So that all generated code conforms to the current documented API and never references deprecated or hallucinated APIs.

**Acceptance Criteria:**

**Given** a developer agent is about to generate code for a specific library or framework
**When** the generation step executes
**Then** a Context7 MCP query is made for that library before the generation prompt is assembled
**And** the query result is included in the generation prompt
**And** skipping the Context7 query for any reason is a hard violation: the code generation step does not proceed without it
**And** the Context7 query itself uses `await` (non-blocking, AD-9)
**And** a log event is published via SSE: "Querying Context7 for <library>…" so the user can see grounding in action

### Story 5.6: Mandatory Test Artifact Gate

As a user,
I want a ticket to only transition to "Done" after a test suite has been executed and a verifiable artifact is written to the project store,
So that no ticket is ever silently marked complete without real test execution (ghost validation is impossible).

**Acceptance Criteria:**

**Given** `TesterAgent` has finished running tests for a ticket
**When** it attempts to close the ticket
**Then** it must call `store.write_test_artifact(ticket_id, artifact_ref)` before the ticket status can be set to `Done`
**And** `artifact_ref` is a non-empty string (log file path or assertion result summary)
**And** if `artifact_ref` is missing or empty, the ticket transition to `Done` raises a hard system error — it does not silently pass
**And** the artifact reference is stored in PostgreSQL on the ticket record and returned by `GET /projects/{id}`
**And** the error is published to SSE and surfaced in the Chat View — it is never swallowed silently

### Story 5.7: Autonomous Pre-Merge Regression Fix

As a user,
I want the agent team to detect regressions before merge and fix them autonomously without interrupting me,
So that only passing code reaches the branch — and I'm only pulled in when the agent genuinely cannot fix it.

**Acceptance Criteria:**

**Given** `TesterAgent` detects a regression before the merge step
**When** the regression is identified
**Then** `SupervisorAgent` delegates a fix attempt to the developer agent — the user is not notified at this point
**And** the fix is committed and the full test suite re-runs before the merge proceeds

**Given** the autonomous fix passes the re-test
**When** re-test completes
**Then** the merge proceeds and the ticket transitions to `Done` with the fix included — no user intervention

**Given** the autonomous fix fails re-test after one attempt
**When** the second test run fails
**Then** the user is notified via SSE/Chat with a structured message: what failed, what was attempted, and the options (Continue / Abandon)

### Story 5.8: Diagnostic Logging Before Escalation

As a developer,
I want the agent to add structured logging instrumentation to the code and re-run before attempting any fix or escalating to the user,
So that every error escalation includes complete log coverage of the failure path — no blind guesses.

**Acceptance Criteria:**

**Given** an agent encounters an error with insufficient log output to diagnose the root cause
**When** the error is detected
**Then** the agent adds logging instrumentation to the relevant code path (committed as a real change, not temporary)
**And** the code is re-run to capture the full log output
**And** only after capturing complete logs does the agent attempt a fix or escalate
**And** the added logging is preserved in the codebase — it is not removed after diagnosis
**And** a "Adding diagnostic logging to <file>…" event is published to SSE

### Story 5.9: Error Report and Flagged Commit

As a user,
I want to receive a full error report and see the branch pushed with a clearly flagged commit when the agent cannot resolve a failure,
So that I can diagnose the problem myself and CI systems can detect the error state automatically.

**Acceptance Criteria:**

**Given** the agent cannot resolve an error after diagnostic logging and at least one fix attempt
**When** the failure is confirmed
**Then** a full error report is written to the project store: error description, complete logs, and all attempted fixes
**And** the report is surfaced in the Chat View via SSE
**And** the branch is pushed with a commit message prefixed `[ERROR]` (e.g. `[ERROR] ticket-42: cannot resolve import failure`)
**And** the ticket transitions to `Error` status in PostgreSQL (and in Jira if configured)
**And** execution continues with the next ticket in the queue — the failed ticket does not block remaining work

### Story 5.10: Default Logging Scaffold in Generated Projects

As a user,
I want every project generated by ai-consultant to include a working structured logger from the very first ticket,
So that I can trace errors in the output codebase without adding logging myself.

**Acceptance Criteria:**

**Given** the first ticket for any project is being implemented
**When** the developer agent writes the initial code
**Then** a structured logging setup is included (e.g. Python `logging` module configured at `INFO` level, or equivalent for the target stack)
**And** the logger is importable and usable by all subsequently generated modules without additional configuration
**And** the logging config is driven by an env var (e.g. `LOG_LEVEL`) with `INFO` as the default
**And** a pytest test confirms the logger initializes without errors on import

---

## Epic 6: Advanced Visibility & Controls

Users can monitor token consumption and estimated cost per session and project, and (in Local Mode) toggle a live file tree showing exactly what the agent is building.

### Story 6.1: Token Consumption Tracking and Cost Ledger

As a user,
I want every LLM call to record its token count to the project's cost ledger in PostgreSQL,
So that I have an accurate, persistent record of usage and cost per project across all sessions.

**Acceptance Criteria:**

**Given** any LLM call is made anywhere in the agent layer
**When** the call completes
**Then** the token count (prompt tokens + completion tokens) is written to the project's `cost_ledger` in PostgreSQL before the call's result is returned
**And** the cost ledger accumulates across all sessions — it is never reset when a session ends
**And** the estimated cost in USD is calculated using the configured model's published price (from env var `COST_PER_1K_TOKENS` with a sensible default)
**And** a `token_update` SSE event is published after each LLM call: `{"session_tokens": N, "session_cost_usd": X, "total_tokens": M, "total_cost_usd": Y}`
**And** no additional LLM call is made to compute or display the cost

### Story 6.2: Cost Display in Chat View

As a user,
I want a visible indicator in the Chat View showing session token usage, estimated session cost, and cumulative project cost,
So that I can monitor spending without leaving the chat interface.

**Acceptance Criteria:**

**Given** I am in a project's Chat View
**When** the view loads
**Then** a cost indicator is visible (e.g. status bar or collapsible panel) showing: current session tokens, current session cost (USD), and total project tokens and cost
**And** the indicator updates after every `token_update` SSE event — no polling, no page reload required

**Given** I open a project that has prior session history
**When** the Chat View loads
**Then** the cumulative project cost is pre-populated from the `cost_ledger` in PostgreSQL
**And** the current session counters start at zero and accumulate from that point

**Given** a project has no LLM usage yet
**When** the cost indicator renders
**Then** it shows `0 tokens / $0.00` — not an empty or hidden state

### Story 6.3: Dev View with Live File Tree (Local Mode)

As a user,
I want to toggle an optional Dev View panel in Local Mode that shows a live file tree of the workspace, updating in real time as the agent creates, modifies, or deletes files,
So that I can follow along with what the agent is building without reading source code.

**Acceptance Criteria:**

**Given** `AGENT_MODE=local` and I am in a project's Chat View
**When** I click the Dev View toggle
**Then** a file tree panel opens alongside the chat showing the current workspace contents
**And** toggling Dev View on or off during active execution does not pause, restart, or interrupt the agent

**Given** the agent creates, modifies, or deletes a file
**When** the file operation completes
**Then** a `file_tree_update` SSE event is published with the updated path and operation type
**And** the file tree in Dev View reflects the change within the same SSE event cycle

**Given** I click any file in the Dev View tree
**When** the file is selected
**Then** its current content is displayed in a read-only viewer — no editing capability

**Given** `AGENT_MODE=remote`
**When** I am in a project's Chat View
**Then** the Dev View toggle is absent — it is not shown as disabled, it simply does not exist in remote mode
