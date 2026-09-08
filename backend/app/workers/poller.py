"""
Background poller for auto-triggered implementation runs.

Runs inside the FastAPI process as an asyncio task. On each tick it:
  1. Reads app_settings + per-project overrides
  2. For each project whose effective mode is 'auto_poll' and has both a
     Jira config and a repo config, queries Jira for issues matching the
     configured trigger status.
  3. For any issue that doesn't already have an 'implement' AgentRun logged,
     enqueues one.
"""
import asyncio
from datetime import datetime

from .. import models
from ..crypto import decrypt
from ..database import SessionLocal
from ..deps import get_effective_model_config
from ..queue import queue
from ..services.agents.implementer import run_implementation
from ..services.jira_client import JiraClient


async def _tick() -> None:
    db = SessionLocal()
    try:
        app_settings = db.query(models.AppSettings).first()
        if not app_settings:
            return
        for project in db.query(models.Project).all():
            effective_mode = project.implementation_trigger_mode or app_settings.implementation_trigger_mode
            if effective_mode != "auto_poll":
                continue
            jc = db.query(models.JiraConfig).filter_by(project_id=project.id).one_or_none()
            rc = db.query(models.RepoConfig).filter_by(project_id=project.id).one_or_none()
            if not (jc and rc):
                continue

            trigger_status = app_settings.auto_trigger_jira_status or "Ready for Dev"
            jql = f'project = "{jc.jira_project_key}" AND status = "{trigger_status}"'
            client = JiraClient(jc.site_url, jc.auth_email, decrypt(jc.encrypted_api_token))
            try:
                results = await client.search(jql=jql, fields="summary,status", max_results=25)
            except Exception:
                continue

            for issue in results.get("issues", []):
                key = issue.get("key")
                if not key:
                    continue
                existing = (
                    db.query(models.AgentRun)
                    .filter_by(project_id=project.id, run_type="implement", related_id=key)
                    .first()
                )
                if existing:
                    continue

                mc = get_effective_model_config(db, project.id)
                coding_model = mc.coding_model
                repo_pat = decrypt(rc.encrypted_pat)
                repo_owner = rc.org_or_owner
                repo_name = rc.repo_name

                run = models.AgentRun(
                    project_id=project.id,
                    run_type="implement",
                    related_id=key,
                    model_used=coding_model,
                    input_summary=f"auto: jira_issue={key}",
                )
                db.add(run)
                db.commit()
                db.refresh(run)

                async def job(sdb, run_id: str, _key=key, _model=coding_model, _pat=repo_pat, _o=repo_owner, _r=repo_name):
                    result = await run_implementation(
                        jira_issue_key=_key,
                        coding_model=_model,
                        repo_pat=_pat,
                        repo_owner=_o,
                        repo_name=_r,
                        mode="remote",
                    )
                    r = sdb.get(models.AgentRun, run_id)
                    if isinstance(result, dict) and result.get("status") == "failed":
                        raise RuntimeError(result.get("error", "implementation failed"))
                    r.output_summary = str(result)[:4000]
                    sdb.commit()

                queue.submit(run.id, job)
    finally:
        db.close()


async def poller_loop() -> None:
    while True:
        try:
            db = SessionLocal()
            row = db.query(models.AppSettings).first()
            interval = row.poll_interval_seconds if row else 60
            db.close()
            await _tick()
        except Exception as e:
            print(f"[poller] tick failed: {e}")
            interval = 60
        await asyncio.sleep(max(10, int(interval)))
