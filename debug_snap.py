import asyncio
import os
import tempfile

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from core.graph import drive_graph_with_gates, build_sdd_graph
from test_sdd_gates import build_demo_graph, _config


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "c.sqlite")
        os.environ["CHECKPOINT_DB"] = db

        # 1. Write checkpoints with the DEMO graph (like the test does)
        async with AsyncSqliteSaver.from_conn_string(db) as cp:
            g_demo = build_demo_graph(checkpointer=cp)
            await drive_graph_with_gates(g_demo, {}, _config("dbg"), on_gate=None)

        # 2. Read them back through the RUNNER path (full SDD graph + fresh connection)
        from app.runner import PipelineRunner
        runner = PipelineRunner()
        print("checkpoint_path:", runner.checkpoint_path)
        info = await runner.get_state("dbg")
        print("info is None?", info is None)
        if info:
            print("info keys:", list(info.keys()))
            print("state:", info["state"])
            print("pending_gate:", info["pending_gate"])
            print("next:", info["next"])

        # 3. Raw peek: what does the demo graph itself see?
        async with AsyncSqliteSaver.from_conn_string(db) as cp:
            g_demo2 = build_demo_graph(checkpointer=cp)
            snap = await g_demo2.aget_state(_config("dbg"))
            print("demo-graph snapshot values:", dict(snap.values), "| next:", snap.next)
            for t in (snap.tasks or []):
                print("  task:", t.name, "interrupts:", getattr(t, "interrupts", None))

        os.environ.pop("CHECKPOINT_DB", None)


asyncio.run(main())
