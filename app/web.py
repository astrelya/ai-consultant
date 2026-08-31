"""
SDD Dashboard (Phase 3)
Server-rendered HTML views (Jinja2) + vanilla JS frontend, served by the same
FastAPI app as the JSON API. Live progress comes from the SSE endpoint;
markdown artifacts are rendered client-side with marked.js.
"""
import json
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.runner import runner
from core.artifacts import read_artifact

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

STATUS_LABELS = {
    "spec_drafting": ("Spécification en cours", "working"),
    "pending_spec_approval": ("En attente — validation de la spec", "gate"),
    "planning": ("Planification en cours", "working"),
    "pending_plan_approval": ("En attente — validation du plan / tâches", "gate"),
    "implementing": ("Implémentation en cours", "working"),
    "verifying": ("Vérification en cours", "working"),
    "completed": ("Terminé", "done"),
    "failed": ("Échec", "error"),
}


def _status_info(status: str) -> tuple[str, str]:
    return STATUS_LABELS.get(status, (status or "inconnu", "working"))


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    pipelines = await runner.list_pipelines()
    rows = []
    for p in pipelines:
        state = p["state"]
        status = state.get("status", "")
        label, css = _status_info(status)
        tasks = state.get("tasks", [])
        rows.append({
            "thread_id": p["thread_id"],
            "ticket_id": state.get("ticket_id", "?"),
            "mode": state.get("mode", "?"),
            "status_label": label,
            "status_css": css,
            "task_progress": f"{state.get('current_task_index', 0)}/{len(tasks)}" if tasks else "—",
            "pending_gate": bool(p["pending_gate"]),
            "running": p["running"],
        })
    return templates.TemplateResponse(request, "index.html", {"pipelines": rows})


@router.post("/pipelines")
async def start_pipeline_web(ticket_id: str = Form(...), mode: str = Form(None)):
    thread_id = await runner.start_pipeline(ticket_id.strip(), mode)
    return RedirectResponse(url=f"/pipelines/{thread_id}", status_code=303)


@router.get("/pipelines/{thread_id}", response_class=HTMLResponse)
async def pipeline_page(request: Request, thread_id: str):
    info = await runner.get_state(thread_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Pipeline {thread_id} not found")

    state = info["state"]
    status = state.get("status", "")
    label, css = _status_info(status)

    repo_name = (state.get("repo_full_name") or "").split("/")[-1]
    ticket_id = state.get("ticket_id", "")
    artifacts = {}
    if repo_name and ticket_id:
        for name in ("spec.md", "plan.md", "tasks.md"):
            content = read_artifact(repo_name, ticket_id, name)
            if content is not None:
                artifacts[name] = content

    tasks = state.get("tasks", [])
    task_rows = []
    for i, t in enumerate(tasks):
        done = i < state.get("current_task_index", 0)
        current = i == state.get("current_task_index", 0) and status == "implementing"
        task_rows.append({
            "id": t.get("id", f"T{i + 1}"),
            "title": t.get("title", ""),
            "done": done,
            "current": current,
        })

    return templates.TemplateResponse(
        request,
        "pipeline.html",
        {
            "thread_id": thread_id,
            "ticket_id": ticket_id or "?",
            "mode": state.get("mode", "?"),
            "status_label": label,
            "status_css": css,
            "running": info["running"],
            "task_progress": f"{state.get('current_task_index', 0)}/{len(tasks)}" if tasks else "—",
            "tasks_total": len(tasks),
            "task_rows": task_rows,
            "implementation_log": state.get("implementation_log", []),
            "artifacts": artifacts,
            # JSON-safe copies for client-side rendering (marked.js).
            "artifacts_json": json.dumps(artifacts),
            "gate_json": json.dumps(info["pending_gate"]),
            "pending_gate": info["pending_gate"],
            "error": state.get("error"),
        },
    )
