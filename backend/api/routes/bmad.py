"""
POST /projects/{project_id}/bmad/run — launch a BMad pipeline as an async subprocess.

Rules:
- Route handler is async def (AD-9).
- Validates project_id exists; returns 404 if not found.
- Fire-and-forget: returns 202 Accepted immediately, subprocess runs in background.
- No synchronous subprocess calls — SubprocessRunner uses asyncio.create_subprocess_exec().

─────────────────────────────────────────────────────────────────────────────
Manual Smoke Test (AC: 5)
─────────────────────────────────────────────────────────────────────────────
Prerequisites:
  1. Backend running:  uvicorn backend.main:app --reload --port 8000
  2. A valid project_id — create one first:
       curl -s -X POST http://localhost:8000/projects \\
         -H "Content-Type: application/json" \\
         -d '{"name": "smoke-test-project"}'
     Note the "id" field in the response.

Step 1 — Subscribe to the SSE stream in a terminal:
    curl -N http://localhost:8000/stream/{project_id}

Step 2 — In a second terminal, trigger the subprocess:
    curl -s -X POST http://localhost:8000/projects/{project_id}/bmad/run \\
      -H "Content-Type: application/json" \\
      -d '{"cmd": "echo test output"}'

Expected result in the SSE terminal:
    event: bmad_output
    data: {"line": "test output"}

    event: bmad_complete
    data: {"exit_code": 0}

Windows note: wrap cmd in cmd /c, e.g. {"cmd": "cmd /c echo test output"}
─────────────────────────────────────────────────────────────────────────────
"""
import asyncio
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.store import project_store
from tools.subprocess_runner import SubprocessRunner

router = APIRouter()


class BmadRunRequest(BaseModel):
    """Request body for launching a BMad pipeline command."""

    cmd: str


class BmadRunResponse(BaseModel):
    """Immediate acknowledgement that the subprocess was accepted."""

    status: str
    project_id: str
    message: str


@router.post(
    "/projects/{project_id}/bmad/run",
    response_model=BmadRunResponse,
    status_code=202,
)
async def run_bmad_endpoint(
    project_id: uuid.UUID,
    body: BmadRunRequest,
) -> BmadRunResponse:
    """Launch a BMad pipeline command for the given project.

    The subprocess runs asynchronously (fire-and-forget). Progress is delivered
    via the SSE stream at GET /stream/{project_id}.

    Returns 202 Accepted immediately; use the SSE stream to observe output.
    Returns 404 if the project does not exist.
    """
    project_id_str = str(project_id)

    # Validate that the project exists (return 404 if not).
    project = await project_store.get_project(project_id_str)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Fire-and-forget: launch subprocess without awaiting completion.
    asyncio.create_task(SubprocessRunner.run(body.cmd, project_id_str))

    return BmadRunResponse(
        status="accepted",
        project_id=project_id_str,
        message="BMad subprocess started",
    )
