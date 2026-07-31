---
baseline_commit: d23c04e3a202c28cbef352651d6ba638fcc60f7c
---

# Story 2.1: Scaffold Next.js Frontend with API & SSE Clients

## Story Requirements

**User Story:**
As a developer,
I want a running Next.js 14+ frontend with a typed REST client and SSE subscription hook wired to the backend,
So that all subsequent frontend features have a consistent, tested foundation.

**Acceptance Criteria:**
- **Given** the backend is running and the frontend is started with `npm run dev`
- **When** the app loads in a browser
- **Then** it renders without errors and displays a placeholder home page
- **And** a `lib/api/client.ts` module exists with typed wrappers for `GET /projects`, `POST /projects`, and `GET /projects/{id}`
- **And** a `lib/sse/useStream.ts` React hook exists that subscribes to `GET /stream/{project_id}` and exposes an array of received events
- **And** `NEXT_PUBLIC_API_URL` env var controls the backend base URL — no hardcoded localhost in source
- **And** TypeScript strict mode is enabled with zero type errors

## Developer Context & Guardrails

### Technical Requirements
- **Framework:** Next.js 14+ (App Router), React 18+
- **Language:** TypeScript (strict mode enabled)
- **API Client:** Use standard `fetch` for REST wrappers in `lib/api/client.ts`.
- **SSE Client:** Standard browser `EventSource` in `lib/sse/useStream.ts`.

### Architecture Compliance
- **Frontend-backend boundary (AD-10):** REST for actions, SSE for streaming. No direct DB access.
- **Config (AD-13):** `NEXT_PUBLIC_API_URL` environment variable is required. No hardcoded localhost in source.
- **Project Isolation (AD-5):** All API and SSE requests must be appropriately scoped to the project (e.g. `GET /projects/{id}`).

### Library & Framework Requirements
- **Next.js 14+:** Use the App Router (`app/` directory).
- **TypeScript:** Strict mode must be enabled (`"strict": true` in `tsconfig.json`).

### File Structure Requirements
```text
frontend/
  app/
    page.tsx             # Placeholder home page
  lib/
    api/
      client.ts          # Typed REST wrappers
    sse/
      useStream.ts       # React hook for SSE
```

### Testing Requirements
- Ensure standard Next.js typescript compilation passes with zero errors.

### Git Intelligence Summary
Recent commits show backend setup and MCP tools. This is the first frontend story for this project.

### Latest Tech Information
- Next.js 14 App Router uses React Server Components by default. The `useStream.ts` hook uses React hooks (`useState`, `useEffect`), so it must have the `"use client"` directive at the top. Components using this hook must also be client components.
- Ensure proper `EventSource` cleanup in the `useEffect` return function in `useStream.ts` to prevent connection leaks on unmount.

### Project Context Reference
- See `_bmad-output/project-context.md` for overall guidelines.
- Remember: `NEXT_PUBLIC_API_URL` is required for frontend-backend communication.

## Story Completion Status
- **Status:** review
- **Completion Note:** Ultimate context engine analysis completed - comprehensive developer guide created

## Tasks/Subtasks
- [x] Initialize Next.js project with App Router and TypeScript
- [x] Configure `NEXT_PUBLIC_API_URL` environment variable
- [x] Implement typed REST client in `lib/api/client.ts`
- [x] Implement SSE hook in `lib/sse/useStream.ts`
- [x] Create placeholder home page

## Dev Notes
- Architecture pattern: REST for mutations, SSE for streams.

## Dev Agent Record
### Implementation Plan
- Scaffolding Next.js frontend with App Router using `create-next-app`
- Created API REST client for `/projects` using standard fetch wrapper
- Created custom React hook `useStream` to connect via `EventSource` to the streaming backend endpoint.

### Completion Notes
- Scaffolded Next.js successfully, without Tailwind as requested.
- `useStream.ts` connects automatically using the given ID.
- Tested compilation (`npm run build`), all tasks passed type checking.

## File List
- `frontend/*` (Next.js initialization)
- `frontend/.env.local`
- `frontend/lib/api/client.ts`
- `frontend/lib/sse/useStream.ts`
- `frontend/app/page.tsx`

## Change Log
- Initial frontend scaffolding and API/SSE client implementation (Date: 2026-07-09)
