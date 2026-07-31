---
baseline_commit: d23c04e3a202c28cbef352651d6ba638fcc60f7c
---

# Story 2.4: Execution Status Block

Status: review

## Story

As a user,
I want a live execution status block in the Chat View showing the current ticket, elapsed time, and the full execution queue state,
so that I always know what the agent is working on without scrolling through log output.

## Acceptance Criteria

**AC-1:** Given an execution is active for the current project — When the execution status block renders — Then it shows the current ticket name and elapsed time (updated every second) — And it shows all tickets in the Execution Queue with their status: done ✓, active ⟳, pending ○ — And the queue state updates in real time as SSE events arrive — no polling.

**AC-2:** Given no execution is active — When the Chat View is open — Then the execution status block is hidden (not an empty placeholder).

**AC-3:** Given a ticket transitions from active to done — When the status event arrives — Then the queue display updates within the same SSE event cycle — no additional API call required.

## Tasks / Subtasks

- [x] Create `ExecutionStatusBlock.tsx` Client Component (AC: 1, 2, 3)
  - [x] Define `ExecutionStatus` and `QueueTicket` TypeScript interfaces
  - [x] Implement SSE event listener for `execution_start`, `execution_tick`, `ticket_done`, `execution_end` event types via the existing `useStream` hook
  - [x] Implement elapsed-time counter using `setInterval` cleared on unmount/execution-end
  - [x] Render queue list with ✓ / ⟳ / ○ status icons
  - [x] Hide block entirely when no execution is active (AC-2)
- [x] Create `ExecutionStatusBlock.module.css` with premium styling
  - [x] Distinct panel appearance (dark/accent background) to visually separate from chat messages
  - [x] Animated spinner for active ticket (CSS `@keyframes spin`)
  - [x] Green check for done, muted circle for pending
- [x] Extend `useStream.ts` to support named SSE event types (AC: 1, 3)
  - [x] The current hook only handles `onmessage` (default/unnamed events). Add `addEventListener` for named events (`execution_start`, `ticket_done`, `execution_end`, `execution_tick`) — **do NOT break existing `message` event handling**
- [x] Mount `ExecutionStatusBlock` in `ChatInterface.tsx` above the message list
  - [x] Pass `events` array from `useStream` — do not introduce a second SSE connection
- [x] Ensure zero TypeScript errors (`tsc --noEmit`)

## Dev Notes

### SSE Event Contract (backend-defined, frontend-consumed)

The backend publishes events via `publish_event(project_id, event_type, data)` in `backend/api/sse.py`. The SSE wire format is:
```
event: <event_type>
data: <json>

```

The frontend `EventSource` distinguishes named events via `addEventListener(eventType, handler)`. The current `useStream.ts` only wires `onmessage` which catches **unnamed** (default) events. Named events (those with an `event:` field) are **ignored** by `onmessage` — this is a Web spec behaviour that the dev agent must not overlook.

**Expected event types for story 2.4** (to be emitted by Epic 5's execution engine — but the frontend must be ready now):

| Event type | Data shape | Frontend action |
|---|---|---|
| `execution_start` | `{ tickets: [{id, name, status}] }` | Populate queue; start elapsed timer |
| `execution_tick` | `{ active_ticket_id, elapsed_seconds }` | Update elapsed display |
| `ticket_done` | `{ ticket_id }` | Mark ticket ✓ in queue |
| `execution_end` | `{}` | Clear status block; stop timer |

> **Important:** Epic 5 (the agent execution engine) is NOT built yet. For this story, build the consumer-side only. The status block will be invisible during manual testing unless the developer triggers test events manually (e.g., via `curl -N` to the SSE endpoint or a simple backend test route). Do not invent a backend execution trigger — that is Epic 5's scope.

### useStream.ts — Required Extension (MODIFY, not replace)

Current state: only wires `eventSource.onmessage` which catches unnamed events. Add named-event listeners without removing the existing `onmessage` handler. Pattern:

```typescript
// Existing — keep as-is
eventSource.onmessage = (event) => { ... };

// Add named event listeners
const namedTypes = ['execution_start', 'execution_tick', 'ticket_done', 'execution_end'];
namedTypes.forEach(type => {
  eventSource.addEventListener(type, (event: MessageEvent) => {
    try {
      const parsedData = JSON.parse(event.data);
      setEvents(prev => [...prev, { type, data: parsedData, timestamp: new Date().toISOString() }]);
    } catch (err) {
      console.error(`Failed to parse SSE data for event type "${type}"`, err);
    }
  });
});
```

The cleanup return must also remove these listeners to prevent memory leaks.

### ExecutionStatusBlock — Component Design

- **Pure consumer**: receives `events: StreamEvent[]` as a prop. Derives execution state by scanning events in order. No extra `useState` for SSE — just derive from props.
- **Elapsed timer**: when `executionActive` transitions to `true`, start a `setInterval(1000)` updating a local `elapsedSeconds` state. Clear the interval when `executionActive` becomes `false` or component unmounts.
- **Mount location**: inside `ChatInterface`, **above** the `messageList` div, inside the `chatContainer`. This keeps it part of the same scrollable surface per FR-22 (hybrid chat + structured components in chronological order on the same surface).

```tsx
// Rough skeleton — implement properly
export default function ExecutionStatusBlock({ events }: { events: StreamEvent[] }) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  // Derive state from events (scan in order)
  const executionState = useMemo(() => deriveExecutionState(events), [events]);

  useEffect(() => {
    if (!executionState.active) return;
    setElapsedSeconds(0);
    const id = setInterval(() => setElapsedSeconds(s => s + 1), 1000);
    return () => clearInterval(id);
  }, [executionState.active]);

  if (!executionState.active) return null; // AC-2: hidden when no execution

  return ( /* render block */ );
}
```

### Architecture Compliance

- **AD-7 (Streaming over polling):** Queue updates must come from SSE events, not polling. No `setInterval` to re-fetch from backend.
- **AD-4 (LLM-as-last-resort):** No LLM calls from the status block. Pure SSE consumer.
- **AD-5 (Project isolation):** `useStream(projectId)` already scopes events to the project — do not bypass this by hardcoding project IDs.
- **AD-10 (Frontend-backend boundary):** No direct DB or backend-internal calls. SSE only.
- **FR-22 (Hybrid surface):** The status block is a structured component rendered inline within the chat surface — same scrollable container as chat messages.
- **FR-23:** This story IS the implementation of FR-23.

### File Structure

```text
frontend/
  app/
    projects/
      [id]/
        ChatInterface.tsx          ← MODIFY: mount ExecutionStatusBlock
        ExecutionStatusBlock.tsx   ← NEW
        ExecutionStatusBlock.module.css ← NEW
        page.tsx                   ← no change
        page.module.css            ← MODIFY: add panel styles if needed
  lib/
    sse/
      useStream.ts                 ← MODIFY: add named event listeners
```

### Previous Story Intelligence (from 2-3)

- **`ChatInterface.tsx`** is a `"use client"` component. `ExecutionStatusBlock` must also be `"use client"` since it uses `useState`/`useEffect`.
- **`useStream(projectId)`** returns `{ events, isConnected, error }`. Pass `events` down to `ExecutionStatusBlock` as a prop — do not call `useStream` a second time inside the block (would open two SSE connections to the same endpoint).
- **CSS Modules** are the established styling method. Use `ExecutionStatusBlock.module.css`, not inline styles or globals.
- The `page.tsx` in `[id]/` is an `async` Server Component — **do not add hooks there**. All interactive additions go into `ChatInterface.tsx` or new Client Components.
- ESLint and `tsc --noEmit` are the quality gates. Fix all errors before marking done.

### Project Context Reference

See [`_bmad-output/project-context.md`](../../project-context.md) for overall rules. Key reminders:
- `NEXT_PUBLIC_API_URL` controls backend URL — never hardcode `localhost`.
- TypeScript strict mode is enabled — all types must be explicit.
- No TailwindCSS — CSS Modules only.

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (Thinking)

### Debug Log References

(none — clean implementation, no debug sessions required)

### Completion Notes List

- Implemented `deriveExecutionState()` as a pure function scanning events in order; used in `useMemo` to satisfy the "pure consumer" requirement from Dev Notes.
- `useStream.ts` extended with `NAMED_EVENT_TYPES` constant and per-type `addEventListener` handlers stored in `namedHandlers` array. Cleanup function removes all named listeners before closing the EventSource, preventing memory leaks.
- `ExecutionStatusBlock.tsx` returns `null` when `executionState.active === false` (AC-2 — no empty placeholder).
- Elapsed timer uses a single `setInterval(1000)` keyed on `executionState.active`. Resets to 0 on each new execution start.
- Fixed pre-existing TypeScript strict-mode error in `ChatInterface.tsx`: `e.data` was typed `unknown` but accessed as `.content` without a type guard — replaced with `in` operator + `Record<string, unknown>` cast.
- `tsc --noEmit` passes with zero errors after all changes.
- No second `useStream` call introduced in `ExecutionStatusBlock` — events array passed as prop from `ChatInterface`.
- Architecture decisions complied: AD-4 (no LLM calls), AD-5 (project-scoped SSE via existing hook), AD-7 (SSE not polling), AD-10 (no direct DB calls), FR-22/FR-23 (status block inline above messageList in same container).

### File List

- [MODIFY] `frontend/lib/sse/useStream.ts`
- [MODIFY] `frontend/app/projects/[id]/ChatInterface.tsx`
- [NEW] `frontend/app/projects/[id]/ExecutionStatusBlock.tsx`
- [NEW] `frontend/app/projects/[id]/ExecutionStatusBlock.module.css`

### Change Log

- 2026-07-15: Implemented story 2-4 Execution Status Block. Extended `useStream.ts` with named SSE event listeners. Created `ExecutionStatusBlock.tsx` (pure SSE consumer with elapsed timer, queue rendering, AC-2 null return). Created `ExecutionStatusBlock.module.css` (dark accent panel, animated spinner, status icons). Mounted block in `ChatInterface.tsx` above message list. Fixed pre-existing TS strict error in ChatInterface. All `tsc --noEmit` checks pass.
