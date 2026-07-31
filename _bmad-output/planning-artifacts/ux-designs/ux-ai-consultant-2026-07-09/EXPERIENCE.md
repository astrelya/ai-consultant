---
name: ai-consultant
status: final
sources:
  - _bmad-output/specs/spec-spec-driven-dev-app/SPEC.md
  - _bmad-output/planning-artifacts/prds/prd-ai-consultant-2026-07-08/prd.md
  - _bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md
  - _bmad-output/planning-artifacts/epics.md
updated: 2026-07-09
---

# ai-consultant — Experience Spine

## Foundation

Desktop web, primary. Next.js 14+ / React 18+ with shadcn/ui and Tailwind CSS. Self-hosted, single-user per deployment instance (no multi-tenancy in v1). `DESIGN.md` is the visual identity reference.

Two execution modes exist at the infrastructure level: **Remote mode** (`AGENT_MODE=remote`, default) uses GitHub MCP only — no local filesystem access. **Local mode** (`AGENT_MODE=local`) clones repositories to a local workspace. The Dev View surface (live file tree) is only available in Local mode; the toggle does not render in Remote mode.

The frontend communicates with the FastAPI backend exclusively via REST (actions) and SSE (streaming output). No direct database or agent access from the browser. The backend owns all state mutations; the frontend is a display-and-dispatch surface.

## Information Architecture

| Surface | Reached from | Purpose | FR |
|---|---|---|---|
| Project List (Home) | App open, sidebar nav | View and create projects | FR-1, FR-2 |
| Chat View | Project row click, project creation | Primary interaction surface — chat, tickets, status | FR-22 |
| Brainstorm Mode | Chat input intent detection | Guided ideation via BMad subprocess | FR-4 |
| Spec Review Mode | Chat input intent detection | Spec gap analysis and refinement | FR-5 |
| Direct Implementation Mode | Chat input intent detection | Accept spec as-is, proceed to tickets | FR-6 |
| Ticket Card View | Embedded in Chat View on ticket generation | Review, edit, accept tickets | FR-7, FR-8, FR-9 |
| Implementation Selection View | Embedded in Chat View after ticket accept | Checkbox select + dependency ordering | FR-9 |
| Execution Status Block | Pinned in Chat View during active execution | Live queue state + elapsed time | FR-23 |
| Dev View (Local mode only) | Toggle within Chat View | Live file tree of the cloned workspace | FR-24 |
| Cost Indicator | Fixed footer of Chat View | Session + cumulative token and cost display | FR-25 |

**Layout composition:**
- Left sidebar (240px): project list, active project indicator, "New Project" CTA.
- Main area: Project List (home) or Chat View (inside a project).
- Chat View default: full-width scroll surface.
- Chat View with Dev View open: 60% chat / 40% Dev View horizontal split.
- Execution Status Block: pinned above the chat input, visible only during active execution.
- Cost Indicator: fixed bottom strip below the chat input.

Sidebar collapses to an icon-only rail on `md` breakpoints.

→ Composition reference: `mockups/project-list.html`, `mockups/chat-view.html`, `mockups/ticket-cards.html`. Spine wins on conflict.

## Voice and Tone

Microcopy. Brand voice and aesthetic posture live in `DESIGN.md.Brand & Style`.

| Do | Don't |
|---|---|
| "Describe what you want to build, or type 'brainstorm'" | "Welcome! Let's start your journey! 🚀" |
| "Spec confirmed. Ready to generate tickets." | "Great job! Your spec looks amazing!" |
| "Agent running — Ticket 3 of 7" | "AI is working… please wait" |
| "No Jira configured — execution begins immediately." | "Jira integration unavailable. You may proceed." |
| "3 tickets pending · 1 in progress · 2 done" | "Status: 3 pending, 1 in progress, 2 done." |
| "Tests passed. Ticket closed." | "Ticket successfully completed ✓" |
| "Error on Ticket 4 — see report below." | "An unexpected error occurred. Please try again." |
| "0 tokens / $0.00" (when no usage) | Hide cost or show nothing |
| Action verbs without filler: "Generate tickets", "Accept all", "Approve & Begin" | "Click here to generate your tickets" |

The product speaks like a senior engineer giving a status update: precise, minimal, no emoji in system messages (only user messages may contain emoji), no cheerleading.

## Component Patterns

Behavioral. Visual specs live in `DESIGN.md.Components`.

| Component | Surface | Behavioral rules |
|---|---|---|
| Project row | Project List, sidebar | Click anywhere navigates to Chat View for that project. No hover-only actions — all actions are in a dropdown menu on the `…` icon. |
| Chat message — user | Chat View | Right-aligned. Text only. Submitted via Enter or the Send button. Displayed immediately on send — before server response. |
| Chat message — agent/system | Chat View | Left-aligned. Renders in chronological order. Streaming text appends token by token — never buffered and displayed in full. |
| Ticket Card (default) | Chat View (embedded) | Inline in the chat scroll surface — not a sidebar or modal. Shows: title, description, acceptance criteria (collapsible beyond 3 lines), `blocking` list, `blocked_by` list. Editable fields (title, description, AC) inline-edit on click. Accept button and revision text field always visible. |
| Ticket Card (done) | Chat View | Fields are read-only. Accept / revision controls hidden. Done indicator visible. |
| Ticket Card (error) | Chat View | Error banner replaces revision controls. Report link visible. |
| Ticket checkbox | Implementation Selection View | Defaults to checked. Unchecking triggers a downstream warning if dependent tickets are still checked (not a hard block — a warning badge). |
| Execution Status Block | Chat View | Visible only during active execution. Hidden (removed from DOM, not just hidden) when idle. |
| Log Stream | Chat View (within Execution Status Block) | Auto-scrolls to newest line unless user has scrolled up. "↓ Jump to latest" button appears when scrolled up. |
| Spec Preview | Chat View | Collapsed by default (5 lines + "Show full spec"). Expand/collapse toggle. Read-only. |
| Dev View file tree | Dev View panel | Tree structure with expand/collapse for directories. Click a file → read-only content viewer below the tree. File state dot: emerald = created, amber = modified, destructive strikethrough = deleted. |
| Cost Indicator | Chat View (fixed footer) | Two rows: session / cumulative. Always visible — shows `0 tokens / $0.00` when no usage. Never behind a toggle. |
| Agent Active Badge | Sidebar (active project), Execution Status Block | Animated pulsing amber dot + "RUNNING" label. Maximum one visible at a time — only the currently executing project shows it. Disappears when execution ends. |

## State Patterns

| State | Surface | Treatment |
|---|---|---|
| No projects | Project List | `display-sm`: "Create your first project." Single input + Create button. No project list table. |
| Project list populated | Project List | List of project rows: name, creation date, last activity. "New Project" button in top right and sidebar CTA. |
| New project created | Chat View | Empty chat with onboarding prompt: "Describe what you want to build, or type 'brainstorm'." No prior history. |
| Project resumed | Chat View | Prior chat history rendered on load. Session cost counters start at zero; cumulative cost pre-populated from DB. |
| Brainstorm mode active | Chat View | Mode badge in Chat View header: "Brainstorm". Log Stream shows BMad subprocess output as it arrives. User is prompted to respond within the chat flow. Spec is not produced until the pipeline completes. |
| Spec Review mode active | Chat View | Mode badge: "Spec Review". Pipeline output streams into chat. At least one gap/question appears before spec is accepted. |
| Direct Implementation mode active | Chat View | Mode badge: "Implement". No validation prompts. Spec preview appears inline after save. |
| Spec confirmed | Chat View | Collapsed Spec Preview block appears in chat. System message: "Spec confirmed. Ready to generate tickets." |
| Tickets generated | Chat View | Ticket Card View replaces the chat input temporarily. Cards appear in dependency order (blockers first). |
| Jira configured — approval required | Ticket Card View | "Approve & Begin" button visible below the card list. No execution starts until clicked. |
| No Jira — proceed immediately | Ticket Card View | "Begin Execution" button after ticket acceptance. No approval gate. |
| Execution active | Chat View | Execution Status Block appears. Log Stream starts receiving lines. Agent Active Badge pulses in sidebar. Input field disabled (greyed, tooltip: "Execution in progress"). |
| Execution idle | Chat View | Execution Status Block removed from DOM. Input field re-enabled. |
| Ticket transitions: Pending → In Progress | Execution Status Block | Queue item changes from `○` to `⟳ (amber)`. |
| Ticket transitions: In Progress → Done | Execution Status Block | Queue item changes from `⟳` to `✓ (emerald)`. |
| Ticket transitions: In Progress → Error | Execution Status Block | Queue item changes from `⟳` to `✗ (destructive)`. Error report appears in chat as a system message. Execution continues with the next ticket. |
| Pre-merge regression detected | Chat View | No user notification — agent attempts autonomous fix. SSE events continue flowing in Log Stream ("Regression detected — attempting autonomous fix…"). |
| Autonomous fix fails | Chat View | Structured escalation message in chat: what failed, what was attempted, two action buttons — "Continue" (mark ticket Error and proceed) or "Abandon" (stop execution). |
| Ghost validation attempt | System (server-side) | Hard system error logged to server; SSE event surfaced in chat: "Error: Ticket {id} cannot close without a test artifact. Execution halted." Never silent. |
| Dev View toggled on | Chat View | Panel opens alongside chat (60/40 split). File tree loads from workspace root. No execution interruption. |
| Dev View toggled off | Chat View | Panel collapses. Chat returns to full width. No execution interruption. |
| File created/modified/deleted | Dev View | `file_tree_update` SSE event received → tree node updates within the same event cycle. Dot indicator reflects operation type. |
| Token update | Cost Indicator | `token_update` SSE event received → both rows update. No page reload, no polling. |
| Backend disconnected | Chat View | shadcn `Toast` (persistent): "Connection lost. Attempting to reconnect…" SSE subscription retries with exponential backoff. |

## Interaction Primitives

**Keyboard:**
- `Enter` — send chat message (Shift+Enter for newline in input)
- `Escape` — close dialogs, collapse Dev View, clear focused state
- `Tab` / `Shift+Tab` — navigate between ticket card fields in edit mode; standard tab order across surfaces

**Mouse / Pointer:**
- Click anywhere on a project row → navigate to Chat View
- Click anywhere on a ticket card field → enter inline edit mode
- Click outside an editing field → commit edit (same as blur-to-save)
- Scroll up in Log Stream → disable auto-scroll; "Jump to latest" button appears
- Click "Jump to latest" → re-enable auto-scroll, scroll to bottom
- Click file in Dev View tree → open file content in read-only viewer below

**Input handling:**
- Chat input is a `Textarea` (auto-grows to max 6 lines, then scrolls).
- Chat send: Enter key OR Send button. Both call `POST /projects/{id}/chat` — no frontend LLM invocation.
- Ticket field edits: inline `Input` or `Textarea` per field. Save on blur or on Accept button.
- Accept single ticket: `PATCH /projects/{id}/tickets/{ticket_id}` — zero LLM calls.
- Accept all tickets: one `PATCH` per ticket — zero LLM calls total.
- Revision instruction submit: text field + Submit → one LLM call, regenerates affected tickets only.
- Dependency ordering: computed by topological sort on the frontend from the ticket graph — zero LLM calls.

**LLM-as-last-resort (AD-4) strictly observed:**
Actions that never invoke an LLM: Accept (single or all), checkbox select/deselect, dependency ordering, field edit + blur, Dev View toggle, Approve & Begin, cost indicator updates.
Actions that invoke exactly one LLM call: chat message send (routing/intent detection), revision instruction submit, ticket generation request, brainstorm/spec-review pipeline trigger.

**Banned patterns:**
- Polling for execution state — all updates arrive via SSE.
- Batch-then-display for agent output — every line streams as produced.
- Modal-on-modal stacking — one dialog depth maximum.
- Spinner with no label — every loading state has a text description.
- Auto-dismissing toasts for errors — errors require explicit dismissal.

## Accessibility Floor

Behavioral. Visual contrast lives in `DESIGN.md` (inherits shadcn's WCAG AA-compliant defaults; brand color overrides verified to maintain contrast ratios).

- WCAG 2.2 AA across all surfaces.
- Screen reader announces surface on navigation: "Project list — {N} projects" / "Chat — {project name}".
- `aria-live="polite"` on the Log Stream — new lines announced without interrupting other speech.
- `aria-live="assertive"` on error escalation messages in chat — these interrupt because they require user action.
- Execution Status Block: `role="status"` with `aria-label="Execution in progress — Ticket {name}, {elapsed time}"`.
- Ticket cards: `role="article"` with `aria-label="Ticket: {title}, status {state}"`. Editable fields have explicit labels (not placeholder-only).
- Checkbox in Implementation Selection View: associated label is the ticket title.
- Dev View file tree: `role="tree"` with keyboard expand/collapse on `Enter` / `Space`.
- Cost Indicator: `aria-label="Token usage: {session_tokens} this session / {total_tokens} total, estimated cost {session_cost} this session / {total_cost} total"`.
- All action buttons have visible text labels — no icon-only buttons without a visible label or `aria-label`.
- Agent Active Badge: `aria-label="Agent running"` with `aria-live="polite"` on badge appearance/disappearance.
- Focus rings: inherit shadcn's `ring` token. Visible at AA contrast against all background surfaces including `log-surface`.
- Tab order: matches reading order on every surface. Logical flow: sidebar → main content → fixed footer (Cost Indicator).

## Responsive & Platform

| Breakpoint | Behavior |
|---|---|
| `≥ xl` (1280px+) | Sidebar expanded (240px). Dev View split available (60/40). Full Execution Status Block visible. |
| `lg` (1024–1279px) | Sidebar expanded. Dev View available but narrows to 35% split. |
| `md` (768–1023px) | Sidebar collapses to icon rail. Dev View disabled — `md` viewport is too narrow for the split. Toggle hidden. |
| `< md` (`sm`) | Sidebar becomes a Sheet triggered from a top bar hamburger. No Dev View. Chat View is single-column full-width. |

ai-consultant is a desktop-primary product. Mobile is supported for read-only project monitoring (view chat history, view ticket status, view cost), but ticket editing, Dev View, and execution triggers are desktop-only (not disabled on mobile — but the layout doesn't optimize for them).

## Brainstorm & Spec Flows

These are the three entry paths to a confirmed Spec. The Chat View header shows the active mode as a badge; only one mode is active at a time per project session.

### Brainstorm Path

**Trigger:** User message contains brainstorm intent ("brainstorm", "I have an idea for…", "let's explore…").

1. System detects intent, sets mode badge to "Brainstorm".
2. Backend invokes BMad brainstorm subprocess (`POST /projects/{id}/chat` returns a stream of BMad pipeline invocation events).
3. Log Stream opens in Chat View showing subprocess stdout line by line via SSE.
4. BMad asks clarifying questions — these appear as system messages; user responds in the chat input.
5. Pipeline completes → `bmad_complete` event received.
6. Spec content saved to project store and repo file.
7. Spec Preview block appears in chat (collapsed).
8. System message: "Spec confirmed. Ready to generate tickets." + "Generate tickets" and "Review spec" buttons.
9. No progression to ticket generation without explicit user action.

### Spec Review Path

**Trigger:** User pastes a spec document into chat.

1. System detects spec-review intent, sets mode badge to "Spec Review".
2. BMad validation subprocess invoked; output streams into Log Stream.
3. At least one gap/question appears before the spec can be accepted.
4. User responds to gaps in chat.
5. On validated state: Spec Preview appears, system message confirms readiness.

### Direct Implementation Path

**Trigger:** User sends a message like "implement this spec: …" or "use this spec and build it".

1. System detects direct implementation intent, sets mode badge to "Implement".
2. No validation prompts or gap analysis shown.
3. Spec saved immediately (dual-location: DB + repo file).
4. Spec Preview appears in chat.
5. System message: "Spec stored. What next?" + "Generate tickets" and "Execute directly" options.
6. If Jira is not configured: execution can begin from this point with no approval gate.

## Ticket Card Flow

After spec confirmation, the user requests ticket generation. This flow covers FR-7 through FR-9 and FR-26.

### Ticket Generation

1. User types "generate tickets" (or equivalent intent) in the chat input.
2. Exactly one LLM call is made (server-side). Frontend shows a skeleton card set during generation.
3. `tickets_generated` SSE event received. Ticket Card View renders inline in the chat scroll surface.
4. Cards appear in dependency order (blockers before dependents).
5. No additional LLM calls on render — the card set is static until the user takes action.

### Ticket Review

- Each card shows: title, description, acceptance criteria, `blocking`, `blocked_by`.
- Fields are individually clickable to inline-edit.
- **Accept (single card):** calls `PATCH /projects/{id}/tickets/{ticket_id}` — zero LLM.
- **Revision instruction:** text field below the card. Submit → one LLM call, only affected ticket(s) regenerated; unaffected tickets unchanged.
- **Accept All:** commits all tickets via direct API calls — zero LLM calls total.
- A card's status badge updates in-place when saved.

### Implementation Selection

1. After all tickets accepted, Implementation Selection View appears (replaces ticket card action controls — cards remain visible but actions are replaced by checkboxes).
2. All tickets checked by default.
3. User unchecks tickets to exclude. Warning badge appears on dependent tickets whose blocker is excluded.
4. "Begin Execution" / "Approve & Begin" (Jira path) button submits `POST /projects/{id}/execute` with ordered ticket ID list.
5. Dependency order computed by frontend topological sort — no LLM, no additional API call.

### Jira Approval Gate

If Jira is configured (`JIRA_URL`, `JIRA_USER`, `JIRA_API_TOKEN` present):
- "Approve & Begin" button visible. Execution does not start until clicked.
- Each ticket is synced to Jira on ticket acceptance (MCP call, not direct HTTP).
- Ticket state transitions (`In Progress`, `Done`, `Error`) are synced to Jira within the same interaction cycle.

If Jira is not configured:
- No approval gate. "Begin Execution" starts immediately.
- No Jira API calls at any point. Workflow is identical minus sync.

## Execution & Agent Output Flow

This covers the live execution experience from FR-11 through FR-21 and FR-23.

### Execution Start

1. `POST /projects/{id}/execute` received by backend.
2. Execution Status Block appears pinned above chat input.
3. Agent Active Badge pulses in sidebar next to the active project.
4. Chat input is disabled.
5. Log Stream starts receiving lines via SSE.

### Execution Status Block Content

```
┌──────────────────────────────────────────────┐
│ ● RUNNING  ai-consultant                     │
│ Ticket 3 of 7: "Scaffold FastAPI backend"    │
│ Elapsed: 04:32                               │
├──────────────────────────────────────────────┤
│ ✓  1. Scaffold Next.js frontend             │
│ ✓  2. PostgreSQL schema                     │
│ ⟳  3. Scaffold FastAPI backend   [active]   │
│ ○  4. SSE streaming endpoint                │
│ ○  5. Spec pipeline integration             │
│ ○  6. Ticket generation                     │
│ ○  7. Agent execution engine                │
├──────────────────────────────────────────────┤
│ [log stream — mono, scrollable]             │
│ > Querying Context7 for FastAPI…            │
│ > Writing backend/main.py                   │
└──────────────────────────────────────────────┘
```

Queue icons: `✓` = Done (emerald), `⟳` = In Progress (amber, animated), `○` = Pending (slate). Updates via SSE — no additional API call.

### Concurrent Execution Conflict

If a second `POST /execute` arrives while execution is running (any project): backend returns `409 Conflict`. Frontend shows a shadcn `Toast`: "Execution already in progress — wait for it to complete before starting another."

### Context7 Grounding

Before every code generation step, the agent queries Context7. SSE event surfaced in Log Stream: `"Querying Context7 for {library}…"`. User sees this without any action required.

### Test Artifact Gate

On ticket close, `TesterAgent` must write a test artifact reference before the ticket can transition to Done. If the artifact is missing: hard server error, surfaced in chat as an error system message. Never silent. Execution halts on that ticket; the error is logged and the next ticket may proceed (per FR-20: `[ERROR]` flagged commit, execution continues with next).

### Pre-Merge Regression Loop

1. `TesterAgent` detects regression.
2. Log Stream: `"Regression detected — attempting autonomous fix…"`.
3. `SupervisorAgent` delegates fix attempt to developer agent. No user notification.
4. Fix committed, test suite re-runs.
5. **If tests pass:** merge proceeds, ticket → Done. Log Stream: `"Fix applied — tests passed. Ticket closed."`.
6. **If tests fail:** structured escalation system message in chat with two action buttons.

### Diagnostic Logging Step

When an agent encounters an error with insufficient log coverage:
1. Log Stream: `"Adding diagnostic logging to {file}…"`.
2. Instrumentation committed to codebase (permanent, not temporary).
3. Code re-run, full logs captured.
4. Fix attempt or escalation follows.

### Escalation Message Format

When the agent cannot resolve a failure:
```
[Error — Ticket {id}]
What failed: {error description}
What was attempted: {list of attempts}
Log output: [collapsible link to error report]

[ Continue — mark Error and proceed ]   [ Abandon — stop execution ]
```

"Continue": ticket → Error, `[ERROR]` prefixed commit pushed, execution moves to next ticket.
"Abandon": execution stops, all remaining tickets stay Pending, input field re-enabled.

## Dev View

Available only when `AGENT_MODE=local`. When in Remote mode, the Dev View toggle does not render — it is absent, not disabled.

**Panel content:**
- File tree rooted at the cloned workspace directory.
- Directories expand/collapse.
- Files show their state dot (created = emerald, modified = amber, deleted = destructive strikethrough).
- Click a file → file content renders in a read-only viewer pane below the tree (shadcn `ScrollArea` with mono text).

**Live update behavior:**
- `file_tree_update` SSE event received → tree node and dot update within the same event cycle.
- No polling.
- The viewer re-reads file content on each `file_tree_update` for the currently viewed file.

**Layout interaction:**
- Toggling Dev View on/off during active execution does not pause, restart, or interrupt the agent.
- Toggle is a button in the Chat View header: "Dev View" with an icon. Not a modal, not a separate page.

## Token Consumption Display

**Source:** `token_update` SSE event after every LLM call: `{"session_tokens": N, "session_cost_usd": X, "total_tokens": M, "total_cost_usd": Y}`.

**Cost Indicator format:**
```
Session: 4,320 tokens · $0.08    Total: 18,940 tokens · $0.38
```

Costs calculated server-side using `COST_PER_1K_TOKENS` env var with a published-price default. No LLM call to compute cost. Cost Indicator updates on every `token_update` event — no polling, no page reload.

When a project is resumed: cumulative totals pre-populated from `cost_ledger` in PostgreSQL. Session counters start at zero.

## Inspiration & Anti-patterns

**Lifted from Linear:** sharp edges, status color discipline (one color per state, no ambiguity), keyboard-first posture, progressive disclosure (summary → drill-down).

**Lifted from Vercel/GitHub Actions:** terminal-surface log blocks, mono font for output, status dot vocabulary, `[ERROR]` prefixed flagged states.

**Lifted from Claude / ChatGPT:** hybrid chat + embedded structured components in a single scroll surface. The insight: users are already in a conversational context; ticket cards are just structured messages, not a separate UI plane.

**Rejected — Tab-based navigation for PM View / Dev View:** views are toggled within the same surface, not navigated to. A PM doesn't "go to" Dev View; it opens alongside chat. Tab navigation would imply they are peer surfaces — they aren't.

**Rejected — Sidebar ticket panel:** tickets are embedded inline in the chat scroll surface, not pushed to a sidebar. Sidebars create a context-switching cost and hide the reasoning flow that led to the ticket set. The conversation is the product.

**Rejected — Polling for agent updates:** all state changes arrive via SSE as they happen. Polling introduces latency and visual jank. The product's core value is live transparency — polling would undermine it.

**Rejected — Code editor in Dev View:** Dev View is a file tree + read-only viewer. The agent owns code. The user owns direction via chat. Providing an editor would break that contract and introduce merge conflicts with in-progress agent edits.

**Rejected — Auto-advancing execution after error:** failed tickets stop at the error state. The user receives a structured escalation and chooses whether to continue or abandon. Silent auto-advance on error is a trust violation.

**Rejected — Modal for ticket details:** tickets are inline cards in chat. A modal would require the user to lose their place in the conversation. Inline expansion (collapsible AC section) is sufficient.

## Key Flows

### Flow 1 — Brainstorm to Execution (Pary, solo developer, evening session)

Pary opens ai-consultant in a browser tab. The Project List shows two prior projects. She clicks "New Project", types "recipe-manager", and hits Enter. The Chat View opens with an empty surface and the onboarding prompt.

She types: *"I want to brainstorm a recipe manager app — I have some fuzzy ideas."* The system detects brainstorm intent. Mode badge changes to "Brainstorm". The Log Stream opens and BMad output starts streaming line by line — project structure, target users, core features. The system asks her two clarifying questions in chat. She answers each.

The pipeline completes. Spec Preview appears in the chat — collapsed to 5 lines. System message: *"Spec confirmed. Ready to generate tickets."* Two buttons: "Generate tickets" and "Review spec". Pary clicks "Generate tickets." A skeleton card set flickers in briefly, then 7 ticket cards appear inline in the chat scroll surface, ordered by dependency.

She reads Ticket 4, changes the title by clicking on it, types a new title, and clicks Accept. She leaves the rest unchanged. She clicks "Accept All." Implementation Selection View replaces the card controls. All 7 are checked. She unchecks Ticket 6 (optional analytics). A warning badge appears on Ticket 7: *"Blocker Ticket 6 excluded."* She re-checks Ticket 6. She clicks "Begin Execution."

Execution Status Block appears. Log Stream starts. The amber pulse badge appears in the sidebar next to "recipe-manager." Pary watches the first ticket's log lines for 20 seconds, then minimizes the window and goes to make tea.

She returns 15 minutes later. Execution Status Block shows `✓` on 5 tickets, `⟳` on Ticket 6. Three minutes later, Ticket 6 → Done. A pre-merge regression was detected and fixed autonomously — she reads *"Regression detected — attempting autonomous fix…"* and *"Fix applied — tests passed."* in the Log Stream without having been interrupted. All 7 tickets close. Agent Active Badge disappears. Input field re-enables.

The Cost Indicator reads: *"Session: 52,840 tokens · $1.12    Total: 52,840 tokens · $1.12"*

### Flow 2 — PM Resume and Review (Sophie, non-technical PM, next morning)

Sophie opens ai-consultant. Project List shows "recipe-manager" with a "last activity: 8 hours ago" timestamp. She clicks it. Chat View loads with prior conversation history — the brainstorm session, ticket cards, execution log output. She scrolls up to re-read the ticket list without having to re-generate anything.

She sees Ticket 5 had an `[ERROR]` flagged commit (Sophie wasn't present when it happened, but the error report is inline in the chat as a system message). She reads the structured escalation message, clicks the link to the error report, and skims the log. She decides to re-run Ticket 5 by typing *"re-run ticket 5."* The system generates a new execution queue with Ticket 5 only.

She leaves again. Ten minutes later, Ticket 5 is Done. Cost Indicator now reads cumulative total across both sessions.

### Flow 3 — Direct Spec Import (Marcus, senior dev, has a spec ready)

Marcus opens a new project, pastes his pre-written spec into the chat input with the prefix "implement this spec:". Mode badge: "Implement". No validation prompts appear. Spec Preview collapses into the chat immediately. System message: *"Spec stored. What next?"* — two buttons: "Generate tickets" and "Execute directly." Marcus clicks "Generate tickets," reviews the cards in 90 seconds, clicks "Accept All," and clicks "Begin Execution."

Because Jira is configured in his environment, the approval gate is present. He sees "Approve & Begin" instead of "Begin Execution." He clicks it. Execution starts.
