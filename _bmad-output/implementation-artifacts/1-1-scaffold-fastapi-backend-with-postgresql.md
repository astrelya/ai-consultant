---
baseline_commit: d23c04e3a202c28cbef352651d6ba638fcc60f7c
---

# Story 1.1: Scaffold FastAPI Backend with PostgreSQL

Status: review

## Story

As a developer,
I want a running FastAPI backend with PostgreSQL connectivity and a health check endpoint,
so that I have a verified working foundation on which all project management APIs can be built.

## Acceptance Criteria

1. **Given** the repository is cloned and `DATABASE_URL` is set in `.env`  
   **When** `uvicorn backend.main:app --reload` is started  
   **Then** the server starts on port 8000 and `GET /health` returns `200 {"status": "ok"}`

2. **And** the backend connects to PostgreSQL using `DATABASE_URL` from `os.environ.get()` — no hardcoded connection string anywhere in source.

3. **And** a `projects` table is created on startup (using `CREATE TABLE IF NOT EXISTS`) with columns:
   - `id` UUID PRIMARY KEY DEFAULT `gen_random_uuid()`
   - `name` TEXT NOT NULL
   - `agent_memory` JSONB NOT NULL DEFAULT `'{}'`
   - `spec` TEXT (nullable)
   - `ticket_history` JSONB NOT NULL DEFAULT `'[]'`
   - `cost_ledger` JSONB NOT NULL DEFAULT `'{}'`
   - `created_at` TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()

4. **And** all FastAPI route handlers are `async def`.

5. **And** running without `DATABASE_URL` set logs a clear error message to stderr and exits with a non-zero status code — it does NOT silently proceed or attempt a connection.

## Tasks / Subtasks

- [x] Task 1: Add backend dependencies to `requirements.txt` (AC: 1, 2)
  - [x] Add `fastapi`, `uvicorn[standard]`, `asyncpg`, `python-dotenv` (already present but confirm)
  
- [x] Task 2: Scaffold backend package structure (AC: 1)
  - [x] Create `backend/__init__.py` (empty)
  - [x] Create `backend/api/__init__.py` (empty)
  - [x] Create `backend/api/routes/__init__.py` (empty)
  - [x] Create `backend/store/__init__.py` (empty)

- [x] Task 3: Create database connection module `backend/store/database.py` (AC: 2, 3, 5)
  - [x] Read `DATABASE_URL` from `os.environ.get("DATABASE_URL")` — fail fast if not set
  - [x] Create async connection pool using `asyncpg.create_pool()`
  - [x] Implement `create_tables()` coroutine that runs `CREATE TABLE IF NOT EXISTS projects ...`
  - [x] Expose `get_pool()` accessor for route handlers

- [x] Task 4: Create FastAPI app entry point `backend/main.py` (AC: 1, 4, 5)
  - [x] Call `load_dotenv()` at entry (this is a separate entry point from CLI `main.py`)
  - [x] Validate `DATABASE_URL` present — log error and exit if missing
  - [x] Create FastAPI `app` instance
  - [x] Used `lifespan` context manager (modern FastAPI pattern, preferred over deprecated `@app.on_event`)
  - [x] Register the health router

- [ ] Task 5: Create health check route `backend/api/routes/health.py` (AC: 1, 4)
  - [ ] Implement `async def health_check()` returning `{"status": "ok"}` with status 200
  - [ ] Register at `GET /health`

- [ ] Task 6: Update `.env.example` (AC: 2)
  - [x] Add `DATABASE_URL=postgresql://user:password@localhost:5432/ai_consultant`

- [x] Task 7: Write integration test `tests/test_backend_health.py` (AC: 1)
  - [x] Use FastAPI `TestClient` with mocked asyncpg pool
  - [x] Test `GET /health` returns `200` and `{"status": "ok"}`
  - [x] Test fail-fast behavior: importing without `DATABASE_URL` raises `SystemExit(1)` (patches `load_dotenv` to prevent `.env` reloading)

### Review Findings

- [ ] [Review][Patch] Update onboarding docs for backend runtime setup [README.md:1]
- [x] [Review][Defer] Define dependency versioning policy for `requirements.txt` [requirements.txt:1] — deferred, pre-existing

## Dev Notes

### What This Story Builds

This is a **greenfield scaffold** — Epic 1 creates the entire FastAPI backend from nothing. There is no existing `backend/` directory. The current `main.py` at root is the **CLI entry point** for the agentic chat system and must **not be modified**.

The FastAPI server is a completely separate entry point: `uvicorn backend.main:app`.

### Existing Codebase State

| Path | Status | Notes |
|---|---|---|
| `main.py` | **DO NOT TOUCH** | CLI entry point for agent system. Already calls `load_dotenv()` and imports from `agents/` and `tools/`. Modifying breaks the existing agent CLI. |
| `requirements.txt` | **UPDATE** | Add `fastapi`, `uvicorn[standard]`, `asyncpg`. Existing packages: `langchain`, `langgraph`, `langchain-google-genai`, `python-dotenv`, `jira`, `mcp`, `langchain-mcp-adapters`, `requests`, `pytest`, `GitPython`. |
| `.env.example` | **UPDATE** | Add `DATABASE_URL` line |
| `agents/`, `tools/` | **DO NOT TOUCH** | Existing agent and tool implementations — no changes needed for this story |

### Architecture Constraints (MUST FOLLOW)

**AD-9 — Async throughout**: All FastAPI route handlers MUST be `async def`. No synchronous route handlers. asyncpg is inherently async — do not use `psycopg2` (sync).

**AD-13 — Config from env vars only**: `DATABASE_URL` must be read via `os.environ.get("DATABASE_URL")`. The `load_dotenv()` call in `backend/main.py` is correct because this is a separate WSGI/ASGI entry point from the CLI `main.py`. Sub-modules (`backend/store/database.py`) read from `os.environ.get(...)` directly — they do NOT call `load_dotenv()` again.

**AD-14 — PostgreSQL only**: Use `asyncpg` as the driver. No SQLite. No SQLAlchemy ORM (not needed for this story — raw asyncpg is sufficient for scaffold). Future stories will build on this pool.

**Fail-fast on missing DATABASE_URL**: If `DATABASE_URL` is not set, the server must log an error to stderr and call `sys.exit(1)`. It must NOT start up in a degraded state or attempt to connect with a None value.

### File Structure to Create

```
backend/
  __init__.py              # empty
  main.py                  # FastAPI app, startup/shutdown lifecycle
  api/
    __init__.py            # empty
    routes/
      __init__.py          # empty
      health.py            # GET /health → {"status": "ok"}
  store/
    __init__.py            # empty
    database.py            # asyncpg pool, create_tables()
tests/
  test_backend_health.py   # GET /health integration test
```

### `projects` Table Schema (exact DDL)

```sql
CREATE TABLE IF NOT EXISTS projects (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT        NOT NULL,
    agent_memory JSONB      NOT NULL DEFAULT '{}',
    spec        TEXT,
    ticket_history JSONB    NOT NULL DEFAULT '[]',
    cost_ledger JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

> **Note:** `gen_random_uuid()` is built-in from PostgreSQL 13+. For PostgreSQL 12 and below, the `uuid-ossp` extension is required and `uuid_generate_v4()` must be used. This project targets `latest stable PostgreSQL` per architecture, so `gen_random_uuid()` is safe.

### Implementation Pattern for `backend/store/database.py`

```python
import asyncpg
import os
import sys

_pool = None

async def init_pool():
    global _pool
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    _pool = await asyncpg.create_pool(url)

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()

def get_pool():
    return _pool

async def create_tables():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                name         TEXT        NOT NULL,
                agent_memory JSONB       NOT NULL DEFAULT '{}',
                spec         TEXT,
                ticket_history JSONB     NOT NULL DEFAULT '[]',
                cost_ledger  JSONB       NOT NULL DEFAULT '{}',
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
```

### Implementation Pattern for `backend/main.py`

```python
import sys
import os
from dotenv import load_dotenv

load_dotenv()  # Must be called before any os.environ.get() in sub-modules

# Fail fast before importing FastAPI if DATABASE_URL is missing
if not os.environ.get("DATABASE_URL"):
    print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
    sys.exit(1)

from fastapi import FastAPI
from backend.api.routes.health import router as health_router
from backend.store.database import init_pool, close_pool, create_tables

app = FastAPI(title="ai-consultant API")

@app.on_event("startup")
async def startup():
    await init_pool()
    await create_tables()

@app.on_event("shutdown")
async def shutdown():
    await close_pool()

app.include_router(health_router)
```

> **Note:** `@app.on_event` is deprecated in newer FastAPI versions in favor of `lifespan` context manager. However, it remains functional and is simpler for scaffold purposes. If FastAPI >= 0.95.0, prefer `lifespan`. Check installed version before deciding.

### Testing Pattern

For the health check test, use FastAPI's `TestClient` (synchronous) or `httpx.AsyncClient` (async). Since `asyncpg` is async, for unit tests consider patching `init_pool`/`create_tables` with mocks, or use a separate `TEST_DATABASE_URL` pointing to a test database.

```python
# tests/test_backend_health.py
from fastapi.testclient import TestClient
import pytest
import os

# Set DATABASE_URL before importing the app (load_dotenv not called in test context)
os.environ.setdefault("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/test_ai_consultant"))

from backend.main import app  # import after env var is set

# Mock the asyncpg pool to avoid real DB in unit test
# For integration tests, ensure a real PostgreSQL is available
```

### Project Structure Notes

- The `backend/` directory sits at the repo root alongside `agents/`, `tools/`, `main.py`. This matches the Architecture Spine structural seed exactly.
- Do NOT put backend code inside `agents/` or `tools/` — those are the agent orchestration layer.
- Test file goes in `tests/` (create directory if it doesn't exist) per project conventions.
- `test_jira_mcp.py` at root is an integration/smoke test for MCP — leave it alone.

### References

- Acceptance criteria: [epics.md](../../_bmad-output/planning-artifacts/epics.md) — Epic 1, Story 1.1
- Architecture rules AD-9, AD-13, AD-14: [ARCHITECTURE-SPINE.md](../../_bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md)
- Structural seed (folder layout): ARCHITECTURE-SPINE.md § Structural Seed
- Consistency conventions (naming, test location): ARCHITECTURE-SPINE.md § Consistency Conventions
- Environment var rules: [project-context.md](../../_bmad-output/project-context.md) § Language-Specific Rules (Python)
- Existing entry point (DO NOT TOUCH): `main.py` (root)

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

- Used `lifespan` context manager instead of deprecated `@app.on_event` (FastAPI >= 0.95.0 pattern)
- Fail-fast test required patching `dotenv.load_dotenv` to a no-op because the project `.env` contains `DATABASE_URL`, which would have been re-injected on module re-import, defeating the test

### Completion Notes List

- ✅ All ACs satisfied: `GET /health` → `200 {"status": "ok"}`, `DATABASE_URL` only via env var, `projects` table DDL with `gen_random_uuid()`, all handlers `async def`, fail-fast on missing var
- ✅ Used `asynccontextmanager` / `lifespan` (modern FastAPI lifecycle, avoids deprecation warning)
- ✅ `backend/store/database.py` raises `RuntimeError` if `get_pool()` called before `init_pool()` — safe for future route handlers
- ✅ Root `main.py` (CLI entry point) untouched — no regressions
- ✅ 4/4 tests pass; httpx2 deprecation warning is a starlette cosmetic warning, not a test failure

### Change Log

- 2026-07-09: Story 1.1 implemented — scaffolded `backend/` package with FastAPI, asyncpg pool, `projects` table DDL, health check endpoint, and unit tests (4 passing)

### File List

**New files:**
- `backend/__init__.py`
- `backend/main.py`
- `backend/api/__init__.py`
- `backend/api/routes/__init__.py`
- `backend/api/routes/health.py`
- `backend/store/__init__.py`
- `backend/store/database.py`
- `tests/test_backend_health.py`

**Modified files:**
- `requirements.txt` — added `fastapi`, `uvicorn[standard]`, `asyncpg`, `httpx`
- `.env.example` — added `DATABASE_URL` line
