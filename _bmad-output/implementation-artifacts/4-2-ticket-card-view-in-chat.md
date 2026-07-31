# Story 4.2: Ticket Card View in Chat

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the generated tickets displayed as structured inline cards in the Chat View -- each showing title, description, acceptance criteria, and dependencies,
So that I can review the full implementation plan before committing to it.

## Acceptance Criteria

1. **Given** a `tickets_generated` SSE event is received via the SSE stream
   **When** the Chat View renders
   **Then** each ticket appears as an inline card in the chat flow (not in a separate panel)
   **And** each card displays: title, description, acceptance criteria, `blocking` list, and `blocked_by` list
   **And** the cards appear in dependency-resolved order (blockers before dependents)
   **And** action buttons (Accept, revision text field) are visible on each card
   **And** displaying the card view does **not** trigger any LLM call

## Tasks / Subtasks

- [ ] Task 1: Register `tickets_generated` as a named SSE event in `useStream.ts` (AC: 1)
  - [ ] Add `'tickets_generated'` to the `NAMED_EVENT_TYPES` constant array in `frontend/lib/sse/useStream.ts`
- [ ] Task 2: Create `TicketCard` component (AC: 1)
  - [ ] Create `frontend/components/TicketCard.tsx`
  - [ ] Props: `ticket: Ticket`, `onAccept: (id: string) => void`, `onRevise: (id: string, instruction: string) => void`
  - [ ] Render: title, description, acceptance criteria, blocking list, blocked_by list
  - [ ] Include Accept button (calls onAccept, no LLM) and revision text field with Submit
  - [ ] Use existing shadcn/ui: Button, Textarea, Badge from @/components/ui/*
  - [ ] Apply project CSS tokens (see Design Tokens section)
- [ ] Task 3: Create `TicketCardList` component (AC: 1)
  - [ ] Create `frontend/components/TicketCardList.tsx`
  - [ ] Props: `tickets: Ticket[]`, `projectId: string`
  - [ ] Sort tickets in dependency-resolved order (topological sort -- blockers before dependents)
  - [ ] Wire `onAccept` to call `PATCH /projects/{projectId}/tickets/{ticketId}` with `{ status: "Accepted" }` -- zero LLM calls
  - [ ] Wire `onRevise` to stub only (Story 4.3 scope) -- show "revision coming soon" or call endpoint if it exists
- [ ] Task 4: Integrate `TicketCardList` into `ChatInterface.tsx` (AC: 1)
  - [ ] Detect `tickets_generated` events in `ChatInterface.tsx` via events from useStream
  - [ ] Extract `tickets` array from `event.data`
  - [ ] Render `<TicketCardList>` inline in the chat message flow (chronological, not in a panel)
  - [ ] Store ticket list in ChatInterface state via useState<Ticket[]>
  - [ ] Zero LLM calls on render
- [ ] Task 5: Add API client helpers (AC: 1)
  - [ ] Add `acceptTicket(projectId, ticketId)` and `reviseTicket(projectId, ticketId, instruction)` to `frontend/lib/api/client.ts`
- [ ] Task 6: Add backend PATCH endpoint and store function (AC: 1)
  - [ ] Add `PATCH /projects/{project_id}/tickets/{ticket_id}` to `backend/api/routes/projects.py`
  - [ ] Add `update_ticket_status()` to `backend/store/project_store.py`
- [ ] Task 7: Add tests (AC: 1)
  - [ ] Add `tests/test_ticket_card_view.py` using pytest
  - [ ] Test PATCH endpoint: valid body -> 200, mock execute

## Dev Notes

### Ticket Interface (TypeScript)

Define in `frontend/components/TicketCard.tsx` and re-export from `frontend/lib/api/client.ts`:

```ts
export interface Ticket {
  id: string;                  // UUID string
  title: string;
  description: string;
  acceptance_criteria: string;
  status: 'Pending' | 'Accepted' | 'In Progress' | 'Done' | 'Error';
  blocking: string[];          // list of ticket UUIDs this ticket blocks
  blocked_by: string[];        // list of ticket UUIDs that block this ticket
}
```

Shape matches exactly what Story 4.1 stores in `ticket_history` JSONB.

### SSE Event Shape from Story 4.1

The `tickets_generated` SSE event (published by backend via `SSEManager.get_instance().publish(project_id, "tickets_generated", json_payload)`) carries:

```json
{
  "tickets": [
    {
      "id": "<uuid>",
      "title": "...",
      "description": "...",
      "acceptance_criteria": "...",
      "status": "Pending",
      "blocking": [],
      "blocked_by": []
    }
  ]
}
```

Parse via: `const { tickets } = event.data as { tickets: Ticket[] }`.

### Dependency-Resolved Ordering (Topological Sort)

Implement purely in frontend, no backend/LLM call:

```ts
function topoSort(tickets: Ticket[]): Ticket[] {
  const map = new Map(tickets.map(t => [t.id, t]));
  const visited = new Set<string>();
  const result: Ticket[] = [];

  function visit(id: string) {
    if (visited.has(id)) return;
    visited.add(id);
    const ticket = map.get(id);
    if (!ticket) return;
    for (const depId of ticket.blocked_by) {
      visit(depId);
    }
    result.push(ticket);
  }

  tickets.forEach(t => visit(t.id));
  return result;
}
```

### Backend: PATCH Ticket Endpoint

Add to `backend/api/routes/projects.py`:

```python
class TicketStatusUpdate(BaseModel):
    status: str

@router.patch("/projects/{project_id}/tickets/{ticket_id}", status_code=200)
async def update_ticket_status_endpoint(
    project_id: uuid.UUID,
    ticket_id: str,
    body: TicketStatusUpdate,
) -> dict:
    await project_store.update_ticket_status(str(project_id), ticket_id, body.status)
    return {"ok": True}
```

Add to `backend/store/project_store.py`:

```python
async def update_ticket_status(project_id: str, ticket_id: str, status: str) -> None:
    """Update the status field of a specific ticket in ticket_history JSONB array."""
    pool = database.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE projects
            SET ticket_history = (
                SELECT jsonb_agg(
                    CASE WHEN t->>'id' = $2
                    THEN t || jsonb_build_object('status', $3)
                    ELSE t
                    END
                )
                FROM jsonb_array_elements(ticket_history) AS t
            )
            WHERE id = $1
            """,
            project_id, ticket_id, status,
        )
```

### Design Tokens to Use

From `frontend/app/globals.css @theme`:

| Token | Value | Use for |
|-------|-------|---------|
| `bg-muted` | #1f2937 | Card background |
| `border-border` | #1f2937 | Card border |
| `text-foreground` | #ffffff | Card title/body |
| `text-muted-foreground` | #9ca3af | Labels, secondary text |
| `bg-primary` | #4F46E5 | Accept button |
| `text-success` | #10B981 | Accepted status badge |
| `bg-log-surface` | #0D1117 | Inner code/AC sections |
| `rounded-xl` | -- | Card border radius |

Use Tailwind utility classes + shadcn/ui components ONLY. No inline `style={}`, no new CSS.

### Architectural Constraints (Non-Negotiable)

- **AD-4:** Accept button -> PATCH call -> zero LLM. Card render -> zero LLM.
- **AD-7:** Cards appear via `tickets_generated` SSE event, NOT by polling `GET /projects/{id}`.
- **AD-9:** All new backend route handlers must be `async def`.
- **AD-10:** All state mutations go through REST endpoints. No direct DB from frontend.
- **AD-13:** Frontend reads `process.env.NEXT_PUBLIC_API_URL` only (already done in `client.ts`).

### Files to Create / Modify

| File | Action | What changes |
|------|--------|--------------|
| `frontend/lib/sse/useStream.ts` | UPDATE | Add 'tickets_generated' to NAMED_EVENT_TYPES |
| `frontend/components/TicketCard.tsx` | NEW | TicketCard component + Ticket interface |
| `frontend/components/TicketCardList.tsx` | NEW | TicketCardList with topoSort + Accept wiring |
| `frontend/lib/api/client.ts` | UPDATE | Add Ticket type + acceptTicket/reviseTicket helpers |
| `frontend/app/projects/[id]/ChatInterface.tsx` | UPDATE | Detect tickets_generated, render <TicketCardList> inline |
| `backend/api/routes/projects.py` | UPDATE | Add PATCH /projects/{id}/tickets/{ticket_id} |
| `backend/store/project_store.py` | UPDATE | Add update_ticket_status() function |
| `tests/test_ticket_card_view.py` | NEW | pytest tests for PATCH endpoint |

### ChatInterface.tsx Integration Pattern

Follow the exact same pattern as the `spec_stored` handler (lines 29-40 and 176-216). Add:

```tsx
const [tickets, setTickets] = useState<Ticket[]>([]);

// Detect tickets_generated SSE event
useEffect(() => {
  const latestTicketsEvent = events
    .filter(ev => ev.type === 'tickets_generated')
    .slice(-1)[0];
  if (latestTicketsEvent) {
    const data = latestTicketsEvent.data as { tickets?: Ticket[] };
    if (data?.tickets) {
      setTickets(data.tickets);
    }
  }
}, [events]);
```

Render `<TicketCardList tickets={tickets} projectId={projectId} />` inline in the chat scrollable div, after the `specPreview` card and before the `messages` list. Only render when `tickets.length > 0`.

### Existing Patterns to Extend (Do NOT Re-create)

- **Named SSE events:** Already handled in `useStream.ts` via `NAMED_EVENT_TYPES` array. Just append `'tickets_generated'` -- no other changes to the hook.
- **Inline spec card pattern:** The `specPreview` card (ChatInterface.tsx lines 176-216) is the established pattern for inline structured components in the chat flow. Replicate its container/border style.
- **`apiClient` pattern:** `frontend/lib/api/client.ts` exports typed fetch helpers. Add ticket methods with the same `fetchApi<T>()` call.
- **shadcn/ui card:** `frontend/components/ui/card.tsx` exists. Use `<Card>`, `<CardHeader>`, `<CardContent>`, `<CardTitle>` -- don't build from raw divs.
- **Test mock pattern:** See `tests/test_projects_create.py` for `make_mock_pool()` + `AsyncMock`. Set `DATABASE_URL` env var before importing backend. Mock `conn.execute = AsyncMock(return_value=None)` for the PATCH endpoint.

### Regression Preservation -- Must Not Break

- `spec_stored` event handling and `specPreview` card in `ChatInterface.tsx`
- `ExecutionStatusBlock` and its SSE events (`execution_start`, `execution_tick`, `ticket_done`, `execution_end`)
- All existing `NAMED_EVENT_TYPES` in `useStream.ts`
- `GET /projects/{project_id}` response shape (no changes to get_project)
- `POST /projects` and `GET /projects` endpoints

### Story 4.1 Dependency

Story 4.1 (`4-1-ticket-generation-from-spec`) must be implemented before E2E testing this story. Unit tests can mock the SSE event and PATCH endpoint independently.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.2]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md]
- [Source: _bmad-output/project-context.md#Critical Implementation Rules]
- [Existing: frontend/lib/sse/useStream.ts]
- [Existing: frontend/app/projects/[id]/ChatInterface.tsx]
- [Existing: frontend/lib/api/client.ts]
- [Existing: backend/api/routes/projects.py]
- [Existing: backend/store/project_store.py]

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
