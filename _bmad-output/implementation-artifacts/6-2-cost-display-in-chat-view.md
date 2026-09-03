---
baseline_commit: b873c0bec72ac891aa89d1b0fcf39a979992fbc7
---

# Story 6.2: Cost Display in Chat View

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want a visible indicator in the Chat View showing session token usage, estimated session cost, and cumulative project cost,
so that I can monitor spending without leaving the chat interface (FR-25 / Epic 6 — frontend consumer of Story 6.1's `token_update` SSE event).

## Acceptance Criteria

1. **Given** I am in a project's Chat View (`frontend/app/projects/[id]/page.tsx` → `ChatInterface.tsx`),
   **When** the view mounts,
   **Then** a cost indicator is visible in the fixed footer of the Chat View surface (below the message composer, above the viewport bottom) rendering EXACTLY two data groups: **Session** (current session tokens + USD cost) and **Total** (cumulative project tokens + USD cost). The indicator MUST be always visible — never hidden, never behind a toggle, never conditionally rendered on `hasMessages`. This replaces the existing static placeholder footer already present in `ChatInterface.tsx` (lines ~298–301 at baseline `b873c0b`) which reads `"Session: 0 tokens / $0.00"` / `"Project: 0 tokens / $0.00"` as hard-coded strings.

2. **And** the indicator MUST update after every `token_update` SSE event with EXACTLY zero polling and zero page reloads. `token_update` is delivered by Story 6.1's `agents/token_tracker.record_llm_call` via `backend/api/sse.publish_event(project_id, "token_update", payload)` where `payload = {"session_tokens": int, "session_cost_usd": float, "total_tokens": int, "total_cost_usd": float}`. The four keys are exact — no additional keys, no renamed keys. The frontend MUST NOT compute cost client-side (no multiplication by a price constant) — it uses the pre-computed `*_cost_usd` values verbatim (AD-4 corollary on the frontend).

3. **And** `frontend/lib/sse/useStream.ts` `NAMED_EVENT_TYPES` MUST be extended to include the literal `"token_update"`. This is the ONE-LINE plumbing change that lets `EventSource.addEventListener("token_update", …)` fire and pushes the event into the `events` array with `type: "token_update"`. Follow the exact pattern already used for `execution_start`, `spec_stored`, and `tickets_generated`. Do NOT introduce a second `EventSource`, do NOT add a new hook, do NOT change the `useStream` return shape — reuse the existing `events` array.

4. **And** a new presentational component `frontend/components/CostIndicator.tsx` MUST be created with the exact public surface:
   ```ts
   export interface CostIndicatorProps {
     events: StreamEvent[];        // from useStream — same reference passed to ExecutionStatusBlock
     initialTotalTokens: number;   // seeded from cost_ledger.total_tokens (0 for new projects)
     initialTotalCostUsd: number;  // seeded from cost_ledger.total_cost_usd (0 for new projects)
   }
   export default function CostIndicator(props: CostIndicatorProps): JSX.Element;
   ```
   Rendering rules:
   - Layout: `flex justify-between items-center` inside a `<footer>` with classes `flex-shrink-0 border-t border-border bg-muted/30 px-4 py-1.5 text-xs font-mono text-muted-foreground` (matches the current placeholder in `ChatInterface.tsx` — preserve the visual token per DESIGN.md `{cost-indicator}` component spec: mono font, muted surface, `rounded/sm` context, never elevated).
   - Left cell content: `Session: <span>{sessionTokensFmt} tokens · ${sessionCostFmt}</span>` — the label `Session:` in muted colour, the value in `text-foreground` (per DESIGN.md mockup rules: `.cost-row` muted / `.cost-row span` foreground).
   - Right cell content: `Total: <span>{totalTokensFmt} tokens · ${totalCostFmt}</span>` — same structure. Label MUST read `Total:` (not `Project:`, not `Cumulative:`) per EXPERIENCE.md line 84 and DESIGN.md `{cost-indicator}` component spec. The current placeholder's `Project:` label is WRONG at baseline — fix it.
   - Number formatting: `sessionTokensFmt` and `totalTokensFmt` use `new Intl.NumberFormat("en-US").format(n)` (i.e. `14820 → "14,820"`). Cost format is `costUsd.toFixed(2)` (i.e. `0.313 → "0.31"`, `0 → "0.00"`). Empty/first-render state MUST render `0 tokens · $0.00` on both rows — NOT an empty string, NOT `--`, NOT a spinner (EXPERIENCE.md line 62 / .memlog decision line 12).
   - Accessibility: the outer `<footer>` MUST carry `aria-label` matching EXPERIENCE.md line 163: `` `Token usage: ${sessionTokens} this session / ${totalTokens} total, estimated cost $${sessionCost} this session / $${totalCost} total` ``. Include `role="status"` and `aria-live="polite"` on the footer so screen readers announce updates without interrupting.

5. **And** `CostIndicator` MUST derive the four live values by scanning the `events` prop for the LAST event with `type === "token_update"` (following the exact pattern in `ChatInterface.tsx` for `spec_stored` and `tickets_generated`: `events.filter(ev => ev.type === "token_update").slice(-1)[0]`). Values:
   - If no `token_update` event has arrived yet: `sessionTokens = 0`, `sessionCostUsd = 0`, `totalTokens = initialTotalTokens`, `totalCostUsd = initialTotalCostUsd`. This satisfies AC-6 (open a project with prior history → totals pre-populated from DB, session counters at zero).
   - After the first `token_update`: use its payload keys verbatim (`data.session_tokens`, `data.session_cost_usd`, `data.total_tokens`, `data.total_cost_usd`). Do NOT fall back to `initialTotal*` once ANY `token_update` has been received — the SSE payload already reflects the ledger state after that call.
   - Type guards: the `data` field is `unknown` on `StreamEvent`; cast via a local type `type TokenUpdatePayload = { session_tokens: number; session_cost_usd: number; total_tokens: number; total_cost_usd: number }` and read defensively with `?? 0` on each key so a malformed payload (missing a key) does not throw or blank the display.

6. **Given** I open a project that has prior session history (Chat View mounts, project detail is fetched via `apiClient.getProject(projectId)`),
   **When** the Chat View loads,
   **Then** the cumulative Total row MUST be pre-populated from `cost_ledger.total_tokens` and `cost_ledger.total_cost_usd` returned by `GET /projects/{project_id}` (already exposed on the backend — see `backend/api/routes/projects.py` `ProjectDetail.cost_ledger: dict` at line 61 of that file at baseline). The Session row MUST start at `0 tokens · $0.00` (a new `session_id` is generated inside `SupervisorAgent.run_tickets` per Story 6.1 — the frontend has no session concept beyond "since the current Chat View mounted").
   **And** if the project has never had an LLM call, `cost_ledger` is `{}` (default per `backend/store/database.py:64`) — the component MUST treat missing `total_tokens` and `total_cost_usd` keys as `0` and render `0 tokens · $0.00` on both rows (AC of "0 tokens / $0.00 — not empty, not hidden").

7. **And** `frontend/lib/api/client.ts` MUST be updated in TWO ways:
   - Extend the `Project` interface (at the top of the file) with a new optional field: `cost_ledger?: { total_prompt_tokens?: number; total_completion_tokens?: number; total_tokens?: number; total_cost_usd?: number; last_updated?: string }`. Keys are optional to reflect the `{}` default. This mirrors the JSONB shape written by `backend/store/project_store.add_cost_ledger_entry` (Story 6.1 AC-4).
   - No new endpoint is needed — `getProject` already returns the full detail record (`ProjectDetail` in `backend/api/routes/projects.py`). Do NOT add a new REST call.

8. **And** `ChatInterface.tsx` MUST wire it end-to-end:
   - Remove the current static `<footer>` block (lines ~298–301 at baseline) and replace with `<CostIndicator events={events} initialTotalTokens={initialTotalTokens} initialTotalCostUsd={initialTotalCostUsd} />`.
   - Add two new pieces of component state in `ChatInterface`: `const [initialTotalTokens, setInitialTotalTokens] = useState<number>(0);` and `const [initialTotalCostUsd, setInitialTotalCostUsd] = useState<number>(0);`.
   - In the existing `loadProject` effect (currently sets `jiraConfigured` and hydrates `messages`), ALSO read `project.cost_ledger` (may be `undefined` or `{}`) and call the setters with `project.cost_ledger?.total_tokens ?? 0` and `project.cost_ledger?.total_cost_usd ?? 0`.
   - The `events` array from `useStream` is already available — pass it through unchanged.
   - Import: `import CostIndicator from '@/components/CostIndicator';`.

9. **And** the cost indicator MUST remain visible during EVERY Chat View state that is currently rendered by `ChatInterface.tsx`: empty state (`!hasMessages` block), hydrated history, active execution (when `ExecutionStatusBlock` is rendered), spec preview shown, ticket cards shown, dev view open (`showDevView === true`). The footer is a sibling of the `flex-1 min-h-0 flex overflow-hidden` main content block — do NOT nest it inside the `showDevView ? 'w-[60%]' : 'w-full'` chat column, because that column re-flows and could push the footer out of view when Dev View opens. Baseline placement (outside both columns, direct child of the top-level flex container) is correct — preserve it.

10. **And** the story delivers ZERO backend changes. Story 6.1 already ships: (a) the SSE `token_update` event with the exact payload keys named in AC-2, (b) `cost_ledger` on the `ProjectDetail` response, (c) atomic ledger accumulation. Verification: at baseline `b873c0b`, `backend/api/routes/projects.py` `ProjectDetail` includes `cost_ledger: dict` (line 61) and `agents/token_tracker.record_llm_call` publishes `"token_update"` with the four-key payload (see `agents/token_tracker.py`). If either invariant does not hold on the working branch, STOP and open a review conversation before diverging from the story.

## Tasks / Subtasks

- [x] 1. Extend `useStream` to receive the `token_update` SSE event (AC: 3)
  - [x] 1.1 Open `frontend/lib/sse/useStream.ts`. Locate the `NAMED_EVENT_TYPES` const array (~line 13 at baseline).
  - [x] 1.2 Append the literal `'token_update'` as a new entry inside the `as const` array — order does not matter functionally; place it after `'tickets_generated'` for readability. No other change to this file.
  - [x] 1.3 Verify `npm run build` still type-checks (`NamedEventType` union widens automatically because the array is `as const`).

- [x] 2. Extend the `Project` TypeScript interface (AC: 7)
  - [x] 2.1 Open `frontend/lib/api/client.ts`. Add the optional `cost_ledger` field to the `Project` interface exactly as specified in AC-7.
  - [x] 2.2 No changes to `apiClient.getProject` — the field flows through the existing `fetchApi<Project>` typing.

- [x] 3. Create `frontend/components/CostIndicator.tsx` (AC: 4, 5)
  - [x] 3.1 Create the file. Header comment: single-line only per repo convention (`// Story 6.2: Cost Indicator — consumes token_update SSE events`).
  - [x] 3.2 Imports: `import React from 'react'; import type { StreamEvent } from '@/lib/sse/useStream';`. If `StreamEvent` is not currently exported from `useStream.ts`, add `export` to its interface declaration in Task 1 (verify at baseline — it IS exported per `useStream.ts` line 5).
  - [x] 3.3 Define `CostIndicatorProps` and the `TokenUpdatePayload` local type per AC-4 and AC-5.
  - [x] 3.4 Implement the last-`token_update` scan inline in the render body (no `useMemo` needed — the list is small; premature optimisation violates the "only make changes directly requested" rule). Fall-back rules per AC-5.
  - [x] 3.5 Number formatting: `const nf = new Intl.NumberFormat('en-US');` at module scope (a single formatter reused per render is fine and avoids reallocation).
  - [x] 3.6 Render the `<footer>` with the classes, aria attributes, and content structure enumerated in AC-4. Reuse the shadcn/tailwind tokens the placeholder currently uses (`border-t border-border bg-muted/30 px-4 py-1.5 text-xs font-mono text-muted-foreground`) — do NOT introduce a new colour or shadow token.
  - [x] 3.7 Export the component as default.

- [x] 4. Wire `CostIndicator` into `ChatInterface.tsx` (AC: 1, 6, 8, 9)
  - [x] 4.1 Add the import: `import CostIndicator from '@/components/CostIndicator';`.
  - [x] 4.2 Add the two new `useState` hooks near the existing state declarations (grouped with `jiraConfigured` for cohesion): `initialTotalTokens` and `initialTotalCostUsd`, both `number`, both defaulting to `0`.
  - [x] 4.3 Inside `loadProject`, after `setJiraConfigured`, add: `const ledger = project.cost_ledger ?? {}; setInitialTotalTokens(ledger.total_tokens ?? 0); setInitialTotalCostUsd(ledger.total_cost_usd ?? 0);`. Preserve existing chat_history hydration.
  - [x] 4.4 Delete the current static `<footer>…</footer>` block at the bottom of the return tree (grep for `Cost Indicator Footer` — the comment above it — to locate).
  - [x] 4.5 Replace with `<CostIndicator events={events} initialTotalTokens={initialTotalTokens} initialTotalCostUsd={initialTotalCostUsd} />`. Placement MUST remain a direct child of the outermost `<div className="flex flex-col h-full relative">` — do NOT move it inside the chat column (AC-9).

- [x] 5. Build + lint verification (AC: 10)
  - [x] 5.1 Run `npm run build` from `frontend/`. Confirm zero TypeScript errors and zero new lint warnings.
  - [x] 5.2 Run `npm run lint` from `frontend/`. Confirm clean.
  - [x] 5.3 Manual verification path (documented for reviewer, no automation required — matches the Story 2.3 / 2.4 convention: "component tests or manual verification"):
    (a) Start backend + frontend locally. Open a fresh project's Chat View — assert both rows read `0 tokens · $0.00` and the footer is visible in every screen state (empty, hydrated, dev-view open).
    (b) Trigger an LLM call (e.g. send any chat message that hits `/projects/{id}/chat` → the router agent turn → Story 6.1's `tracked_ainvoke`). Observe the footer update within one SSE tick — no reload.
    (c) Refresh the browser. Assert Total row reflects DB-persisted `cost_ledger.total_tokens`/`total_cost_usd` and Session row resets to zero.
  - [x] 5.4 Backend regression: no backend files are modified in this story. Nonetheless run `pytest tests/ -q` and confirm the Story 6.1 baseline of 151 tests still passes — this proves the story is purely frontend-additive.

- [x] 6. Cross-check story boundary (AC: 10)
  - [x] 6.1 Confirm `agents/token_tracker.py` at baseline emits the SSE event with EXACTLY the four keys `session_tokens`, `session_cost_usd`, `total_tokens`, `total_cost_usd`. If a rename has occurred (e.g. `session_cost` vs `session_cost_usd`) STOP and file a correction against Story 6.1 rather than adapting the frontend to a divergent payload.
  - [x] 6.2 Confirm `ProjectDetail` in `backend/api/routes/projects.py` still exposes `cost_ledger: dict`. If it has been narrowed or removed, STOP — a schema regression in Story 6.1 must be fixed first.

## Dev Notes

### Architecture patterns & constraints (must obey)

- **AD-4 (LLM-as-last-resort) — frontend corollary:** the client MUST NOT compute cost, price-per-token, or any arithmetic beyond formatting. All numbers come from the SSE payload or the pre-populated ledger. No `costPerToken * n` on the client — that logic lives once, in `agents/token_tracker.compute_cost_usd`.
- **AD-7 (Streaming over polling):** the Cost Indicator subscribes to `token_update` on the shared `EventSource` opened by `useStream`. No `setInterval`, no `fetch` refresh loop, no revalidation hook. The existing `EventSource` auto-reconnects (see `useStream.onerror` — leaves reconnect to the browser when `readyState === CONNECTING`); the Cost Indicator inherits this reliability for free.
- **AD-13 (Config from env vars) — not applicable client-side:** the only price knob is `COST_PER_1K_TOKENS` and it lives on the backend (Story 6.1). Do not surface it in the frontend and do not read `process.env.NEXT_PUBLIC_COST_PER_1K_TOKENS` — that would duplicate the source of truth.
- **`{cost-indicator}` design-system token (DESIGN.md):** mono font, muted surface, always visible, two rows, `rounded/sm` context. The story MUST reuse existing shadcn tokens (`border-border`, `bg-muted/30`, `text-muted-foreground`, `font-mono`, `text-xs`) — do not introduce new tokens. Ref: DESIGN.md line 206 (`rounded/sm — badges, cost indicator, small tags, file tree items`) and line 227 (`{cost-indicator}` component spec).
- **project-context.md — "LLM content responses can be a list":** does NOT apply here (frontend does not touch LangChain messages).
- **project-context.md — env var access:** does NOT apply (no new env var).

### Source tree components to touch

**NEW files:**
- `frontend/components/CostIndicator.tsx`

**MODIFIED files (read fully before changing):**
- `frontend/lib/sse/useStream.ts` — one-line addition to `NAMED_EVENT_TYPES`; confirm `StreamEvent` is exported (it is — line 5).
- `frontend/lib/api/client.ts` — extend `Project` interface with optional `cost_ledger` field.
- `frontend/app/projects/[id]/ChatInterface.tsx` — add two state hooks, hydrate them in `loadProject`, replace static footer with `<CostIndicator …/>`. This file is 300+ lines and touches many stories — read from top to bottom before editing to avoid clobbering Story 2.3 / 3.3 / 3.4 / 4.1 logic that surrounds the edit points.

**DO NOT TOUCH:**
- `agents/token_tracker.py`, `backend/store/project_store.py`, `backend/api/sse.py`, `backend/api/routes/projects.py` — Story 6.1 already delivered these. Any change here is out of scope.
- `frontend/lib/sse/useStream.ts` return shape — do not add new returned values (e.g. `latestTokenUpdate`). The `events` array is sufficient and matches the pattern used by `ExecutionStatusBlock` and the spec/ticket derivations already in `ChatInterface.tsx`.
- `frontend/components/ExecutionStatusBlock.tsx`, `TicketCard.tsx`, `TicketCardList.tsx`, `Sidebar.tsx` — the Cost Indicator is orthogonal to all of them.
- The static mockup HTML under `_bmad-output/planning-artifacts/ux-designs/…/mockups/` — these are frozen references. Do NOT try to reuse the raw class names (`.cost-indicator`, `.cost-row`) from those mockups — the live app uses shadcn/tailwind, not raw CSS classes.

### Testing standards summary

- The frontend has NO test runner installed at baseline (`package.json` has no `jest` / `vitest` / `@testing-library/*` deps — verified). Every prior frontend story (2.1 through 4.5) accepts "component tests or manual verification" as the test artefact. Story 6.2 follows the same convention: the test artefacts are (a) `npm run build` passes with zero TS errors, (b) `npm run lint` passes, (c) manual verification per Task 5.3 (three-step recipe). Do NOT introduce a test framework in this story — that is a project-wide decision worth its own story, not a side effect of a footer widget.
- The backend regression proof for this story is the existing `pytest tests/ -q` suite — it must still show the Story 6.1 count (151 pass, 0 new warnings). This is Task 5.4.

### Read files being modified — critical current state

- `frontend/lib/sse/useStream.ts` (baseline): a single `EventSource` per project, `NAMED_EVENT_TYPES` is `as const` so widening the literal union is automatic. `events` accumulates every event (typed and default), so any event with `type === "token_update"` will surface once the listener is registered. `StreamEvent` is exported (line 5) — CostIndicator can import the type without a re-export shim.
- `frontend/app/projects/[id]/ChatInterface.tsx` (baseline): already uses the "filter events, take last" idiom TWICE (for `spec_stored` line ~60 and `tickets_generated` line ~72). CostIndicator MUST follow the same idiom in its own component body — do NOT hoist the derivation into `ChatInterface` state (that would trigger an extra re-render per SSE tick without gain). The bottom of the JSX contains the current static footer (search for `{/* Cost Indicator Footer */}` — that exact comment is present at baseline). Replace the whole `<footer>…</footer>` block, not just the numbers.
- `frontend/lib/api/client.ts` (baseline): the `Project` interface at the top of the file is used everywhere the SDK returns a project. Widening it with an OPTIONAL field is safe — all callers already access via optional chaining or check for presence.
- `backend/api/routes/projects.py::ProjectDetail` (baseline line 61): includes `cost_ledger: dict`. No optionality — an empty dict `{}` is the default per DB schema.
- `agents/token_tracker.py` (baseline, from Story 6.1): the SSE publish call is guarded in try/except so a missing subscriber is silent — the frontend has no way to detect "no subscriber" from the server. That is fine; the browser's `EventSource` will simply see no event.

### Previous story intelligence (Story 6.1 — reviewed)

- Story 6.1 established: `session_id` is generated in `SupervisorAgent.run_tickets` (not `execute` — spec text used the older name; actual method is `run_tickets`). `SupervisorAgent.process_chat` also generates a lazy `self._chat_session_id`. Either entry point emits `token_update` after every LLM call. The frontend does NOT need to know the `session_id` — it just consumes the last event.
- Story 6.1 published `token_update` from a `record_llm_call` that catches all `publish_event` exceptions and logs at WARNING. So if the SSE queue is momentarily missing (`SSEManager` unregistered), no crash, no retry — the next call will publish. Consequence for the frontend: reconnect gaps produce a "missed one tick" experience — acceptable per FR-25 ("updates after every event"), and covered by AC-6's rule "cumulative Total row is pre-populated from DB" (any missed tick is rebuilt from the ledger on next refresh).
- Story 6.1 renamed nothing else on the payload — the four keys are stable.
- Story 6.1 test convention (unit tests colocated with the module, mocks at the import site) does NOT translate to the frontend for this story: the frontend has no test framework, and adding one is out of scope (see Testing standards summary).

### External context / library specifics

- **`Intl.NumberFormat("en-US")`**: standard ECMA-402 API — supported in every browser Next.js 16 targets. Safe to instantiate at module scope in a client component; no SSR concerns because this component is a child of an already-`"use client"` tree (`ChatInterface.tsx` starts with `"use client"`).
- **React 19 / Next.js 16**: no new hook required. The `events` prop is a stable identity reference from `useStream`'s `useState`, so React's default re-render on prop change is sufficient. Do NOT wrap in `React.memo` — the parent re-renders on every event anyway (that is the design of the shared `events` array); memoisation would only add hash overhead.
- **shadcn/tailwind**: the project uses shadcn (`components.json` at `frontend/`). All colour and spacing values MUST resolve to existing shadcn tokens. `border-border`, `bg-muted/30`, `text-muted-foreground`, `text-foreground` are all already in the theme (see `frontend/app/globals.css`).
- **`EventSource` reconnect semantics**: `useStream` deliberately does NOT set state to disconnected on `readyState === CONNECTING` (comment: "EventSource will auto-reconnect"). If a `token_update` fires during a reconnect gap it is lost — but the next `token_update` carries the full `total_tokens` and `total_cost_usd`, so the display self-heals on the next call. No compensating logic required.

### Project Structure Notes

- Layout matches the ARCHITECTURE-SPINE structural seed for the frontend: shared UI in `frontend/components/`, page-scoped UI under `frontend/app/projects/[id]/`. CostIndicator is a shared, project-agnostic presentational component — belongs in `frontend/components/` alongside `Sidebar.tsx`, `TicketCard.tsx`, `TicketCardList.tsx`. Do NOT place it under `frontend/app/projects/[id]/` — that folder is reserved for page-composition components (`ChatInterface`, `ExecutionStatusBlock`, `page.tsx`).
- No conflicts detected. The `cost_ledger` column already exists (Story 6.1); the SSE event pipe already exists (Story 6.1); the `Project` type already flows through `apiClient.getProject`.

### References

- [Epic 6 / Story 6.2 spec](../planning-artifacts/epics.md#story-62-cost-display-in-chat-view)
- [PRD FR-25 — Token Consumption and Cost Display](../planning-artifacts/prds/prd-ai-consultant-2026-07-08/prd.md#fr-25-token-consumption-and-cost-display)
- [UX Experience — Token Consumption Display](../planning-artifacts/ux-designs/ux-ai-consultant-2026-07-09/EXPERIENCE.md#token-consumption-display)
- [UX Design System — `{cost-indicator}` component + `.cost-row` mono style](../planning-artifacts/ux-designs/ux-ai-consultant-2026-07-09/DESIGN.md)
- [UX mockup — Chat View execution state with Cost Indicator](../planning-artifacts/ux-designs/ux-ai-consultant-2026-07-09/mockups/chat-view-execution.html)
- [Story 6.1 — token tracker + SSE `token_update` producer](./6-1-token-consumption-tracking-and-cost-ledger.md)
- [`frontend/lib/sse/useStream.ts` — NAMED_EVENT_TYPES pattern](../../frontend/lib/sse/useStream.ts)
- [`frontend/lib/api/client.ts` — Project interface](../../frontend/lib/api/client.ts)
- [`frontend/app/projects/[id]/ChatInterface.tsx` — Chat View host, static footer to replace](../../frontend/app/projects/%5Bid%5D/ChatInterface.tsx)
- [`backend/api/routes/projects.py` — ProjectDetail.cost_ledger exposure](../../backend/api/routes/projects.py)
- [`agents/token_tracker.py` — `token_update` SSE payload producer](../../agents/token_tracker.py)
- [`_bmad-output/project-context.md` — global rules](../project-context.md)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (GitHub Copilot)

### Debug Log References

- `npm run build` (frontend/): compiled successfully, TypeScript passes, static pages generated (4/4).
- `npm run lint` (frontend/): 12 pre-existing problems (9 errors, 3 warnings), all in files not touched by this story or on lines untouched by this story's edits (`ExecutionStatusBlock.tsx:120`, `useStream.ts:40`, `page.tsx:7-11`, `ChatInterface.tsx:11/19/274`, `client.ts:80/86`, `TicketCardList.tsx:73`). Zero new issues introduced.
- `pytest tests/ -q`: 151 passed, 6 pre-existing warnings — matches Story 6.1 baseline, confirming zero backend regression.
- Cross-check verified at baseline commit `b873c0b`: `agents/token_tracker.py` publishes `token_update` with exact keys `session_tokens`, `session_cost_usd`, `total_tokens`, `total_cost_usd` (lines 140-146); `backend/api/routes/projects.py::ProjectDetail.cost_ledger: dict` present (line 61).

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created.
- Implementation is purely frontend-additive: three modified files + one new file. Zero backend changes.
- `useStream.ts`: appended `'token_update'` to `NAMED_EVENT_TYPES`. `StreamEvent` already exported at line 7 (baseline had it at line 5 as noted in Dev Notes — line shift due to new comment lines above).
- `client.ts`: extended `Project` interface with optional `cost_ledger` field (all sub-keys optional to reflect the `{}` default from `backend/store/database.py`).
- `CostIndicator.tsx` (new): consumes `events` prop; derives four live values by scanning the last `token_update` event with defensive `?? 0` fallbacks. When no `token_update` has arrived, session values are 0 and total values come from `initialTotal*` props (AC-5, AC-6). Uses `React.JSX.Element` (React 19 removed the global `JSX` namespace; the type moved to `React.JSX`). Uses `role="status"` + `aria-live="polite"` + full `aria-label` per AC-4 / EXPERIENCE.md line 163.
- `ChatInterface.tsx`: added import, two `useState` hooks (`initialTotalTokens`, `initialTotalCostUsd`), ledger read in `loadProject`, replaced static footer with `<CostIndicator …/>` at the outermost flex-column level so it remains visible in every state including `showDevView` (AC-9). Preserved the missing `</div>` closing the main content flex-container — verified in the render tree.
- The client performs zero cost arithmetic; it consumes `session_cost_usd` and `total_cost_usd` verbatim (AD-4 corollary). Formatting only: `Intl.NumberFormat('en-US')` for token counts, `toFixed(2)` for USD.
- Backend regression: 151 tests pass, unchanged from Story 6.1 baseline.

### File List

**Modified:**
- `frontend/lib/sse/useStream.ts`
- `frontend/lib/api/client.ts`
- `frontend/app/projects/[id]/ChatInterface.tsx`

**New:**
- `frontend/components/CostIndicator.tsx`

### Change Log

| Date       | Change                                                                                              |
|------------|-----------------------------------------------------------------------------------------------------|
| 2026-09-01 | Story 6.2 implemented: `CostIndicator` component wired to `token_update` SSE event and hydrated from `cost_ledger` on mount. Static placeholder footer replaced. Zero backend changes; 151 backend tests still pass. |
