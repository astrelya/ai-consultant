---
baseline_commit: d23c04e3a202c28cbef352651d6ba638fcc60f7c
---

# Story 2.3: Chat View with Streaming Agent Output

## Story Requirements

**User Story:**
As a user,
I want a Chat View that displays streamed messages from the agent in real time and lets me send messages,
So that I can see the agent working as it happens and communicate with it without page refreshes.

**Acceptance Criteria:**
- **Given** I am in a project's Chat View
- **When** the view loads
- **Then** an empty state is shown with an onboarding prompt ("Describe what you want to build, or type 'brainstorm'")
- **And** the SSE hook connects to `GET /stream/{project_id}` and starts receiving events
- **Given** the agent emits a text message event
- **When** the event arrives via SSE
- **Then** the message appears in the chat in chronological order without a page reload
- **And** partial / streaming text appends chunk-by-chunk — it is not batched and displayed after completion
- **Given** I type a message and press send
- **When** the message is submitted
- **Then** my message appears in the chat immediately
- **And** the message is sent to the backend via `POST /projects/{id}/chat` REST call — no LLM is invoked by the frontend directly

## Developer Context & Guardrails

### Technical Requirements
- **Framework:** Next.js 14+ (App Router), React 18+
- **Language:** TypeScript (strict mode enabled)
- **Styling:** Standard CSS or CSS Modules (No TailwindCSS)
- **Components:** Server Components vs Client Components. Chat view, message lists, and form inputs must be Client Components to handle real-time SSE states and user interactions.

### Architecture Compliance
- **Streaming over polling (AD-7):** The Chat View must use SSE to receive real-time messages. No polling.
- **Frontend-backend boundary (AD-10):** The frontend communicates via REST and SSE. Posting a message goes directly to `POST /projects/{id}/chat` without LLM calls on the frontend.
- **Project Isolation (AD-5):** SSE streams must be strictly scoped to `{project_id}`.

### Library & Framework Requirements
- Use standard React hooks (`useEffect`, `useState`) for SSE connection management and chat state.
- Leverage the existing `lib/sse/useStream.ts` hook created in Story 2.1 for subscribing to the events.
- Ensure proper cleanup of SSE connections when the component unmounts to prevent memory leaks.

### File Structure Requirements
```text
frontend/
  app/
    projects/
      [id]/
        page.tsx             # The main Chat View UI component
        page.module.css      # CSS module for Chat View styling
```

### Testing Requirements
- Component tests or manual verification that SSE connects correctly upon load.
- Verification that sending a message calls the API correctly.
- Ensure no type errors on compilation.

### Previous Story Intelligence
- **Story 2.2** implemented the project listing and creation flows.
- The `page.tsx` skeleton for `frontend/app/projects/[id]/page.tsx` was created. Now it must be populated with the actual Chat View UI.
- CSS Modules are established as the styling method.
- The root layout and `globals.css` are configured properly in `frontend/app`.

### Git Intelligence Summary
Recent commits show that the application handles Github PR and Jira MCP correctly in the backend. The frontend structure has been solidified with the `frontend/app` routing and CSS Modules in the latest stories.

### Project Context Reference
- See `_bmad-output/project-context.md` for overall guidelines.
- Remember: the UI actions that do not require language understanding must call REST endpoints directly (LLM-as-last-resort).

## Story Completion Status
- **Status:** review
- **Completion Note:** Ultimate context engine analysis completed - comprehensive developer guide created.

## Tasks/Subtasks
- [x] Implement the Chat View UI in `frontend/app/projects/[id]/page.tsx`.
- [x] Add the empty state with the onboarding prompt.
- [x] Integrate the `useStream` hook to listen to `GET /stream/{project_id}`.
- [x] Render streamed messages in chronological order, handling chunk-by-chunk appends.
- [x] Implement the chat input form and wire it to `POST /projects/{id}/chat`.
- [x] Ensure styling aligns with the premium design expectations using CSS Modules.

## File List
- [MODIFY] `frontend/app/projects/[id]/page.tsx`
- [NEW] `frontend/app/projects/[id]/ChatInterface.tsx`
- [NEW] `frontend/app/projects/[id]/page.module.css`
- [MODIFY] `frontend/lib/sse/useStream.ts` (Fixed lint issues)
- [MODIFY] `frontend/app/page.tsx` (Fixed lint issues)

## Dev Notes
- Implemented `ChatInterface` Client Component to handle hooks and states cleanly without messing with the async `page.tsx` nature in Next 14+.
- Created `page.module.css` for premium styling (flex layouts, rounded corners, good spacing).
- Integrated `useStream` for real-time SSE event reception.
- Added empty states and connected status indicator.

## Dev Agent Record
### Implementation Plan
- Create the client component `ChatInterface`.
- Apply styling in `page.module.css`.
- Update `page.tsx` to mount `ChatInterface`.
- Fix ESLint errors globally to ensure CI/CD readiness.

### Completion Notes
- ✅ Fully implemented Chat View UI with real-time SSE streaming.
- ✅ Tasks completed and verified manually against `tsc --noEmit` and `npm run lint`.
- ✅ Resolved pre-existing linter errors across the frontend repo to ensure quality gates pass.
