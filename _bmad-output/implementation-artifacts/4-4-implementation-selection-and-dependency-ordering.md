---
baseline_commit: 0ce5653ee60582c85b363902903e510f65023a8d
---

# Story 4.4: Implementation Selection and Dependency Ordering

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want to select which tickets to include in the current execution run using checkboxes, with the system automatically ordering them to respect blocking relationships,
So that I control scope while the system guarantees a safe execution sequence.

## Acceptance Criteria

1. **Given** all tickets have been accepted
   **When** the selection view renders
   **Then** each ticket is shown as a card with a checkbox, defaulting to checked
   **And** I can uncheck any ticket to exclude it from the current run

2. **Given** I confirm my selection
   **When** the Execution Queue is built
   **Then** the queue is ordered by topological sort of the blocking/blocked-by graph — computed without any LLM call
   **And** a ticket marked as `blocked_by` another is never placed before its blocker in the queue
   **And** a deselected ticket's dependents are also flagged with a warning (their blocker will not run)
   **And** `POST /projects/{id}/execute` is called with the ordered ticket ID list to begin execution

## Tasks / Subtasks

- [x] Task 1: Add checkbox selection to Ticket Cards (AC: 1)
  - [x] Update `frontend/components/TicketCard.tsx` (or `TicketCardList.tsx`) to render a checkbox next to each ticket card.
  - [x] Default all accepted tickets to checked state.
  - [x] Add state management for selected ticket IDs in the frontend.
- [x] Task 2: Implement Dependency Warning Logic (AC: 2)
  - [x] When a ticket is unchecked, recursively check for its dependents (tickets that list it in `blocked_by`).
  - [x] Show a warning indicator on those dependent tickets to indicate their blocker will not run.
- [x] Task 3: Implement Topological Sort (AC: 2)
  - [x] Add a utility function on the frontend to perform topological sorting of tickets based on their `blocked_by` and `blocking` relationships.
  - [x] The algorithm must ensure that a blocking ticket is ordered *before* its dependents in the resulting queue.
- [x] Task 4: Execute with Ordered List (AC: 2)
  - [x] Create a "Confirm Selection" (or "Execute") button.
  - [x] When confirmed, filter the full list to only the checked tickets, apply the topological sort, and extract the ordered list of ticket IDs.
  - [x] Call the backend `POST /projects/{id}/execute` endpoint with this ordered ID list.

## Dev Notes

### Frontend: Checkbox & Warnings
- Keep the state in `TicketCardList` or the parent `ChatView` so that selection spans across the list.
- For dependent warnings, you can visually alter the card (e.g., a yellow banner or an alert icon) if a ticket in its `blocked_by` list is currently unchecked.

### Frontend: Topological Sorting
- Implement a graph traversal (like Kahn's algorithm or DFS) to sort the tickets.
- It must be deterministic and guarantee that if Ticket A blocks Ticket B, A appears before B.
- Ensure cycles (if accidentally present, though LLM ticket generation shouldn't produce them) do not cause an infinite loop (e.g. throw an error or drop the cycle).

### Architectural Constraints (Non-Negotiable)
- **AD-4 (LLM-as-last-resort):** The topological sort and dependency ordering MUST be computed entirely with traditional code (e.g., TS graph algorithms). Do NOT use an LLM for sorting.
- **AD-10 (Frontend-backend boundary):** The action simply posts the correctly ordered IDs to the execution REST endpoint.

## Previous Story Intelligence (4.3 Context)
- Story 4.3 completed the inline edit and Accept mechanisms. This story builds upon the state where tickets are "Accepted" by allowing the user to select the subset for the execution run.
- Checkboxes should only be active/meaningful once the ticket generation and acceptance loop is finalized.

## Project Context Reference
- **Language Rules:** All LangGraph/LLM calls must be async. (Not strictly applicable here as this is primarily frontend/REST logic, but good to remember).
- **Framework Rules:** Next.js 14+ for the frontend React components.

## References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.4]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md]
- [Source: _bmad-output/project-context.md]
- [Existing: frontend/components/TicketCard.tsx]
- [Existing: frontend/components/TicketCardList.tsx]

## Dev Agent Record
### Agent Model Used
Gemini 3.1 Pro
### Debug Log References
None
### Completion Notes List
Ultimate context engine analysis completed - comprehensive developer guide created.
✅ Implemented checkbox selection for ticket cards to toggle execution inclusion.
✅ Handled dependency warning logic: if a blocked ticket is selected but its blocker is not (or has a warning itself), it is visually flagged.
✅ Implemented `handleExecute` using existing topological sort to send an ordered list to `POST /projects/{id}/execute`.
✅ Zero LLM calls in UI logic as per AD-4.
### File List
- _bmad-output/implementation-artifacts/4-4-implementation-selection-and-dependency-ordering.md
- frontend/components/TicketCard.tsx
- frontend/components/TicketCardList.tsx
- frontend/lib/api/client.ts
