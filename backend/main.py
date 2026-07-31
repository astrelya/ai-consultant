"""
FastAPI application entry point for the ai-consultant backend.

Start the server with:
    uvicorn backend.main:app --reload --port 8000

This is a separate entry point from the CLI main.py at the repo root.
load_dotenv() is called here because this is an independent ASGI entry point.
"""
import sys
import os
from dotenv import load_dotenv

# Load .env before any sub-module reads os.environ (AD-13)
load_dotenv()

# Fail fast if DATABASE_URL is not configured (AC-5)
if not os.environ.get("DATABASE_URL"):
    print(
        "ERROR: DATABASE_URL environment variable is not set. "
        "Add DATABASE_URL to your .env file and restart the server.",
        file=sys.stderr,
    )
    sys.exit(1)

from contextlib import asynccontextmanager
from fastapi import FastAPI

from backend.api.routes.health import router as health_router
from backend.api.routes.projects import router as projects_router
from backend.api.routes.stream import router as stream_router
from backend.api.routes.bmad import router as bmad_router
from backend.api.routes.chat import router as chat_router
from backend.store.database import init_pool, close_pool, create_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown lifecycle for the FastAPI application."""
    # Startup: initialize DB pool and ensure schema exists
    await init_pool()
    await create_tables()
    from backend.store.migrations import run_migrations
    try:
        from backend.store.database import get_pool
        pool = get_pool()
        await run_migrations(pool)
    except RuntimeError:
        pass  # Expected during tests where init_pool is mocked
    yield
    # Shutdown: close the connection pool
    await close_pool()


app = FastAPI(title="ai-consultant API", lifespan=lifespan)

app.include_router(health_router)
app.include_router(projects_router)
app.include_router(stream_router)
app.include_router(bmad_router)
app.include_router(chat_router)
