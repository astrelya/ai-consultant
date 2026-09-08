from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_project_or_404

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.post("", response_model=schemas.ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(payload: schemas.ProjectCreate, db: Session = Depends(get_db)):
    p = models.Project(name=payload.name, description=payload.description)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("", response_model=list[schemas.ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(models.Project).order_by(models.Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=schemas.ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    return get_project_or_404(db, project_id)


@router.patch("/{project_id}", response_model=schemas.ProjectOut)
def update_project(project_id: str, payload: schemas.ProjectUpdate, db: Session = Depends(get_db)):
    p = get_project_or_404(db, project_id)
    if payload.name is not None:
        p.name = payload.name
    if payload.description is not None:
        p.description = payload.description
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    p = get_project_or_404(db, project_id)
    db.delete(p)
    db.commit()


@router.get("/{project_id}/token-usage")
def get_token_usage(project_id: str, db: Session = Depends(get_db)):
    get_project_or_404(db, project_id)

    # Chat tokens grouped by model
    chat_rows = (
        db.query(
            models.ChatMessage.model_used,
            func.coalesce(func.sum(models.ChatMessage.input_tokens), 0),
            func.coalesce(func.sum(models.ChatMessage.output_tokens), 0),
            func.count(models.ChatMessage.id),
        )
        .join(models.ChatSession, models.ChatMessage.session_id == models.ChatSession.id)
        .filter(models.ChatSession.project_id == project_id)
        .filter(models.ChatMessage.role == "assistant")
        .group_by(models.ChatMessage.model_used)
        .all()
    )

    # Agent-run tokens grouped by model
    run_rows = (
        db.query(
            models.AgentRun.model_used,
            models.AgentRun.run_type,
            func.coalesce(func.sum(models.AgentRun.input_tokens), 0),
            func.coalesce(func.sum(models.AgentRun.output_tokens), 0),
            func.count(models.AgentRun.id),
        )
        .filter(models.AgentRun.project_id == project_id)
        .group_by(models.AgentRun.model_used, models.AgentRun.run_type)
        .all()
    )

    by_model: dict[str, dict] = {}

    def _bucket(model: str | None) -> dict:
        key = model or "unknown"
        if key not in by_model:
            by_model[key] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "calls": 0}
        return by_model[key]

    chat_totals = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
    for model_used, in_toks, out_toks, calls in chat_rows:
        b = _bucket(model_used)
        b["input_tokens"] += int(in_toks)
        b["output_tokens"] += int(out_toks)
        b["total_tokens"] += int(in_toks) + int(out_toks)
        b["calls"] += int(calls)
        chat_totals["input_tokens"] += int(in_toks)
        chat_totals["output_tokens"] += int(out_toks)
        chat_totals["calls"] += int(calls)

    run_totals: dict[str, dict] = {}
    for model_used, run_type, in_toks, out_toks, calls in run_rows:
        b = _bucket(model_used)
        b["input_tokens"] += int(in_toks)
        b["output_tokens"] += int(out_toks)
        b["total_tokens"] += int(in_toks) + int(out_toks)
        b["calls"] += int(calls)
        r = run_totals.setdefault(run_type, {"input_tokens": 0, "output_tokens": 0, "calls": 0})
        r["input_tokens"] += int(in_toks)
        r["output_tokens"] += int(out_toks)
        r["calls"] += int(calls)

    total_input = sum(b["input_tokens"] for b in by_model.values())
    total_output = sum(b["output_tokens"] for b in by_model.values())
    return {
        "project_id": project_id,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "by_model": by_model,
        "chat_totals": chat_totals,
        "run_totals": run_totals,
    }
