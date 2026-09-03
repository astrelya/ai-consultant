## Deferred from: code review of 1-1-scaffold-fastapi-backend-with-postgresql (2026-07-09)

- Define dependency versioning policy for requirements.txt (pinning or bounded ranges) to improve reproducibility. Observed in requirements.txt additions; deferred as a repository-wide pre-existing policy decision.

## Deferred from: code review of epic-1 (2026-09-01)

- **Story 1.1** — `sys.exit(1)` inside `async init_pool()` duplicates the fail-fast check in `backend/main.py` and hard-kills the process mid-lifespan. Refactor to `raise RuntimeError` and let uvicorn own exit. [backend/store/database.py:26]
- **Story 1.1** — `gen_random_uuid()` assumes PostgreSQL ≥ 13; add explicit `CREATE EXTENSION IF NOT EXISTS pgcrypto` guard when broadening supported versions. [backend/store/database.py:59]
- **Story 1.1** — Task 5 (`health.py`) and Task 6 header remain unchecked despite implementation present (also tracked by retro action epic-1-A2). [1-1-scaffold-fastapi-backend-with-postgresql.md:65]
- **Story 1.1** — Diff-scoping process gap: Epic 1 review diff omitted `backend/api/routes/stream.py`; matches retro action epic-1-A6 (require Review Findings section per story).
- **Story 1.2** — `name_not_blank` validates on `str(v).strip()` but returns `v` unstripped; leading/trailing whitespace stored verbatim. Not required by AC-4. [backend/api/routes/projects.py:31]
- **Story 1.2** — `create_project_endpoint` has no exception handler around DB writes; raw asyncpg errors surface to the client as 500 with traceback. [backend/api/routes/projects.py:45]
- **Story 1.3** — `list_projects_endpoint` returns all rows unpaginated; add `limit`/`offset` when project count grows. [backend/api/routes/projects.py:64]
- **Story 1.4** — SSE `register`/`unregister` and event queues have no `maxsize`; slow clients or runaway publishers can grow queues without bound. Add a bound + drop-with-log. [backend/api/sse.py:20, 36]
- **Story 1.4** — `publish_event` silently swallows `asyncio.QueueFull` with no log — hard to diagnose stalled UIs. [backend/api/sse.py:38]
- **Story 1.4** — `SSEManager.get_instance` singleton is not lock-guarded; safe under a single event loop but fragile under multi-loop tests. [backend/api/sse.py:13]

### Epic 4/5 issues discovered while auditing `backend/api/routes/projects.py` (out of Epic 1 scope, tracked for the owning epics)

- **Story 4.5** — `update_ticket_endpoint` passes the internal ticket UUID to `tm.transition_ticket(ticket_id, body.status)`, but Jira transitions require the Jira key returned from `create_jira_ticket`. Returned `jira_key` is currently discarded (`# Could save the Jira key back to DB here if needed`). Every transition after Accepted will hit the wrong issue or fail. [backend/api/routes/projects.py:140]
- **Story 4.x** — `generate_tickets_endpoint` builds `structured_llm = llm.with_structured_output(GeneratedTicket, ...)` and immediately reassigns it to `TicketGenerationResult`; the first call is dead code. [backend/api/routes/projects.py:171-176]
- **Story 4.x** — `overwrite_ticket_history` is last-write-wins; two concurrent revisions on the same project silently drop one revision's changes (no optimistic locking / `updated_at` CAS). [backend/store/project_store.py:overwrite_ticket_history]
- **Story 4.x** — LLM calls in ticket routes have no timeout, retry, auth check, or error boundary; missing `GOOGLE_API_KEY` raises deep in langchain and surfaces as 500 with traceback. [backend/api/routes/projects.py:161, 236]
- **Story 4.x** — `TicketManager()` is instantiated per PATCH request; hoist to a lifespan-scoped singleton if the constructor opens sockets/loads credentials. [backend/api/routes/projects.py:130]
- **Story 5.x** — `update_ticket_status` / `update_ticket_fields` use `jsonb_agg(CASE ...)` over `jsonb_array_elements(ticket_history)` — when `ticket_history` is empty, `jsonb_agg` returns NULL and violates the `NOT NULL` constraint. Wrap with `COALESCE(jsonb_agg(...), '[]'::jsonb)`. [backend/store/project_store.py:update_ticket_status, update_ticket_fields]
- **Cross-cutting** — No CORS middleware on the FastAPI app; frontend cannot cross-origin call the backend without an ad-hoc proxy. Owning epic TBD (Epic 2 frontend integration is the natural home). [backend/main.py]
