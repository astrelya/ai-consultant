"""
Project store — asyncpg-backed CRUD for the projects table.

Rules (from project-context.md):
- Access get_pool() via the database module object so mocking the definition
  site (backend.store.database.get_pool) works correctly in tests.
- Never call init_pool() here.
- All functions are async def.
- asyncpg.Record is dict-like but not a plain dict — convert with dict(record).
"""
from backend.store import database


async def create_project(name: str) -> dict:
    """Insert a new project record and return its id, name, created_at."""
    pool = database.get_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow(
            "INSERT INTO projects (name) VALUES ($1) RETURNING id, name, created_at",
            name,
        )
    return dict(record)


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

import json

async def save_generated_tickets(project_id: str, tickets: list[dict]) -> list[dict]:
    """Append generated tickets to the project's ticket_history."""
    pool = database.get_pool()
    # Use jsonb_cat or similar, or fetch and update.
    # Since we need to update a JSONB array, let's fetch, append, and update.
    # Actually, Postgres JSONB has `||` operator, but `ticket_history` is a list.
    # Let's fetch the project, append, and save, or do it in SQL:
    # UPDATE projects SET ticket_history = COALESCE(ticket_history, '[]'::jsonb) || $1::jsonb WHERE id = $2 RETURNING ticket_history
    
    async with pool.acquire() as conn:
        record = await conn.fetchrow(
            "UPDATE projects SET ticket_history = COALESCE(ticket_history, '[]'::jsonb) || $1::jsonb "
            "WHERE id = $2 RETURNING ticket_history",
            json.dumps(tickets),
            project_id
        )
    return json.loads(record["ticket_history"]) if record and record["ticket_history"] else []
