"""
PostgreSQL connection pool management and schema initialization.

Reads DATABASE_URL from os.environ (loaded by backend/main.py via load_dotenv).
Sub-modules must NOT call load_dotenv() again.
"""
import asyncpg
import os
import sys

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    """Initialize the asyncpg connection pool.

    Reads DATABASE_URL from the environment. Exits with status 1 if not set.
    """
    global _pool
    url = os.environ.get("DATABASE_URL")
    if not url:
        print(
            "ERROR: DATABASE_URL environment variable is not set.",
            file=sys.stderr,
        )
        sys.exit(1)
    _pool = await asyncpg.create_pool(url)


async def close_pool() -> None:
    """Close the asyncpg connection pool gracefully."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Return the active connection pool.

    Raises RuntimeError if the pool has not been initialized yet.
    """
    if _pool is None:
        raise RuntimeError("Database pool is not initialized. Call init_pool() first.")
    return _pool


async def create_tables() -> None:
    """Create application tables if they do not already exist.

    Creates the `projects` table required by Epic 1.
    Uses gen_random_uuid() which is built-in from PostgreSQL 13+.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                name           TEXT        NOT NULL,
                agent_memory   JSONB       NOT NULL DEFAULT '{}',
                spec           TEXT,
                ticket_history JSONB       NOT NULL DEFAULT '[]',
                cost_ledger    JSONB       NOT NULL DEFAULT '{}',
                chat_history   JSONB       NOT NULL DEFAULT '[]',
                repo_path      TEXT,
                updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
