---
baseline_commit: d23c04e3a202c28cbef352651d6ba638fcc60f7c
---

# Story 1.3: List and Resume Projects

Status: in-progress

## Story

As a user,
I want to list all my projects and retrieve any one by ID,
so that I can resume work on a previous project without re-configuring or re-explaining context.

## Acceptance Criteria

1. **Given** two or more projects exist in the database
   **When** I send `GET /projects`
   **Then** all projects are returned as a JSON array, each with `id`, `name`, and `created_at`
   **And** no `agent_memory` or `spec` data is included in the list response (list is lightweight)

2. **Given** a project with a known ID exists
   **When** I send `GET /projects/{id}`
   **Then** the full project record is returned including `agent_memory`, `spec`, `ticket_history`, and `cost_ledger`

3. **Given** no project with that ID exists
   **When** I send `GET /projects/{nonexistent-id}`
   **Then** the response is `404 Not Found`

## Tasks / Subtasks

- [x] Task 1: Add `list_projects()` and `get_project()` to `backend/store/project_store.py` (AC: 1, 2, 3)
  - [x] Implement `async def list_projects() -> list[dict]` - SELECT id, name, created_at FROM projects ORDER BY created_at DESC
  - [x] Implement `async def get_project(project_id: str) -> dict | None` - SELECT all columns WHERE id = $1; return None if not found
  - [x] Access pool via `database.get_pool()` (module reference - same pattern as `create_project`, critical for mocking)
  - [x] Convert each asyncpg.Record to dict with `dict(record)` before returning

- [x] Task 2: Add `GET /projects` and `GET /projects/{project_id}` routes to `backend/api/routes/projects.py` (AC: 1, 2, 3)
  - [x] Add `ProjectListItem(BaseModel)` with `id: uuid.UUID`, `name: str`, `created_at: datetime` - lightweight, no heavy fields
  - [x] Add `ProjectDetail(BaseModel)` with `id: uuid.UUID`, `name: str`, `created_at: datetime`, `agent_memory: dict`, `spec: str | None`, `ticket_history: list`, `cost_ledger: dict`
  - [x] Implement `async def list_projects_endpoint() -> list[ProjectListItem]` for `GET /projects`
  - [x] Implement `async def get_project_endpoint(project_id: uuid.UUID) -> ProjectDetail` for `GET /projects/{project_id}`, raises `HTTPException(404)` when not found
  - [x] Import `HTTPException` from `fastapi` for 404 case
  - [x] No LLM calls - direct DB reads only (AD-4)

- [x] Task 3: Write tests `tests/test_projects_list_resume.py` (AC: 1, 2, 3)
  - [x] Mock asyncpg pool at `backend.store.database.get_pool` (definition site - see critical pattern below)
  - [x] Test `GET /projects` returns list with correct shape (id, name, created_at only - no agent_memory/spec)
  - [x] Test `GET /projects` with empty database returns empty array `[]`
  - [x] Test `GET /projects/{id}` with existing project returns full record including agent_memory, spec, ticket_history, cost_ledger
  - [x] Test `GET /projects/{nonexistent-id}` returns 404
  - [x] Test `GET /projects/{invalid-uuid}` returns 422 (FastAPI auto-validates UUID path param)

### Review Findings

#### Epic 1 Review (2026-09-01)

- [x] [Review][Decision] `ProjectDetail` exposes `chat_history: list` and `jira_configured: bool` beyond the Story 1.3 contract — resolved 2026-09-01: spec amended to include both fields in the `ProjectDetail` model as accepted additions from Story 5.4 and Story 4.5.
- [ ] [Review][Patch] `ProjectDetail` will 500 without a JSONB codec — same asyncpg codec finding tracked against Story 1.1; called out here because `GET /projects/{id}` is where Pydantic v2 will actually raise on `agent_memory: dict` / `ticket_history: list` / `cost_ledger: dict`. [backend/api/routes/projects.py:53]
- [x] [Review][Defer] `list_projects_endpoint` returns the entire table with no pagination — fine for now, add `limit`/`offset` when project count grows. [backend/api/routes/projects.py:64]

## Dev Notes

### What Stories 1.1 and 1.2 Already Built (DO NOT RECREATE)

| File | What exists | How Story 1.3 uses it |
|---|---|---|
| `backend/main.py` | FastAPI `app` with `lifespan`, health + projects router registered | **DO NOT TOUCH** |
| `backend/store/database.py` | `get_pool()`, `init_pool()`, `close_pool()`, `create_tables()` | Import via module object: `from backend.store import database; database.get_pool()` |
| `backend/api/routes/projects.py` | `POST /projects` route, `ProjectCreate`, `ProjectResponse` models, `router = APIRouter()` | **EXTEND** - add new routes and models, do NOT rewrite existing content |
| `backend/store/project_store.py` | `create_project(name)` function | **EXTEND** - add `list_projects()` and `get_project()` below existing function |
| All `__init__.py` files | Empty package markers | Already exist |
| `tests/test_backend_health.py` | 4 passing tests | **DO NOT TOUCH** - regression guard |
| `tests/test_projects_create.py` | 5 passing tests for `POST /projects` | **DO NOT TOUCH** - regression guard |

### New Files to Create

```
tests/
  test_projects_list_resume.py   # Tests for GET /projects and GET /projects/{id}
```

### Files to EXTEND (not recreate)

```
backend/
  store/
    project_store.py             # ADD list_projects() and get_project() below existing create_project()
  api/
    routes/
      projects.py                # ADD ProjectListItem, ProjectDetail models + 2 new route handlers
                                 # KEEP existing ProjectCreate, ProjectResponse, POST /projects unchanged
```

### Architecture Constraints (MUST FOLLOW)

**AD-4 - LLM-as-last-resort**: Both endpoints are direct DB reads. Zero LLM calls in this story.

**AD-5 - Project isolation**: `GET /projects` must NEVER expose one project's `agent_memory` in the list response. The list endpoint returns `id`, `name`, `created_at` ONLY.

**AD-9 - Async throughout**: All route handlers and store functions must be `async def`. Use `await` for all asyncpg calls.

**AD-14 - PostgreSQL only**: asyncpg is the only driver. No SQLite fallback.

### Critical Implementation Pattern: Pool Access for Mocking

`project_store.py` already uses `database.get_pool()` via module reference. All new store functions MUST follow this exact pattern:

```python
from backend.store import database


async def list_projects() -> list[dict]:
    """Return all projects as lightweight records (id, name, created_at)."""
    pool = database.get_pool()
    async with pool.acquire() as conn:
        records = await conn.fetch(
            "SELECT id, name, created_at FROM projects ORDER BY created_at DESC"
        )
    return [dict(r) for r in records]


async def get_project(project_id: str) -> dict | None:
    """Return full project record by UUID string, or None if not found."""
    pool = database.get_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow(
            "SELECT id, name, agent_memory, spec, ticket_history, cost_ledger, created_at "
            "FROM projects WHERE id = $1",
            project_id,
        )
    return dict(record) if record else None
```

> asyncpg note: `conn.fetch()` returns list of asyncpg.Record; `conn.fetchrow()` returns single Record or None. Both are dict-like but must be converted with dict(r).

### Route Implementation Pattern

```python
# Add to backend/api/routes/projects.py - BELOW existing code

from typing import Optional
from fastapi import HTTPException


class ProjectListItem(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime.datetime


class ProjectDetail(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime.datetime
    agent_memory: dict
    spec: Optional[str]
    ticket_history: list
    cost_ledger: dict
    # Schema amendment (2026-09-01, Epic 1 review D2):
    # chat_history added by Story 5.4 (persistent chat); jira_configured added
    # by Story 4.5 (Jira approval gate). Both are part of the ProjectDetail
    # contract from Epic 1 onwards.
    chat_history: list = []
    jira_configured: bool = False


@router.get("/projects", response_model=list[ProjectListItem])
async def list_projects_endpoint() -> list[ProjectListItem]:
    results = await project_store.list_projects()
    return [ProjectListItem(**r) for r in results]


@router.get("/projects/{project_id}", response_model=ProjectDetail)
async def get_project_endpoint(project_id: uuid.UUID) -> ProjectDetail:
    result = await project_store.get_project(str(project_id))
    if result is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectDetail(**result)
```

> UUID path param: Declare `project_id: uuid.UUID` - FastAPI auto-validates and returns 422 for malformed UUIDs. Pass as `str(project_id)` to asyncpg.
> JSONB fields: asyncpg returns `agent_memory`, `ticket_history`, `cost_ledger` as Python dict/list directly - no json.loads() needed.
> spec is TEXT nullable: asyncpg returns None for NULL. `Optional[str]` handles this correctly.

### Testing Pattern for `tests/test_projects_list_resume.py`

```python
import os
import uuid
import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_ai_consultant")
import backend.store.database  # noqa: E402


def make_list_record(project_id=None, name="test-project"):
    return {
        "id": project_id or uuid.uuid4(),
        "name": name,
        "created_at": datetime.datetime.now(tz=datetime.timezone.utc),
    }


def make_detail_record(project_id=None, name="test-project"):
    return {
        "id": project_id or uuid.uuid4(),
        "name": name,
        "created_at": datetime.datetime.now(tz=datetime.timezone.utc),
        "agent_memory": {},
        "spec": None,
        "ticket_history": [],
        "cost_ledger": {},
    }


def make_mock_pool_fetch(records: list) -> MagicMock:
    """Pool mock for conn.fetch() - returns a list of records."""
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=records)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool


def make_mock_pool_fetchrow(record) -> MagicMock:
    """Pool mock for conn.fetchrow() - returns single record or None."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=record)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool


@pytest.fixture(scope="module")
def client():
    with (
        patch("backend.store.database.init_pool", new_callable=AsyncMock),
        patch("backend.store.database.close_pool", new_callable=AsyncMock),
        patch("backend.store.database.create_tables", new_callable=AsyncMock),
    ):
        from backend.main import app
        with TestClient(app) as test_client:
            yield test_client
```

> CRITICAL: Do NOT import `from backend.main import app` before the patches are active. The scope="module" fixture ensures app is imported once inside the patch context. This is the same lesson from Story 1.2.

### Previous Story Learnings Applied

| Learning from Story 1.2 | Applied in Story 1.3 |
|---|---|
| Patch `backend.store.database.get_pool` (definition site) | Same pattern - patch the module's `get_pool`, not the imported name in `project_store` |
| `project_store.py` uses `database.get_pool()` via module reference | New functions must follow this exact pattern |
| asyncpg `.Record` must be converted with `dict(record)` | `list_projects()` uses `[dict(r) for r in records]`; `get_project()` uses `dict(record) if record else None` |
| `TestClient` + `scope="module"` fixture with patches active during app import | Reuse same fixture approach in new test file |
| `Optional[str]` for nullable fields in Pydantic models | `spec: Optional[str]` in `ProjectDetail` |

### Database Schema Reference

```sql
-- Already created by create_tables() in backend/store/database.py - NO CHANGES NEEDED
CREATE TABLE IF NOT EXISTS projects (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name           TEXT        NOT NULL,
    agent_memory   JSONB       NOT NULL DEFAULT '{}',
    spec           TEXT,                          -- nullable
    ticket_history JSONB       NOT NULL DEFAULT '[]',
    cost_ledger    JSONB       NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

GET /projects selects: `id, name, created_at` ONLY
GET /projects/{id} selects: all columns
No schema changes, no migrations, no new tables.

### References

- Acceptance criteria: [epics.md](../../_bmad-output/planning-artifacts/epics.md) - Epic 1, Story 1.3
- Architecture AD-4, AD-5, AD-9, AD-14: [ARCHITECTURE-SPINE.md](../../_bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md)
- asyncpg fetch/fetchrow API: https://magicstack.github.io/asyncpg/current/api/index.html#asyncpg.Connection.fetch
- FastAPI path params + UUID: https://fastapi.tiangolo.com/tutorial/path-params/#path-parameters-with-types
- Pydantic Optional fields (v2): https://docs.pydantic.dev/latest/concepts/types/#optional-fields
- Story 1.1 (scaffold/DB): [1-1-scaffold-fastapi-backend-with-postgresql.md](./1-1-scaffold-fastapi-backend-with-postgresql.md)
- Story 1.2 (POST /projects): [1-2-create-a-new-project.md](./1-2-create-a-new-project.md)
- Project context rules: [project-context.md](../../_bmad-output/project-context.md)

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (Thinking)

### Debug Log References

No issues encountered. All patterns followed from Stories 1.1 and 1.2 exactly.

### Completion Notes List

- Extended `backend/store/project_store.py` with `list_projects()` and `get_project()` using the established `database.get_pool()` module-reference pattern (critical for test mocking).
- Extended `backend/api/routes/projects.py` with `ProjectListItem`, `ProjectDetail` Pydantic models and two new GET route handlers. `GET /projects` exposes only `id`, `name`, `created_at` (AD-5 compliance). `GET /projects/{project_id}` exposes all columns; 404 on missing record; 422 on invalid UUID (FastAPI auto-validation).
- Created `tests/test_projects_list_resume.py` with 7 tests covering: correct shape (no heavy fields in list), empty DB, full record retrieval, NULL spec handling, 404 not-found, 422 invalid-UUID.
- All 16 tests pass (9 pre-existing + 7 new). Zero regressions.

### File List

- `backend/store/project_store.py` (modified)
- `backend/api/routes/projects.py` (modified)
- `tests/test_projects_list_resume.py` (created)

## Change Log

- 2026-07-09: Implemented Story 1.3 — added `list_projects()` and `get_project()` to project store; added `GET /projects` and `GET /projects/{project_id}` routes; created 7 tests; all 16 tests pass.
