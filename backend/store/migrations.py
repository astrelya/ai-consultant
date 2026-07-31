import logging

logger = logging.getLogger(__name__)

async def run_migrations(pool) -> None:
    """Run lightweight schema migrations."""
    if hasattr(pool, 'acquire') and callable(getattr(pool, 'acquire')):
        async with pool.acquire() as conn:
            logger.info("Running schema migrations...")
            try:
                await conn.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS repo_path TEXT;")
                await conn.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();")
            except Exception as e:
                logger.error(f"Migration failed: {e}")
                raise
    else:
        logger.warning("Invalid pool provided to run_migrations, skipping.")
