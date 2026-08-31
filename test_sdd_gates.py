"""
SDD Gate Mechanism Test
Verifies the human-in-the-loop machinery used by the SDD pipeline WITHOUT any
external service (no LLM, Jira, GitHub or Docker):

1. A gate is approved on the first attempt -> graph completes.
2. A gate is rejected once, then approved -> revision loop, then completion.
3. No on_gate callback -> graph returns a paused state carrying __interrupt__.
4. Checkpoints are persisted to a real SQLite file via AsyncSqliteSaver.
5. PipelineRunner reads state + pending gate from checkpoints and resumes across
   a fresh connection (the web backend's start/approve flow).

Run directly:  python test_sdd_gates.py
Or via pytest: pytest test_sdd_gates.py
"""
import asyncio
import os
import sqlite3
import tempfile
from typing import List, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import interrupt

from core.graph import drive_graph_with_gates
from core.state import SDDState, STATUS_COMPLETED, STATUS_SPEC_DRAFTING


class GateState(TypedDict, total=False):
    attempts: int
    status: str
    log: List[str]


def _gate_node(state: GateState) -> dict:
    # First run: raises GraphInterrupt (pause). After resume: returns the decision.
    decision = interrupt({"gate": "demo", "attempt": state.get("attempts", 0) + 1})
    if decision.get("approved"):
        return {"status": "done", "log": state.get("log", []) + ["approved"]}
    return {
        "attempts": state.get("attempts", 0) + 1,
        "status": "pending",
        "log": state.get("log", []) + [f"rejected: {decision.get('feedback')}"],
    }


def _route(state: GateState):
    return END if state.get("status") == "done" else "gate_node"


def build_demo_graph(checkpointer=None):
    graph = StateGraph(GateState)
    graph.add_node("gate_node", _gate_node)
    graph.add_edge(START, "gate_node")
    graph.add_conditional_edges("gate_node", _route)
    return graph.compile(checkpointer=checkpointer or MemorySaver())


def _stub_gate_spec(state: SDDState) -> dict:
    # Same state schema and node name as the real SDD graph's spec gate, so the
    # checkpoints are readable by PipelineRunner (which deserializes via the SDD graph).
    decision = interrupt({
        "gate": "spec",
        "artifact": "spec.md",
        "content": "STUB SPECIFICATION",
        "question": "approve?",
    })
    if decision.get("approved"):
        return {"status": STATUS_COMPLETED}
    return {"status": STATUS_SPEC_DRAFTING, "spec_feedback": decision.get("feedback", "")}


def build_stub_graph(checkpointer=None):
    graph = StateGraph(SDDState)
    graph.add_node("gate_spec", _stub_gate_spec)
    graph.add_edge(START, "gate_spec")
    graph.add_conditional_edges(
        "gate_spec", lambda s: END if s.get("status") == STATUS_COMPLETED else "gate_spec"
    )
    return graph.compile(checkpointer=checkpointer or MemorySaver())


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}


async def _auto_approve(payload: dict) -> dict:
    return {"approved": True, "feedback": ""}


async def scenario_approve():
    calls = []

    async def on_gate(payload: dict) -> dict:
        calls.append(payload)
        return {"approved": True, "feedback": ""}

    final = await drive_graph_with_gates(build_demo_graph(), {}, _config("t-approve"), on_gate=on_gate)
    assert final["status"] == "done", f"expected done, got {final.get('status')}"
    assert len(calls) == 1 and calls[0]["attempt"] == 1


async def scenario_reject_then_approve():
    decisions = iter([
        {"approved": False, "feedback": "add more detail"},
        {"approved": True, "feedback": ""},
    ])

    async def on_gate(payload: dict) -> dict:
        return next(decisions)

    final = await drive_graph_with_gates(build_demo_graph(), {}, _config("t-reject"), on_gate=on_gate)
    assert final["status"] == "done", f"expected done, got {final.get('status')}"
    assert final["attempts"] == 1, f"expected 1 rejection, got {final['attempts']}"
    assert any("add more detail" in entry for entry in final["log"]), "feedback missing from revision log"


async def scenario_paused():
    paused = await drive_graph_with_gates(build_demo_graph(), {}, _config("t-paused"), on_gate=None)
    assert "__interrupt__" in paused, "expected a paused state with __interrupt__"
    payload = paused["__interrupt__"][0].value
    assert payload["gate"] == "demo" and payload["attempt"] == 1


async def scenario_sqlite_persistence():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "checkpoints.sqlite")
        async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
            graph = build_demo_graph(checkpointer=checkpointer)
            final = await drive_graph_with_gates(graph, {}, _config("t-sqlite"), on_gate=_auto_approve)
        assert final["status"] == "done"
        assert os.path.exists(db_path) and os.path.getsize(db_path) > 0, "checkpoint file missing or empty"
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
        conn.close()
        assert rows >= 1, f"expected checkpoint rows in SQLite, got {rows}"


async def scenario_runner_state_reading():
    from app.runner import PipelineRunner

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "checkpoints.sqlite")
        os.environ["CHECKPOINT_DB"] = db_path
        try:
            runner = PipelineRunner()
            assert runner.checkpoint_path == db_path

            # Pause a pipeline at the spec gate (SDDState schema + real node name),
            # exactly like the web backend's background run does.
            async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
                stub = build_stub_graph(checkpointer=checkpointer)
                paused = await drive_graph_with_gates(
                    stub, {"ticket_id": "T-1", "mode": "local"}, _config("t-runner"), on_gate=None
                )
            assert "__interrupt__" in paused

            info = await runner.get_state("t-runner")
            assert info is not None, "get_state returned None for a known thread"
            assert info["pending_gate"] is not None and info["pending_gate"]["gate"] == "spec"
            assert "gate_spec" in info["next"], f"expected gate_spec in next, got {info['next']}"

            pipelines = await runner.list_pipelines()
            assert any(p["thread_id"] == "t-runner" for p in pipelines)

            # Resume across a fresh connection, exactly like POST /approve does.
            # The resume must use the same graph that wrote the checkpoints, so a
            # runner wired to the stub graph mirrors the production behavior here.
            stub_runner = PipelineRunner(graph_factory=lambda cp: build_stub_graph(cp))
            await stub_runner.resume_pipeline("t-runner", approved=True)
            await stub_runner._running["t-runner"]
            final = await stub_runner.get_state("t-runner")
            assert final["state"].get("status") == STATUS_COMPLETED
            assert final["pending_gate"] is None
        finally:
            os.environ.pop("CHECKPOINT_DB", None)


def test_approve():
    asyncio.run(scenario_approve())


def test_reject_then_approve():
    asyncio.run(scenario_reject_then_approve())


def test_paused_without_callback():
    asyncio.run(scenario_paused())


def test_sqlite_persistence():
    asyncio.run(scenario_sqlite_persistence())


def test_runner_state_reading():
    asyncio.run(scenario_runner_state_reading())


async def main():
    print("Running SDD gate mechanism tests...\n")
    await scenario_approve()
    print("[PASS] approve on first attempt")
    await scenario_reject_then_approve()
    print("[PASS] reject -> revision loop -> approve")
    await scenario_paused()
    print("[PASS] paused state returned without on_gate callback")
    await scenario_sqlite_persistence()
    print("[PASS] checkpoints persisted to SQLite")
    await scenario_runner_state_reading()
    print("[PASS] PipelineRunner reads state + pending gate from real checkpoints")
    print("\n[SUCCESS] All gate mechanism tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
