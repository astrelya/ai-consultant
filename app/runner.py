"""
SDD Pipeline Runner (web backend)
Manages background pipeline executions and reads their state from the LangGraph
checkpoint database. The checkpoint DB is the single source of truth, so
pipeline state survives server restarts.
"""
import asyncio
import os
import time
from typing import Optional

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from core.graph import build_sdd_graph, drive_graph_with_gates


def _safe_id(ticket_id: str) -> str:
    return ticket_id.replace("/", "-").replace("#", "-")


class PipelineRunner:
    def __init__(self, graph_factory=None):
        self._running: dict[str, asyncio.Task] = {}
        # Injectable for tests: a callable (checkpointer) -> compiled graph.
        if graph_factory is None:
            def graph_factory(checkpointer):
                return build_sdd_graph(human_gates=True, checkpointer=checkpointer)
        self._graph_factory = graph_factory

    @property
    def checkpoint_path(self) -> str:
        from core.artifacts import artifact_root
        return os.environ.get("CHECKPOINT_DB", os.path.join(artifact_root(), "checkpoints.sqlite"))

    def is_running(self, thread_id: str) -> bool:
        task = self._running.get(thread_id)
        return task is not None and not task.done()

    async def start_pipeline(self, ticket_id: str, mode: Optional[str] = None) -> str:
        if mode is None:
            mode = os.environ.get("AGENT_MODE", "remote")
        thread_id = f"sdd-{_safe_id(ticket_id)}-{int(time.time())}"
        self._running[thread_id] = asyncio.create_task(self._run(thread_id, ticket_id, mode))
        return thread_id

    async def resume_pipeline(self, thread_id: str, approved: bool, feedback: str = "") -> None:
        if self.is_running(thread_id):
            raise RuntimeError("Pipeline is currently running; it cannot be resumed.")
        decision = {"approved": approved, "feedback": feedback}
        self._running[thread_id] = asyncio.create_task(self._resume(thread_id, decision))

    async def _run(self, thread_id: str, ticket_id: str, mode: str) -> None:
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 100}
        try:
            async with AsyncSqliteSaver.from_conn_string(self.checkpoint_path) as checkpointer:
                graph = self._graph_factory(checkpointer)
                # on_gate=None: the run pauses at the first gate and returns;
                # the dashboard resumes it via resume_pipeline().
                await drive_graph_with_gates(
                    graph, {"ticket_id": ticket_id, "mode": mode}, config, on_gate=None
                )
        except Exception as e:
            print(f"[Runner] Pipeline {thread_id} crashed: {e}")

    async def _resume(self, thread_id: str, decision: dict) -> None:
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 100}
        try:
            async with AsyncSqliteSaver.from_conn_string(self.checkpoint_path) as checkpointer:
                graph = self._graph_factory(checkpointer)
                await drive_graph_with_gates(
                    graph, Command(resume=decision), config, on_gate=None
                )
        except Exception as e:
            print(f"[Runner] Resume of {thread_id} crashed: {e}")

    async def get_state(self, thread_id: str) -> Optional[dict]:
        """Reads the latest state snapshot for a pipeline from the checkpoint DB."""
        if not os.path.exists(self.checkpoint_path):
            return None
        async with AsyncSqliteSaver.from_conn_string(self.checkpoint_path) as checkpointer:
            graph = self._graph_factory(checkpointer)
            snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
        if snapshot is None or not snapshot.values:
            return None

        pending_gate = None
        for task in (snapshot.tasks or []):
            interrupts = getattr(task, "interrupts", None)
            if interrupts:
                pending_gate = interrupts[0].value
                break

        return {
            "thread_id": thread_id,
            "state": dict(snapshot.values),
            "next": list(snapshot.next),
            "pending_gate": pending_gate,
            "running": self.is_running(thread_id),
        }

    async def list_pipelines(self) -> list:
        if not os.path.exists(self.checkpoint_path):
            return []
        async with aiosqlite.connect(self.checkpoint_path) as db:
            cursor = await db.execute("SELECT DISTINCT thread_id FROM checkpoints")
            rows = await cursor.fetchall()

        pipelines = []
        for (thread_id,) in rows:
            info = await self.get_state(thread_id)
            if info is not None:
                pipelines.append(info)
        return pipelines


# Shared singleton used by both the JSON API and the dashboard.
runner = PipelineRunner()
