from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..crypto import encrypt
from ..database import get_db
from ..deps import get_or_create_app_settings, get_project_or_404

router = APIRouter(prefix="/api/v1", tags=["settings"])


def _to_out(row: models.AppSettings) -> schemas.AppSettingsOut:
    return schemas.AppSettingsOut(
        id=row.id,
        implementation_trigger_mode=row.implementation_trigger_mode,
        poll_interval_seconds=row.poll_interval_seconds,
        auto_trigger_jira_status=row.auto_trigger_jira_status,
        gemini_api_key_set=bool(row.encrypted_gemini_api_key),
    )


@router.get("/settings", response_model=schemas.AppSettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return _to_out(get_or_create_app_settings(db))


@router.put("/settings", response_model=schemas.AppSettingsOut)
def put_settings(payload: schemas.AppSettingsIn, db: Session = Depends(get_db)):
    row = get_or_create_app_settings(db)
    row.implementation_trigger_mode = payload.implementation_trigger_mode
    row.poll_interval_seconds = payload.poll_interval_seconds
    row.auto_trigger_jira_status = payload.auto_trigger_jira_status
    if payload.gemini_api_key is not None:
        row.encrypted_gemini_api_key = encrypt(payload.gemini_api_key) if payload.gemini_api_key else None
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.patch("/projects/{project_id}/implementation-trigger")
def patch_project_trigger(project_id: str, payload: schemas.TriggerModeIn, db: Session = Depends(get_db)):
    p = get_project_or_404(db, project_id)
    p.implementation_trigger_mode = payload.implementation_trigger_mode
    db.commit()
    db.refresh(p)
    return {"project_id": p.id, "implementation_trigger_mode": p.implementation_trigger_mode}
