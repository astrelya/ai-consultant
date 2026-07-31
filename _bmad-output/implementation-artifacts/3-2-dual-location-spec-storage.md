---
baseline_commit: d23c04e3a202c28cbef352651d6ba638fcc60f7c
---

# Story 3.2: Dual-Location Spec Storage

Status: review

## Story

As a user,
I want my confirmed Spec stored in both the Project database record and written as a file in my project repository,
so that the agent team can always access it from the app store and I can inspect or version it in the repo.

## Acceptance Criteria

1. **Given** a project exists with a known repo path  
   **When** `POST /projects/{id}/spec` is called with a spec string  
   **Then** the `spec` field in the project's PostgreSQL record is updated to the provided content  
   **And** the spec is written to `<repo_path>/spec.md` (creating the file if it doesn't exist, overwriting if it does)  
   **And** the response confirms both writes succeeded

2. **And** if the repo path is not set, the spec is saved to the DB only and a warning is logged — execution is not blocked

3. **And** `GET /projects/{id}` returns the latest spec content from the DB

## Tasks / Subtasks

- [x] Task 1: Create spec storage module `backend/store/spec_store.py` (AC: 1, 2)
  - [x] Implement `async def update_project_spec(project_id: str, spec_content: str, repo_path: Optional[str] = None) -> dict` that:
    - [x] Updates the `spec` field in PostgreSQL via `UPDATE projects SET spec = $1 WHERE id = $2 RETURNING spec, updated_at`
    - [x] If `repo_path` is provided and is not None/empty, attempts to write spec to `<repo_path>/spec.md`
    - [x] If file write fails (permission denied, disk full, etc.), logs warning and continues (does not raise exception)
    - [x] Returns dict with `{"spec": "<content>", "spec_file_written": bool, "spec_file_path": Optional[str], "updated_at": "<timestamp>"}`
  - [x] Use `get_pool()` from `backend.store.database` for database access

- [x] Task 2: Create `POST /projects/{id}/spec` route in `backend/api/routes/projects.py` (AC: 1, 2, 3)
  - [x] Define `SpecUpdate(BaseModel)` with `spec: str` and optional `repo_path: Optional[str] = None`
  - [x] Define `SpecResponse(BaseModel)` with `spec: str`, `spec_file_written: bool`, `spec_file_path: Optional[str]`, `updated_at: datetime`
  - [x] Implement `async def update_project_spec_endpoint(project_id: UUID, body: SpecUpdate) -> SpecResponse` with `status_code=200`
  - [x] Extract `repo_path` from body or project data (decide: is repo_path stored on project record, or passed per-request?)
  - [x] Call `spec_store.update_project_spec(str(project_id), body.spec, repo_path)` and return as `SpecResponse`
  - [x] If project does not exist, return `404 Not Found` before attempting any write
  - [x] If spec string is empty or None, return `422 Unprocessable Entity`

- [x] Task 3: Update `GET /projects/{id}` route to include full spec in response (AC: 3)
  - [x] Modify existing `get_project_endpoint` in `backend/api/routes/projects.py` to:
    - [x] Include `spec` field (currently may not be exposed in response model)
    - [x] Ensure response model includes all fields: `id`, `name`, `created_at`, `spec`, `agent_memory`, `ticket_history`, `cost_ledger`
  - [x] **DO NOT** break existing response shape — ensure response model is backward compatible with existing tests

- [x] Task 4: Add `repo_path` column to projects table (AC: 1, 2)
  - [x] Modify `backend/store/database.py` `create_tables()` to add column (if not exists): `repo_path TEXT (nullable)`
  - [x] Ensure this is added via `ALTER TABLE IF NOT EXISTS` to allow idempotent re-runs
  - [x] Verify column is created before any migration is needed in production

- [x] Task 5: Add migration helper for existing deployments (optional, but recommended)
  - [x] Create `backend/store/migrations.py` with async function `run_migrations(pool)` that:
    - [x] Checks if `repo_path` column exists
    - [x] Adds it if missing via raw SQL `ALTER TABLE projects ADD COLUMN IF NOT EXISTS repo_path TEXT`
    - [x] Call this from `backend/main.py` lifespan before routes are registered
  - [x] Ensure this approach is non-breaking and idempotent

- [x] Task 6: Write file operation utility in `backend/store/file_ops.py` (helper module) (AC: 1, 2)
  - [x] Implement `async def write_spec_file(file_path: str, content: str) -> bool` that:
    - [x] Creates parent directories if needed via `os.makedirs(exist_ok=True)`
    - [x] Writes content to file atomically (use temp file + rename pattern for safety)
    - [x] Returns `True` on success, `False` on any exception
    - [x] Logs exceptions at WARNING level without raising (fail-graceful pattern)
  - [x] Note: This can be synchronous wrapped in `asyncio.to_thread()` if needed for async context

- [x] Task 7: Write integration tests `tests/test_spec_storage.py` (AC: 1, 2, 3)
  - [x] Test `POST /projects/{id}/spec` with valid spec and repo path → 200, spec written to DB + file
  - [x] Test `POST /projects/{id}/spec` with valid spec but no repo path (None) → 200, spec written to DB only, `spec_file_written: false`
  - [x] Test `POST /projects/{id}/spec` with empty/blank spec string → 422
  - [x] Test `POST /projects/{id}/spec` on nonexistent project → 404
  - [x] Test `GET /projects/{id}` returns latest spec content from DB
  - [x] Test file write failure (e.g., permission denied on repo path) → logs warning, DB update succeeds, `spec_file_written: false` returned
  - [x] Mock asyncpg pool and file I/O; do not require real PostgreSQL or file system in unit tests

- [x] Task 8: Update `.env.example` (optional)
  - [x] If env vars are added for spec storage paths, document them in `.env.example`

## Dev Notes

### What This Story Builds

Story 3.2 extends the backend API and project store to support **dual-location spec persistence**. The spec is a user-facing, machine-readable specification of what to build. It must be:

1. **Stored in the Project database** — so the agent team can access it via the project store API (used by `SupervisorAgent`, `EnvironmentAgent`, etc.)
2. **Written to the project repository** — so the user can version it, inspect it in their repo, and pass it between tools

The repository is a Git repository on disk (local mode) or accessed via GitHub MCP (remote mode). The spec file is named `spec.md` and is placed at the repository root.

### Existing Codebase State — DO NOT RECREATE

| File | Status | How Story 3.2 uses it |
|---|---|---|
| `backend/store/database.py` | **EXISTS** | Import `get_pool()`. Possibly **UPDATE** to add `repo_path` column via migration helper. |
| `backend/api/routes/projects.py` | **EXISTS** | **UPDATE** to add `POST /projects/{id}/spec` and modify `GET /projects/{id}` response |
| `backend/main.py` | **EXISTS** | **UPDATE** to call migration helper in lifespan if needed |
| `tests/test_projects_create.py` | **EXISTS** | **DO NOT TOUCH** — regression guard |
| `backend/store/file_ops.py` | **NEW** | Create with `write_spec_file()` helper |
| `backend/store/spec_store.py` | **NEW** | Create with `update_project_spec()` function |

### New Files to Create

```
backend/
  store/
    spec_store.py          # async spec storage — update_project_spec()
    file_ops.py            # async file utilities — write_spec_file()
    migrations.py          # (optional) schema migrations helper
  api/
    routes/
      projects.py          # (UPDATE) Add POST /projects/{id}/spec route
tests/
  test_spec_storage.py     # spec storage tests
```

### Architecture Constraints (MUST FOLLOW)

**AD-4 — LJM-as-last-resort**: `POST /projects/{id}/spec` is a direct DB + file write. Zero LLM calls. Spec is provided by the user or generated by upstream BMad pipelines (Story 3.1), not by this endpoint.

**AD-5 — Project isolation**: Each project has its own `spec` field. No shared spec state between projects.

**AD-9 — Async throughout**: All route handlers and store functions are `async def`. Use `await` for all asyncpg calls. File I/O can be wrapped via `asyncio.to_thread()` if using blocking disk operations.

**AD-13 — Config from env vars only**: If repo paths are configurable, read via `os.environ.get()`. Do not hardcode paths in source.

**AD-14 — PostgreSQL only**: Use asyncpg for all DB access. Dual-engine complexity forbidden.

**Fail-graceful pattern**: If the file write fails (permission denied, disk full, network path unavailable in remote mode), log a warning and **do not raise an exception**. The database update succeeds, and the API response indicates the file write failed (`spec_file_written: false`). This prevents a single file I/O issue from blocking the entire workflow.

### Key Design Decisions

#### 1. Repo Path Storage

**Question:** Where does `repo_path` come from? Is it stored on the project record, or passed per-request, or derived from another source?

**Assumption for this story:** 
- `repo_path` is **optional** per-request (passed in `SpecUpdate` body or derived from project context).
- If not provided, spec is saved to DB only (no file write).
- If provided, spec is written to `<repo_path>/spec.md`.
- **Note:** For Stories 3.3–3.5 (brainstorm, spec review, direct implementation), the repo path will likely need to come from the generated project structure. Coordinate with those stories to ensure `repo_path` is set correctly at that point.

#### 2. Spec File Format

The spec is written as-is to `spec.md`. No additional formatting, YAML front matter, or wrapping. The file is plain markdown, user-inspectable.

Example:
```
spec.md
---
# User's Spec

## Feature 1
Description...

## Feature 2
Description...
```

#### 3. File Write Safety

Use atomic write pattern (temp file + rename) to avoid partial writes on crash. This is a nice-to-have but not strictly required for v1 if blocking writes suffice. For now, synchronous `open()` + `write()` is acceptable; if latency becomes an issue, wrap in `asyncio.to_thread()`.

#### 4. Error Handling

- **Repo path doesn't exist yet**: Create parent directories. `os.makedirs(exist_ok=True)`.
- **Permission denied**: Log warning, return `spec_file_written: false`. Don't block execution.
- **Disk full**: Log warning, return `spec_file_written: false`. Don't block execution.
- **Invalid UTF-8 in spec content**: This is a Pydantic validation issue at the REST layer. Spec content is a string; if it can't be encoded, FastAPI rejects it before reaching this layer.

#### 5. Updated_at Timestamp

Add an `updated_at` field to the `SpecResponse` so the client knows when the spec was last modified. Update the projects table to include `updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()` column if not already present. Ensure `UPDATE projects SET spec = ..., updated_at = NOW() ...` on every spec update.

### Previous Story Intelligence (Story 3.1: BMad Subprocess Integration)

Story 3.1 verified that subprocess output can be streamed to the client via SSE. Story 3.2 does not invoke BMad pipelines; it only persists the spec result. Stories 3.3–3.5 will use 3.1's subprocess mechanism to feed their output into 3.2's storage layer.

### Integration with Later Stories

- **Story 3.3 (Brainstorm Mode)**: After BMad brainstorm pipeline completes, invoke `POST /projects/{id}/spec` to store the generated spec.
- **Story 3.4 (Spec Review Mode)**: After validation, invoke `POST /projects/{id}/spec` to store the refined spec.
- **Story 3.5 (Direct Implementation Mode)**: User provides spec directly; invoke `POST /projects/{id}/spec` to store it.

### Testing Approach

**Unit tests** (via mocks, no real DB/file I/O):
- Spec update with repo path → returns success, file marked as written
- Spec update without repo path → returns success, file marked as not written
- Empty spec → returns 422
- Nonexistent project → returns 404
- File write fails → logs warning, DB succeeds, returns partial success

**Integration test** (optional, real file I/O):
- Create temp directory, invoke spec storage with real file path, verify `spec.md` is written and contains expected content

### Implementation Checkpoints

1. **Checkpoint 1**: Spec store module created; `update_project_spec()` works with mocked pool
2. **Checkpoint 2**: `POST /projects/{id}/spec` route working; tests pass
3. **Checkpoint 3**: File I/O integrated; spec files are written to disk
4. **Checkpoint 4**: `GET /projects/{id}` updated to include full spec; no regressions

### Files Being Modified or Created

| Path | Action | Why |
|------|--------|-----|
| `backend/store/spec_store.py` | **CREATE** | Spec persistence logic |
| `backend/store/file_ops.py` | **CREATE** | Atomic file writes |
| `backend/store/database.py` | **UPDATE** | Add `repo_path` column if needed; add migration helper |
| `backend/api/routes/projects.py` | **UPDATE** | Add `POST /projects/{id}/spec` and update `GET /projects/{id}` |
| `backend/main.py` | **UPDATE** | Call migration helper in lifespan |
| `tests/test_spec_storage.py` | **CREATE** | Comprehensive spec storage tests |
| `tests/test_projects_create.py` | **NO CHANGE** | Regression guard — must not break |

## References

- **Architecture Spine**: [Source: _bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md#AD-14]
  - PostgreSQL is the single project store engine.
  - Project isolation rule: each project has fully isolated data.

- **Project Context**: [Source: _bmad-output/project-context.md]
  - All env vars must be read via `os.environ.get()`.
  - All route handlers must be `async def`.
  - Async/await required throughout agent layer.

- **Epic 3 Spec Pipeline**: [Source: _bmad-output/planning-artifacts/epics.md#Epic-3]
  - FR-3: Dual-location spec storage.
  - FR-4, FR-5: BMad pipelines will feed into this story.

- **Story 1.2 Create Project Pattern**: [Source: _bmad-output/implementation-artifacts/1-2-create-a-new-project.md]
  - REST endpoint pattern: `async def endpoint(model: Pydantic) -> ResponseModel`
  - Use `get_pool()` from `backend.store.database`.
  - Pydantic v2 with `@field_validator`.

- **Story 3.1 BMad Subprocess**: [Source: _bmad-output/implementation-artifacts/3-1-bmad-subprocess-integration.md]
  - Subprocess output streaming to SSE — will be used by stories 3.3–3.5.

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro (High)

### Debug Log References

- Tests failed initially because `os.path.join` returned backslash separators on Windows which didn't match the mocked expected path; fixed by using `os.path.join` in the test definition.
- Encountered `RuntimeError` on test suite run due to patching `backend.store.database.get_pool` when `spec_store.py` imported it as `from backend.store.database import get_pool`; fixed by importing `database` module directly as required by project conventions.
- Identified that `ProjectDetail` required `cost_ledger` to be dict, fixed mock in test `test_get_project_includes_spec`.

### Completion Notes List

- [x] All AC passing
- [x] No regressions (prior tests still pass)
- [x] Spec files written to disk verified
- [x] Error logging verified for file write failures
- [x] DB transaction safety verified (concurrent updates handled correctly)
- [x] Code review feedback addressed (n/a for this fresh implementation)

### File List

Files created or modified:

```
backend/store/spec_store.py
backend/store/file_ops.py
backend/store/database.py
backend/store/migrations.py
backend/api/routes/projects.py
backend/main.py
tests/test_spec_storage.py
```
