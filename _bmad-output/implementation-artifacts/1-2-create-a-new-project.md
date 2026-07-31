---
baseline_commit: d23c04e3a202c28cbef352651d6ba638fcc60f7c
---

# Story 1.2: Create a New Project

Status: review

## Story

As a user,
I want to create a new project by providing a name,
so that I have a persistent, isolated workspace with its own memory, spec slot, and ticket history.

## Acceptance Criteria

1. **Given** the backend is running and connected to PostgreSQL  
   **When** I send `POST /projects` with body `{"name": "my-project"}`  
   **Then** a new project record is inserted with a unique UUID, empty `agent_memory` (`{}`), null `spec`, empty `ticket_history` (`[]`), and zeroed `cost_ledger` (`{}`)  
   **And** the response is `201` with `{"id": "<uuid>", "name": "my-project", "created_at": "<timestamp>"}`

2. **And** sending a second `POST /projects` with the same name creates a separate distinct project — names are **not** unique keys; both records coexist with different UUIDs.

3. **And** sending `POST /projects` with a **missing** `name` field returns `422 Unprocessable Entity`.

4. **And** sending `POST /projects` with a **blank** `name` (empty string or whitespace-only) returns `422 Unprocessable Entity`.

## Tasks / Subtasks

- [x] Task 1: Create project store module `backend/store/project_store.py` (AC: 1, 2)
  - [x] Implement `async def create_project(name: str) -> dict` that inserts a row and returns the new record as a dict with `id`, `name`, `created_at`
  - [x] Use `get_pool()` from `backend.store.database` — never call `init_pool()` directly in store modules
  - [x] Use `INSERT INTO projects (name) VALUES ($1) RETURNING id, name, created_at`

- [x] Task 2: Create `POST /projects` route in `backend/api/routes/projects.py` (AC: 1, 2, 3, 4)
  - [x] Define `ProjectCreate(BaseModel)` with `name: str` — add `@field_validator` (Pydantic v2) or `@validator` (Pydantic v1) to reject blank/whitespace-only strings, raising `ValueError`
  - [x] Define `ProjectResponse(BaseModel)` with `id: uuid.UUID`, `name: str`, `created_at: datetime`
  - [x] Implement `async def create_project_endpoint(body: ProjectCreate) -> ProjectResponse` with `status_code=201`
  - [x] Call `project_store.create_project(body.name)` and return the result as `ProjectResponse`

- [x] Task 3: Register projects router in `backend/main.py` (AC: 1)
  - [x] Import `projects_router` from `backend.api.routes.projects`
  - [x] Add `app.include_router(projects_router)` alongside health router

- [x] Task 4: Write tests `tests/test_projects_create.py` (AC: 1, 2, 3, 4)
  - [x] Mock asyncpg pool so tests run without a real PostgreSQL connection
  - [x] Test `POST /projects` with valid name → 201 + correct JSON shape
  - [x] Test `POST /projects` with same name twice → both succeed with different UUIDs
  - [x] Test `POST /projects` with missing `name` field → 422
  - [x] Test `POST /projects` with blank/whitespace-only name → 422

## Dev Notes

### What Story 1.1 Already Built (DO NOT RECREATE)

Story 1.1 is in `review` status. The following are already implemented and **must be reused**:

| File | What exists | How Story 1.2 uses it |
|---|---|---|
| `backend/main.py` | FastAPI `app` with `lifespan`, health router registered | **ADD** projects router — do not rewrite existing content |
| `backend/store/database.py` | `get_pool()`, `init_pool()`, `close_pool()`, `create_tables()` | Import `get_pool()` in `project_store.py` |
| `backend/api/routes/health.py` | `GET /health` | **DO NOT TOUCH** |
| `backend/__init__.py`, all `__init__.py` | Empty package markers | Already exist — do not recreate |
| `tests/test_backend_health.py` | 4 passing tests | **DO NOT TOUCH** — regression guard |

### New Files to Create

```
backend/
  api/
    routes/
      projects.py          # POST /projects route + Pydantic models
  store/
    project_store.py       # async DB access — create_project()
tests/
  test_projects_create.py  # 5 tests for create project endpoint
```

### Architecture Constraints (MUST FOLLOW)

**AD-4 — LLM-as-last-resort**: `POST /projects` is a direct DB write. Zero LLM calls anywhere in this story. No agent invocation for project creation.

**AD-5 — Project isolation**: Each created project receives its own UUID primary key. Default values (`{}`, `[]`) are set at the database level via column defaults — not injected by application code.

**AD-9 — Async throughout**: Route handler and store function must both be `async def`. Use `await` for all asyncpg calls.

**Pydantic version**: FastAPI on Python 3.14 ships with **Pydantic v2**. Use `@field_validator` (not deprecated `@validator`). Check with `import pydantic; print(pydantic.VERSION)` if unsure.

**asyncpg returns `asyncpg.Record`** for `fetchrow()` — it is dict-like but not a plain `dict`. Convert to dict via `dict(record)` before returning from `create_project()`. The `id` column is a `uuid.UUID` object; `created_at` is a `datetime.datetime` with timezone. Pydantic serializes both correctly when declared as `uuid.UUID` and `datetime` in `ProjectResponse`.

**Blank name validation**: Pydantic v2 `str` type does NOT automatically reject `""` or `"   "`. Implement a `@field_validator('name', mode='before')` that calls `.strip()` and raises `ValueError('name must not be blank')` if result is empty. This triggers FastAPI's 422 response.

### Implementation Pattern for `backend/store/project_store.py`

```python
import uuid
import datetime
from backend.store.database import get_pool


async def create_project(name: str) -> dict:
    """Insert a new project record and return its id, name, created_at."""
    pool = get_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow(
            "INSERT INTO projects (name) VALUES ($1) RETURNING id, name, created_at",
            name,
        )
    return dict(record)
```

> Column defaults (`agent_memory`, `spec`, `ticket_history`, `cost_ledger`) are set in the DDL (`DEFAULT '{}' / NULL / DEFAULT '[]'`) — the INSERT omits them intentionally. The SELECT `RETURNING` clause only returns the fields needed for the `201` response.

### Implementation Pattern for `backend/api/routes/projects.py`

```python
import uuid
import datetime
from fastapi import APIRouter
from pydantic import BaseModel, field_validator
from backend.store import project_store

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str

    @field_validator("name", mode="before")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not str(v).strip():
            raise ValueError("name must not be blank")
        return v


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime.datetime


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project_endpoint(body: ProjectCreate) -> ProjectResponse:
    result = await project_store.create_project(body.name)
    return ProjectResponse(**result)
```

### Registering the Router in `backend/main.py`

Add ONE import and ONE `include_router` call — nothing else changes in `backend/main.py`:

```python
from backend.api.routes.projects import router as projects_router
# ... existing code ...
app.include_router(projects_router)
```

### Testing Pattern for `tests/test_projects_create.py`

The key challenge: mocking `get_pool()` so the route handler's call to `pool.acquire()` returns a mock connection with a usable `fetchrow`.

```python
import uuid
import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

# asyncpg.Record mock — dict-like
def make_mock_record(project_id, name):
    return {
        "id": project_id,
        "name": name,
        "created_at": datetime.datetime.now(tz=datetime.timezone.utc),
    }

def make_mock_pool(record):
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=record)
    # pool.acquire() must work as async context manager
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool
```

> **Important**: Patch `backend.store.database.get_pool` (where it is defined), not `backend.store.project_store.get_pool` (where it is imported). Python mock resolution requires patching the definition site.

### Previous Story Learnings Applied

| Learning from Story 1.1 | Applied in Story 1.2 |
|---|---|
| Use `lifespan` not `@app.on_event` | Already done in `backend/main.py` — do not change |
| Patch `dotenv.load_dotenv` for fail-fast tests | Not needed for this story (fail-fast is in `backend/main.py`, unchanged) |
| `get_pool()` raises `RuntimeError` if called before `init_pool()` | Mock `get_pool` at the definition site in tests |
| asyncpg `pool.acquire()` is an async context manager | Mock both `__aenter__` and `__aexit__` on the return value |
| `TestClient` module caching: patch before importing `app` | Use `scope="module"` fixture with patches active during `TestClient` init |

### References

- Acceptance criteria: [epics.md](../../_bmad-output/planning-artifacts/epics.md) — Epic 1, Story 1.2
- Architecture AD-4, AD-5, AD-9: [ARCHITECTURE-SPINE.md](../../_bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md)
- Pydantic v2 validators: https://docs.pydantic.dev/latest/concepts/validators/
- asyncpg `fetchrow`: https://magicstack.github.io/asyncpg/current/api/index.html#asyncpg.Connection.fetchrow
- Story 1.1 (previous story / foundation): [1-1-scaffold-fastapi-backend-with-postgresql.md](./1-1-scaffold-fastapi-backend-with-postgresql.md)
- Project context rules: [project-context.md](../../_bmad-output/project-context.md)

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

- Patching `backend.store.database.get_pool` works only when `project_store.py` accesses `get_pool` via the module object (`database.get_pool()`). Using `from ... import get_pool` binds a local reference that is NOT affected by the patch. Changed `project_store.py` to `from backend.store import database` and call `database.get_pool()` so the definition-site patch takes effect.

### Completion Notes List

- Task 1 ✅: `backend/store/project_store.py` created. `create_project()` issues `INSERT ... RETURNING id, name, created_at` and converts the asyncpg Record to dict. Accesses pool via `database.get_pool()` (module reference) so tests can mock at definition site.
- Task 2 ✅: `backend/api/routes/projects.py` created. `ProjectCreate` uses Pydantic v2 `@field_validator(mode='before')` to reject blank/whitespace names with 422. `ProjectResponse` typed with `uuid.UUID` and `datetime`. Route returns 201.
- Task 3 ✅: `backend/main.py` updated — `projects_router` imported and registered via `app.include_router(projects_router)`.
- Task 4 ✅: `tests/test_projects_create.py` created with 5 tests. All pass. Existing 4 health tests still pass (9/9 total).

### File List

- backend/store/project_store.py (created)
- backend/api/routes/projects.py (created)
- backend/main.py (modified)
- tests/test_projects_create.py (created)

## Change Log

- Implemented POST /projects endpoint: project_store, route, router registration, 5 tests (Date: 2026-07-09)
