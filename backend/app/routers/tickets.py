from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..crypto import decrypt
from ..database import get_db
from ..services.jira_client import JiraClient

router = APIRouter(prefix="/api/v1/ticket-drafts", tags=["ticket-drafts"])


@router.get("", response_model=list[schemas.TicketDraftOut])
def list_drafts(
    project_id: str | None = None,
    session_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.TicketDraft)
    if project_id:
        q = q.filter(models.TicketDraft.project_id == project_id)
    if session_id:
        q = q.filter(models.TicketDraft.chat_session_id == session_id)
    if status:
        q = q.filter(models.TicketDraft.status == status)
    return q.order_by(models.TicketDraft.order_index.asc(), models.TicketDraft.created_at.asc()).all()


@router.get("/{draft_id}", response_model=schemas.TicketDraftOut)
def get_draft(draft_id: str, db: Session = Depends(get_db)):
    d = db.get(models.TicketDraft, draft_id)
    if not d:
        raise HTTPException(404, "Draft not found")
    return d


@router.patch("/{draft_id}", response_model=schemas.TicketDraftOut)
def edit_draft(draft_id: str, payload: schemas.TicketDraftUpdate, db: Session = Depends(get_db)):
    d = db.get(models.TicketDraft, draft_id)
    if not d:
        raise HTTPException(404, "Draft not found")
    if d.status in ("pushed",):
        raise HTTPException(400, "Cannot edit a pushed draft")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(d, k, v)
    if data:
        d.status = "edited"
    db.commit()
    db.refresh(d)
    return d


@router.post("/{draft_id}/accept", response_model=schemas.TicketDraftOut)
def accept_draft(draft_id: str, db: Session = Depends(get_db)):
    d = db.get(models.TicketDraft, draft_id)
    if not d:
        raise HTTPException(404, "Draft not found")
    d.status = "accepted"
    db.commit()
    db.refresh(d)
    return d


@router.post("/{draft_id}/reject", response_model=schemas.TicketDraftOut)
def reject_draft(draft_id: str, db: Session = Depends(get_db)):
    d = db.get(models.TicketDraft, draft_id)
    if not d:
        raise HTTPException(404, "Draft not found")
    d.status = "rejected"
    db.commit()
    db.refresh(d)
    return d


@router.post("/batch-accept", response_model=list[schemas.TicketDraftOut])
def batch_accept(payload: schemas.BatchIdsIn, db: Session = Depends(get_db)):
    drafts = db.query(models.TicketDraft).filter(models.TicketDraft.id.in_(payload.draft_ids)).all()
    for d in drafts:
        if d.status not in ("pushed",):
            d.status = "accepted"
    db.commit()
    return drafts


async def _push_one(db: Session, draft: models.TicketDraft) -> None:
    if draft.jira_issue_key:
        return  # idempotent
    jc = db.query(models.JiraConfig).filter_by(project_id=draft.project_id).one_or_none()
    if not jc:
        raise RuntimeError("Project has no Jira config")
    client = JiraClient(jc.site_url, jc.auth_email, decrypt(jc.encrypted_api_token))
    description = draft.description
    if draft.acceptance_criteria:
        description += "\n\nAcceptance Criteria:\n" + "\n".join(f"- {c}" for c in draft.acceptance_criteria)
    created = await client.create_issue(
        project_key=jc.jira_project_key,
        summary=draft.title,
        description=description,
        issue_type=draft.issue_type or jc.default_issue_type,
        priority=draft.priority,
        labels=draft.labels or None,
    )
    draft.jira_issue_key = created.get("key")
    draft.status = "pushed"
    draft.push_error = None


@router.post("/push", response_model=list[schemas.TicketDraftOut])
async def push_drafts(payload: schemas.BatchIdsIn, db: Session = Depends(get_db)):
    drafts = db.query(models.TicketDraft).filter(models.TicketDraft.id.in_(payload.draft_ids)).all()
    for d in drafts:
        if d.status != "accepted":
            continue
        try:
            await _push_one(db, d)
        except Exception as e:
            d.status = "push_failed"
            d.push_error = str(e)[:4000]
    db.commit()
    for d in drafts:
        db.refresh(d)
    return drafts


@router.post("/{draft_id}/retry-push", response_model=schemas.TicketDraftOut)
async def retry_push(draft_id: str, db: Session = Depends(get_db)):
    d = db.get(models.TicketDraft, draft_id)
    if not d:
        raise HTTPException(404, "Draft not found")
    if d.status not in ("accepted", "push_failed"):
        raise HTTPException(400, f"Cannot push draft in status '{d.status}'")
    try:
        await _push_one(db, d)
    except Exception as e:
        d.status = "push_failed"
        d.push_error = str(e)[:4000]
    db.commit()
    db.refresh(d)
    return d
