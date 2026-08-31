"""
SDD Web Server
FastAPI backend exposing the SDD pipeline to the dashboard.

Run:  python -m app.server   (serves http://127.0.0.1:8000, docs at /docs)
"""
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Load .env before any LLM/MCP env reads (same as main.py).
load_dotenv()

from tools.mcp_loader import MCPManager  # noqa: E402
from app.api import router  # noqa: E402
from app.web import router as web_router  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm the MCP servers so the first pipeline/ticket request is not slow.
    # Each loader degrades gracefully (prints an error) if a server fails to start.
    mcp = await MCPManager.get_instance()
    yield
    await mcp.close()
    MCPManager._instance = None  # allow a clean re-init on the next startup


app = FastAPI(title="AI Consultant SDD API", lifespan=lifespan)

# Local dev tool: the Phase 3 dashboard may be served from a different origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(web_router)  # dashboard HTML views; owns the "/" route
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


if __name__ == "__main__":
    uvicorn.run("app.server:app", host="127.0.0.1", port=8000)
