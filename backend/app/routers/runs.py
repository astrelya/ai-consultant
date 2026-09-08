from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
import asyncio

from .. import models, schemas
from ..crypto import decrypt
from ..database import SessionLocal, get_db
from ..deps import get_effective_model_config, get_project_or_404
from ..queue import queue
from ..services.agents.implementer import run_implementation

router = APIRouter(prefix="/api/v1", tags=["runs"])


@router.post("/projects/{project_id}/implement", response_model=schemas.AgentRunOut)
def enqueue_implement(project_id: str, payload: schemas.ImplementIn, db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    repo = db.query(models.RepoConfig).filter_by(project_id=project_id).one_or_none()
    if not repo:
        raise HTTPException(400, "Project has no repo config")

    model_cfg = get_effective_model_config(db, project_id)
    coding_model = model_cfg.coding_model
    repo_owner = repo.org_or_owner
    repo_name = repo.repo_name
    repo_pat = decrypt(repo.encrypted_pat)

    run = models.AgentRun(
        project_id=project_id,
        run_type="implement",
        related_id=payload.jira_issue_key,
        model_used=coding_model,
        input_summary=f"jira_issue={payload.jira_issue_key}",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    async def job(sdb, run_id: str):
        result = await run_implementation(
            jira_issue_key=payload.jira_issue_key,
            coding_model=coding_model,
            repo_pat=repo_pat,
            repo_owner=repo_owner,
            repo_name=repo_name,
            mode="remote",
        )
        r = sdb.get(models.AgentRun, run_id)
        if isinstance(result, dict) and result.get("status") == "failed":
            raise RuntimeError(result.get("error", "implementation failed"))
        r.output_summary = str(result)[:4000]

        # Record a PR row if a URL is present in the developer output.
        pr_url = None
        if isinstance(result, dict):
            dev = result.get("development") or {}
            pr_url = dev.get("pr_url")
        if pr_url:
            pr = models.PullRequest(
                project_id=project_id,
                jira_issue_key=payload.jira_issue_key,
                repo_config_id=repo.id,
                pr_url=pr_url,
                agent_run_id=run_id,
            )
            sdb.add(pr)
        sdb.commit()

    queue.submit(run.id, job)
    return run


@router.get("/agent-runs", response_model=list[schemas.AgentRunOut])
def list_runs(
    project_id: str | None = None,
    run_type: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.AgentRun)
    if project_id:
        q = q.filter(models.AgentRun.project_id == project_id)
    if run_type:
        q = q.filter(models.AgentRun.run_type == run_type)
    if status:
        q = q.filter(models.AgentRun.status == status)
    return q.order_by(models.AgentRun.created_at.desc()).limit(200).all()


@router.get("/agent-runs/{run_id}", response_model=schemas.AgentRunOut)
def get_run(run_id: str, db: Session = Depends(get_db)):
    r = db.get(models.AgentRun, run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    return r


@router.websocket("/ws/agent-runs/{run_id}")
async def ws_run_status(websocket: WebSocket, run_id: str):
    await websocket.accept()
    last_status = None
    try:
        while True:
            db = SessionLocal()
            try:
                r = db.get(models.AgentRun, run_id)
                if not r:
                    await websocket.send_json({"type": "error", "message": "Run not found"})
                    break
                if r.status != last_status:
                    last_status = r.status
                    await websocket.send_json({
                        "type": "status",
                        "status": r.status,
                        "output_summary": r.output_summary,
                        "error_message": r.error_message,
                    })
                if r.status in ("succeeded", "failed"):
                    break
            finally:
                db.close()
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.get("/pull-requests", response_model=list[schemas.PullRequestOut])
def list_prs(
    project_id: str | None = None,
    jira_issue_key: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.PullRequest)
    if project_id:
        q = q.filter(models.PullRequest.project_id == project_id)
    if jira_issue_key:
        q = q.filter(models.PullRequest.jira_issue_key == jira_issue_key)
    return q.order_by(models.PullRequest.created_at.desc()).all()
