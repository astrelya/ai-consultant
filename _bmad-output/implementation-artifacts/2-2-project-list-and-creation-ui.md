---
baseline_commit: d23c04e3a202c28cbef352651d6ba638fcc60f7c
---

# Story 2.2: Project List and Creation UI

## Story Requirements

**User Story:**
As a user,
I want to see all my projects on the home screen and create a new one by entering a name,
So that I can start a new project or return to any existing one without touching a command line.

**Acceptance Criteria:**
- **Given** the frontend is loaded
- **When** the home page renders
- **Then** all existing projects are displayed (fetched from `GET /projects`) showing name and creation date
- **And** an empty state with a "Create your first project" prompt is shown when no projects exist
- **Given** I enter a project name and submit
- **When** the create action fires
- **Then** `POST /projects` is called directly (no LLM call)
- **And** the new project appears in the list immediately
- **And** the app navigates to the Chat View for the new project
- **Given** I click an existing project
- **When** the navigation occurs
- **Then** the app loads the Chat View for that project, fetching its data from `GET /projects/{id}`

## Developer Context & Guardrails

### Technical Requirements
- **Framework:** Next.js 14+ (App Router), React 18+
- **Language:** TypeScript (strict mode enabled)
- **Components:** Server Components vs Client Components. Form submission and interactive lists must be Client Components or use Server Actions. 

### Architecture Compliance
- **LLM-as-last-resort (AD-4):** Project creation must call the REST endpoint directly without invoking the LLM.
- **Project Isolation (AD-5):** Project lists only show project metadata, no cross-project data merged.

### Library & Framework Requirements
- Use standard Next.js routing (`next/navigation` `useRouter`) for navigation to Chat View.
- Use `lib/api/client.ts` to call backend APIs.

### File Structure Requirements
```text
frontend/
  app/
    page.tsx             # Updates to show project list and creation form
    projects/
      [id]/
        page.tsx         # Basic skeleton for Chat View navigation target
```

### Testing Requirements
- Component tests or manual verification that the empty state, populated list, and creation flow work as expected.
- No type errors on compilation.

### Previous Story Intelligence
- Story 2.1 scaffolded Next.js successfully, configured API endpoints, and set up `lib/api/client.ts` with `GET /projects` and `POST /projects`.
- Tailwind was NOT used as requested, use standard CSS or CSS modules for styling.
- `NEXT_PUBLIC_API_URL` is configured for API calls.

### Git Intelligence Summary
Recent commit shows frontend scaffolded in `frontend/`. The structure is standard Next.js App Router.

### Project Context Reference
- See `_bmad-output/project-context.md` for overall guidelines.
- Frontend-backend boundary: REST for mutations and fetching.

## Story Completion Status
- **Status:** review
- **Completion Note:** Story implemented and verified. Project listing and creation flows work correctly. Navigation works. Next.js structure consolidated.

## Tasks/Subtasks
- [x] Create UI for listing projects
- [x] Create UI for "Create new project" form
- [x] Wire up `GET /projects` in home page
- [x] Wire up `POST /projects` on form submit
- [x] Implement navigation to `app/projects/[id]/page.tsx` on success/click
- [x] Create skeleton page for Chat View target

## Dev Notes
- Ensure form submission handles loading and error states gracefully.

## Dev Agent Record
### Debug Log
- Handled Next.js structure consolidation to standard App Router layout in `frontend/app`.
- Fixed `tsconfig.json` path aliasing so `@/lib/...` maps directly to `./lib/...` for the root-level frontend structure.
- Build passing with no type errors.
### Completion Notes
- Implemented the `page.tsx` as a Client Component for direct data fetching.
- CSS Modules used for custom styling as per the requirements.

## Change Log
- Removed `src/app` and moved `layout.tsx` and `globals.css` to `frontend/app/`.
- Replaced `frontend/app/page.tsx` with project list and creation UI.
- Created CSS Module `frontend/app/page.module.css`.
- Added `frontend/app/projects/[id]/page.tsx` skeleton.
- Fixed `frontend/tsconfig.json` mappings.

## File List
- `frontend/app/page.tsx`
- `frontend/app/page.module.css`
- `frontend/app/projects/[id]/page.tsx`
- `frontend/app/layout.tsx` (moved from src)
- `frontend/app/globals.css` (moved from src)
- `frontend/tsconfig.json`
