from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..crypto import encrypt, decrypt
from ..database import get_db
from ..deps import get_project_or_404, get_effective_model_config
from ..services.jira_client import JiraClient
from ..services.github_client import GitHubClient

router = APIRouter(prefix="/api/v1", tags=["configs"])


# ---------------- Repo Config ----------------
@router.post("/projects/{project_id}/repo-config", response_model=schemas.RepoConfigOut)
def upsert_repo_config(project_id: str, payload: schemas.RepoConfigIn, db: Session = Depends(get_db)):
    get_project_or_404(db, project_id)
    existing = db.query(models.RepoConfig).filter_by(project_id=project_id).one_or_none()
    if existing:
        existing.org_or_owner = payload.org_or_owner
        existing.repo_name = payload.repo_name
        existing.default_branch = payload.default_branch
        existing.encrypted_pat = encrypt(payload.pat)
        db.commit()
        db.refresh(existing)
        return existing
    rc = models.RepoConfig(
        project_id=project_id,
        org_or_owner=payload.org_or_owner,
        repo_name=payload.repo_name,
        default_branch=payload.default_branch,
        encrypted_pat=encrypt(payload.pat),
    )
    db.add(rc)
    db.commit()
    db.refresh(rc)
    return rc


@router.post("/projects/{project_id}/repo-config/test")
async def test_repo_config(project_id: str, db: Session = Depends(get_db)):
    rc = db.query(models.RepoConfig).filter_by(project_id=project_id).one_or_none()
    if not rc:
        raise HTTPException(404, "No repo config for this project")
    client = GitHubClient(decrypt(rc.encrypted_pat))
    try:
        repo = await client.get_repo(rc.org_or_owner, rc.repo_name)
        return {"ok": True, "full_name": repo.get("full_name"), "default_branch": repo.get("default_branch")}
    except Exception as e:
        raise HTTPException(400, f"GitHub validation failed: {e}")


@router.delete("/projects/{project_id}/repo-config", status_code=204)
def delete_repo_config(project_id: str, db: Session = Depends(get_db)):
    rc = db.query(models.RepoConfig).filter_by(project_id=project_id).one_or_none()
    if rc:
        db.delete(rc)
        db.commit()


@router.get("/projects/{project_id}/repo-config", response_model=schemas.RepoConfigOut | None)
def get_repo_config(project_id: str, db: Session = Depends(get_db)):
    return db.query(models.RepoConfig).filter_by(project_id=project_id).one_or_none()


# ---------------- Jira Config ----------------
@router.post("/projects/{project_id}/jira-config", response_model=schemas.JiraConfigOut)
def upsert_jira_config(project_id: str, payload: schemas.JiraConfigIn, db: Session = Depends(get_db)):
    get_project_or_404(db, project_id)
    existing = db.query(models.JiraConfig).filter_by(project_id=project_id).one_or_none()
    if existing:
        existing.site_url = payload.site_url
        existing.jira_project_key = payload.jira_project_key
        existing.default_issue_type = payload.default_issue_type
        existing.auth_email = payload.auth_email
        existing.encrypted_api_token = encrypt(payload.api_token)
        db.commit()
        db.refresh(existing)
        return existing
    jc = models.JiraConfig(
        project_id=project_id,
        site_url=payload.site_url,
        jira_project_key=payload.jira_project_key,
        default_issue_type=payload.default_issue_type,
        auth_email=payload.auth_email,
        encrypted_api_token=encrypt(payload.api_token),
    )
    db.add(jc)
    db.commit()
    db.refresh(jc)
    return jc


@router.post("/projects/{project_id}/jira-config/test")
async def test_jira_config(project_id: str, db: Session = Depends(get_db)):
    jc = db.query(models.JiraConfig).filter_by(project_id=project_id).one_or_none()
    if not jc:
        raise HTTPException(404, "No Jira config for this project")
    client = JiraClient(jc.site_url, jc.auth_email, decrypt(jc.encrypted_api_token))
    try:
        me = await client.myself()
        proj = await client.project(jc.jira_project_key)
        return {"ok": True, "account_id": me.get("accountId"), "project_name": proj.get("name")}
    except Exception as e:
        raise HTTPException(400, f"Jira validation failed: {e}")


@router.delete("/projects/{project_id}/jira-config", status_code=204)
def delete_jira_config(project_id: str, db: Session = Depends(get_db)):
    jc = db.query(models.JiraConfig).filter_by(project_id=project_id).one_or_none()
    if jc:
        db.delete(jc)
        db.commit()


@router.get("/projects/{project_id}/jira-config", response_model=schemas.JiraConfigOut | None)
def get_jira_config(project_id: str, db: Session = Depends(get_db)):
    return db.query(models.JiraConfig).filter_by(project_id=project_id).one_or_none()


# ---------------- Model Config ----------------
@router.get("/model-configs/default", response_model=schemas.ModelConfigOut)
def get_default_model_config(db: Session = Depends(get_db)):
    row = db.query(models.ModelConfig).filter(models.ModelConfig.project_id.is_(None)).one_or_none()
    if not row:
        row = models.ModelConfig(project_id=None)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.put("/model-configs/default", response_model=schemas.ModelConfigOut)
def put_default_model_config(payload: schemas.ModelConfigIn, db: Session = Depends(get_db)):
    row = db.query(models.ModelConfig).filter(models.ModelConfig.project_id.is_(None)).one_or_none()
    if not row:
        row = models.ModelConfig(project_id=None)
        db.add(row)
    row.chat_model = payload.chat_model
    row.coding_model = payload.coding_model
    row.chat_model_params = payload.chat_model_params
    row.coding_model_params = payload.coding_model_params
    db.commit()
    db.refresh(row)
    return row


@router.get("/projects/{project_id}/model-config", response_model=schemas.ModelConfigOut)
def get_project_model_config(project_id: str, db: Session = Depends(get_db)):
    get_project_or_404(db, project_id)
    return get_effective_model_config(db, project_id)


@router.put("/projects/{project_id}/model-config", response_model=schemas.ModelConfigOut)
def put_project_model_config(project_id: str, payload: schemas.ModelConfigIn, db: Session = Depends(get_db)):
    get_project_or_404(db, project_id)
    row = db.query(models.ModelConfig).filter_by(project_id=project_id).one_or_none()
    if not row:
        row = models.ModelConfig(project_id=project_id)
        db.add(row)
    row.chat_model = payload.chat_model
    row.coding_model = payload.coding_model
    row.chat_model_params = payload.chat_model_params
    row.coding_model_params = payload.coding_model_params
    db.commit()
    db.refresh(row)
    return row
