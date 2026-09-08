from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from . import models


def get_project_or_404(db: Session, project_id: str) -> models.Project:
    p = db.get(models.Project, project_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return p


def get_effective_model_config(db: Session, project_id: str) -> models.ModelConfig:
    project_cfg = (
        db.query(models.ModelConfig).filter(models.ModelConfig.project_id == project_id).one_or_none()
    )
    if project_cfg:
        return project_cfg
    default = db.query(models.ModelConfig).filter(models.ModelConfig.project_id.is_(None)).one_or_none()
    if not default:
        default = models.ModelConfig(project_id=None)
        db.add(default)
        db.commit()
        db.refresh(default)
    return default


def get_or_create_app_settings(db: Session) -> models.AppSettings:
    row = db.query(models.AppSettings).first()
    if not row:
        row = models.AppSettings()
        db.add(row)
        db.commit()
        db.refresh(row)
    return row
