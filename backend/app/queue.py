"""
Simple in-process asyncio task queue for agent runs.

For a single-user, local-only app this is sufficient: FastAPI's own event loop
runs the worker coroutines. Swappable for Celery/RQ if the app ever needs to
scale beyond one process.
"""
import asyncio
from datetime import datetime
from typing import Awaitable, Callable

from sqlalchemy.orm import Session

from . import models
from .database import SessionLocal


AgentJob = Callable[[Session, str], Awaitable[None]]


class RunQueue:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def submit(self, run_id: str, job: AgentJob) -> None:
        task = asyncio.create_task(self._run(run_id, job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, run_id: str, job: AgentJob) -> None:
        db = SessionLocal()
        try:
            run = db.get(models.AgentRun, run_id)
            if not run:
                return
            run.status = "running"
            run.started_at = datetime.utcnow()
            db.commit()

            try:
                await job(db, run_id)
                run = db.get(models.AgentRun, run_id)
                if run and run.status == "running":
                    run.status = "succeeded"
            except Exception as e:
                run = db.get(models.AgentRun, run_id)
                if run:
                    run.status = "failed"
                    run.error_message = str(e)[:4000]
            finally:
                run = db.get(models.AgentRun, run_id)
                if run:
                    run.finished_at = datetime.utcnow()
                    db.commit()
        finally:
            db.close()


queue = RunQueue()
