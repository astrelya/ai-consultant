---
baseline_commit: a4a3b0bcf5ba42f43aac42feb819144788d799ed
---
# Story 4.3: Inline Ticket Edit and Accept

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want to edit any field on a ticket card directly and accept it without an LLM call, or submit a revision instruction that regenerates only the affected tickets,
So that I maintain full control over the plan with minimal AI overhead on simple edits.

## Acceptance Criteria

1. **Given** a ticket card is displayed in the Chat View
   **When** I edit any field (title, description, or AC) directly in the card and click Accept
   **Then** `PATCH /projects/{id}/tickets/{ticket_id}` is called with the edited fields — no LLM call is made
   **And** the card updates in place with the saved values

2. **Given** I type a revision instruction in the card's text field and submit
   **When** the revision is sent
   **Then** exactly one LLM call is made to regenerate only the affected ticket(s)
   **And** regenerated cards replace the old ones in the chat flow
   **And** unaffected tickets are not re-generated

3. **Given** I click Accept All
   **When** the action fires
   **Then** all tickets are committed to the project store via direct API calls — zero LLM invocations

## Tasks / Subtasks

- [x] Task 1: Make `TicketCard` fields editable (AC: 1)
  - [x] Update `frontend/components/TicketCard.tsx` to toggle an "edit mode" for title, description, and acceptance criteria.
  - [x] Use `Input` and `Textarea` components for editing fields.
  - [x] clicking "Accept" (or "Save") in edit mode calls the `onAccept` handler with the updated field values.
- [x] Task 2: Extend backend `PATCH` endpoint (AC: 1)
  - [x] Update `TicketStatusUpdate` in `backend/api/routes/projects.py` to optionally include `title`, `description`, and `acceptance_criteria`.
  - [x] Update `update_ticket_status` in `backend/store/project_store.py` (or create a new `update_ticket_fields` method) to apply the provided updates to the ticket in the JSONB array.
- [x] Task 3: Implement Ticket Revision Backend (AC: 2)
  - [x] Add `POST /projects/{project_id}/tickets/{ticket_id}/revise` to `backend/api/routes/projects.py`.
  - [x] Create a LangChain invocation that takes the current tickets, the target `ticket_id`, and the user's `instruction`. The LLM should be instructed to output only the updated JSON for the affected ticket(s).
  - [x] Update the `ticket_history` in the database with the LLM's response.
  - [x] Publish a `tickets_generated` SSE event with the newly updated full ticket list so the frontend refreshes.
- [x] Task 4: Wire Revision Frontend (AC: 2)
  - [x] Update `reviseTicket` in `frontend/lib/api/client.ts` to call the new POST endpoint.
  - [x] Ensure the Submit button next to the revision text area in `TicketCard` calls `onRevise` with the instruction.
- [x] Task 5: Implement Accept All (AC: 3)
  - [x] Update `TicketCardList.tsx` to include an "Accept All" button at the top/bottom of the list.
  - [x] When clicked, iterate through all tickets with status `Pending` and call the `PATCH` endpoint for each (or create a bulk accept endpoint if preferred, though direct API calls in a `Promise.all` loop is acceptable).

## Dev Notes

### Frontend: Inline Editing
- Do not make the user navigate to a separate page.
- When the user clicks an "Edit" icon/button on the card, convert the text displays into `<Input>` (for title) and `<Textarea>` (for description/AC).
- Saving calls the same PATCH endpoint established in Story 4.2, but now passing the modified text fields.

### Backend: PATCH Endpoint Extension
Update the Pydantic model in `backend/api/routes/projects.py`:
```python
class TicketUpdate(BaseModel):
    status: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    acceptance_criteria: Optional[str] = None
```
Ensure the SQL update safely handles optional fields. Use `COALESCE` or dynamically build the jsonb object.

### Backend: Revision Endpoint
The revision endpoint requires **exactly one LLM call**.
Use `TICKET_MODEL` (default: `gemini-2.5-flash`) for this task.
The prompt to the LLM should include:
- The full current ticket list
- The ID of the ticket the user wants to revise
- The user's revision instruction
The LLM should return structured JSON containing **only** the modified tickets (often just the one, but possibly dependents if the change cascades).
Merge these changes into the database and broadcast `tickets_generated` via SSE.

### Architectural Constraints (Non-Negotiable)
- **AD-4:** Edit/Accept actions MUST NOT trigger LLM calls. Only the revision text field action triggers the LLM.
- **AD-9:** New backend route handlers must be `async def`.
- **AD-10:** Frontend communicates with backend exclusively via REST. Do not modify DB directly.
- **FR-8:** Accept All commits tickets with zero LLM invocations.

## Previous Story Intelligence (4.2 Context)
- Story 4.2 created `TicketCard`, `TicketCardList`, and established the `tickets_generated` SSE event pattern.
- The `TicketCard` component already has UI stubs for the Accept button and revision text field. You are making them fully functional.
- The `PATCH` endpoint was initially created for `status` only; you are expanding it.

## Project Context Reference
- **Language Rules:** All LangGraph/LLM calls must be async (`await agent_executor.ainvoke(...)`). Handle Gemini's potential list-of-dicts response format safely.
- **Framework Rules:** Config comes from `os.environ.get(...)` (e.g. `TICKET_MODEL`).
- **Workspace Rules:** `tools/file_ops.py` functions are plain Python.

## References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.3]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md]
- [Source: _bmad-output/project-context.md]
- [Existing: frontend/components/TicketCard.tsx]
- [Existing: frontend/components/TicketCardList.tsx]
- [Existing: backend/api/routes/projects.py]
- [Existing: backend/store/project_store.py]

## Dev Agent Record
### Agent Model Used
Gemini 3.1 Pro
### Debug Log References
None
### Completion Notes List
Ultimate context engine analysis completed - comprehensive developer guide created.
### File List
- `_bmad-output/implementation-artifacts/4-3-inline-ticket-edit-and-accept.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `frontend/components/TicketCard.tsx`
- `frontend/components/TicketCardList.tsx`
- `frontend/lib/api/client.ts`
- `backend/api/routes/projects.py`
- `backend/store/project_store.py`
- `tests/test_ticket_card_view.py`
- `tests/test_inline_ticket_edit.py`

### Change Log
- Implemented inline editing in TicketCard
- Updated acceptTicket in frontend API client to support updates
- Created Accept All logic in TicketCardList
- Modified PATCH endpoint in backend to support field updates
- Implemented ticket revision endpoint using LangChain
- Added unit tests for new store and route methods
