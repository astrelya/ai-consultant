"""
Project store — asyncpg-backed CRUD for the projects table.

Rules (from project-context.md):
- Access get_pool() via the database module object so mocking the definition
  site (backend.store.database.get_pool) works correctly in tests.
- Never call init_pool() here.
- All functions are async def.
- asyncpg.Record is dict-like but not a plain dict — convert with dict(record).
"""
import datetime
import json
import logging
import uuid

from backend.store import database
from backend.store.errors import TestArtifactMissingError

logger = logging.getLogger(__name__)


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
            "SELECT id, name, agent_memory, spec, ticket_history, cost_ledger, "
            "COALESCE(chat_history, '[]'::jsonb) AS chat_history, created_at "
            "FROM projects WHERE id = $1",
            project_id,
        )
    if not record:
        return None
    row = dict(record)
    # asyncpg returns JSONB as text; decode into Python objects for Pydantic.
    for field, default in (
        ("agent_memory", {}),
        ("ticket_history", []),
        ("cost_ledger", {}),
        ("chat_history", []),
    ):
        value = row.get(field)
        if isinstance(value, str):
            try:
                row[field] = json.loads(value)
            except (TypeError, ValueError):
                row[field] = default
        elif value is None:
            row[field] = default
    return row


async def append_chat_message(
    project_id: str,
    role: str,
    content: str,
    metadata: dict | None = None,
) -> None:
    """Append a single chat message to the project's chat_history JSONB array.

    Story 5.4 — persists conversation across sessions.
    """
    if role not in {"user", "agent", "system"}:
        raise ValueError(f"invalid role: {role!r}")
    entry = {
        "id": str(uuid.uuid4()),
        "role": role,
        "content": content,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "metadata": metadata or {},
    }
    pool = database.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE projects "
            "SET chat_history = COALESCE(chat_history, '[]'::jsonb) || $1::jsonb "
            "WHERE id = $2",
            json.dumps([entry]),
            project_id,
        )

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


async def update_agent_memory(project_id: str, patch: dict) -> None:
    """Merge ``patch`` into the project's ``agent_memory`` JSONB column.

    Story 6.3 (AC-6) — used to persist ``workspace_path`` after successful
    environment prep. Merge semantics (JSONB ``||``): top-level keys from
    ``patch`` overwrite existing keys; other keys are preserved.
    """
    if not patch:
        return
    pool = database.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE projects "
            "SET agent_memory = COALESCE(agent_memory, '{}'::jsonb) || $1::jsonb "
            "WHERE id = $2",
            json.dumps(patch),
            project_id,
        )


async def update_ticket_status(project_id: str, ticket_id: str, status: str) -> None:
    """Update the status field of a specific ticket in ticket_history JSONB array."""
    pool = database.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE projects
            SET ticket_history = (
                SELECT jsonb_agg(
                    CASE WHEN t->>'id' = $2
                    THEN t || jsonb_build_object('status', $3::text)
                    ELSE t
                    END
                )
                FROM jsonb_array_elements(ticket_history) AS t
            )
            WHERE id = $1
            """,
            project_id, ticket_id, status,
        )

async def update_ticket_fields(project_id: str, ticket_id: str, fields: dict) -> None:
    """Update multiple fields of a specific ticket in ticket_history JSONB array."""
    pool = database.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE projects
            SET ticket_history = (
                SELECT jsonb_agg(
                    CASE WHEN t->>'id' = $2
                    THEN t || $3::jsonb
                    ELSE t
                    END
                )
                FROM jsonb_array_elements(ticket_history) AS t
            )
            WHERE id = $1
            """,
            project_id, ticket_id, json.dumps(fields),
        )

async def overwrite_ticket_history(project_id: str, tickets: list[dict]) -> None:
    """Overwrite the entire ticket_history array with the provided tickets."""
    pool = database.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE projects
            SET ticket_history = $2::jsonb
            WHERE id = $1
            """,
            project_id, json.dumps(tickets),
        )


async def add_cost_ledger_entry(
    project_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
) -> dict:
    """FR-25 / Story 6.1: atomically accumulate token usage on the cost_ledger JSONB column.

    Uses a single UPDATE with ``jsonb_build_object`` + ``COALESCE`` so concurrent
    read-only endpoints (e.g. GET /projects/{id}) never observe a torn write.

    Returns the NEW ledger dict; returns ``{}`` and logs a warning when the
    project id is unknown (never raises — SSE / LLM paths must not crash on
    missing project rows).
    """
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    total_tokens = prompt_tokens + completion_tokens
    pool = database.get_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow(
            """
            UPDATE projects
            SET cost_ledger = jsonb_build_object(
                'total_prompt_tokens',     COALESCE((cost_ledger->>'total_prompt_tokens')::int, 0)     + $2,
                'total_completion_tokens', COALESCE((cost_ledger->>'total_completion_tokens')::int, 0) + $3,
                'total_tokens',            COALESCE((cost_ledger->>'total_tokens')::int, 0)            + $4,
                'total_cost_usd',          COALESCE((cost_ledger->>'total_cost_usd')::float, 0.0)      + $5,
                'last_updated',            $6::text
            )
            WHERE id = $1
            RETURNING cost_ledger
            """,
            project_id, prompt_tokens, completion_tokens, total_tokens, cost_usd, now_iso,
        )
    if not record or record["cost_ledger"] is None:
        logger.warning("add_cost_ledger_entry: project %s not found", project_id)
        return {}
    raw = record["cost_ledger"]
    return json.loads(raw) if isinstance(raw, str) else dict(raw)


async def write_test_artifact(
    project_id: str, ticket_id: str, artifact_ref: str
) -> None:
    """AD-6 / FR-17: persist a non-empty test artifact reference on a ticket.

    Must be called by TesterAgent before ``mark_ticket_done`` can succeed.
    """
    if not isinstance(artifact_ref, str) or not artifact_ref.strip():
        raise ValueError("artifact_ref must be a non-empty string")
    pool = database.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE projects
            SET ticket_history = (
                SELECT jsonb_agg(
                    CASE WHEN t->>'id' = $2
                    THEN t || $3::jsonb
                    ELSE t
                    END
                )
                FROM jsonb_array_elements(ticket_history) AS t
            )
            WHERE id = $1
            """,
            project_id,
            ticket_id,
            json.dumps({"test_artifact_ref": artifact_ref}),
        )


async def write_error_report(
    project_id: str, ticket_id: str, error_report: dict
) -> None:
    """FR-20: persist a structured error report on a ticket.

    Called by SupervisorAgent when a ticket transitions to Error after
    exhausting autonomous remediation. Overwrites any prior report on
    the same ticket — the latest attempt is authoritative.
    """
    if not isinstance(error_report, dict):
        raise ValueError("error_report must be a dict")
    required_keys = {
        "ticket_id", "failure_kind", "description",
        "initial_failures", "attempted_fixes",
        "log_references", "branch",
    }
    missing = required_keys - error_report.keys()
    if missing:
        raise ValueError(f"error_report missing keys: {sorted(missing)}")
    pool = database.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE projects
            SET ticket_history = (
                SELECT jsonb_agg(
                    CASE WHEN t->>'id' = $2
                    THEN t || $3::jsonb
                    ELSE t
                    END
                )
                FROM jsonb_array_elements(ticket_history) AS t
            )
            WHERE id = $1
            """,
            project_id,
            ticket_id,
            json.dumps({"error_report": error_report}),
        )


async def mark_ticket_done(project_id: str, ticket_id: str) -> None:
    """AD-6 / FR-17 gate: only transition ticket to Done when a test artifact exists.

    Raises ``TestArtifactMissingError`` (a hard system error) if the ticket's
    ``test_artifact_ref`` field is missing, empty, or whitespace-only. The gate
    lives at the persistence boundary so every code path — supervisor, review
    workflow, CLI, or ad-hoc REPL — hits the same guardrail.
    """
    pool = database.get_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow(
            "SELECT ticket_history FROM projects WHERE id = $1",
            project_id,
        )
    if not record:
        raise ValueError(f"Project {project_id} not found")
    history = record["ticket_history"]
    if isinstance(history, str):
        try:
            history = json.loads(history)
        except (TypeError, ValueError):
            history = []
    ticket = next(
        (
            t
            for t in (history or [])
            if isinstance(t, dict) and t.get("id") == ticket_id
        ),
        None,
    )
    if ticket is None:
        raise ValueError(
            f"Ticket {ticket_id} not found in project {project_id}"
        )
    ref = ticket.get("test_artifact_ref")
    if not isinstance(ref, str) or not ref.strip():
        raise TestArtifactMissingError(project_id, ticket_id)

    pool = database.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE projects
            SET ticket_history = (
                SELECT jsonb_agg(
                    CASE WHEN t->>'id' = $2
                    THEN t || jsonb_build_object('status', 'Done')
                    ELSE t
                    END
                )
                FROM jsonb_array_elements(ticket_history) AS t
            )
            WHERE id = $1
            """,
            project_id,
            ticket_id,
        )
