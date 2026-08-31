"""
SDD Pipeline Graph Module
Builds the explicit LangGraph StateGraph for Spec-Driven Development:

    START -> fetch_ticket -> prepare_env -> write_spec -> gate_spec
      gate_spec --approved--> write_plan -> breakdown_tasks -> gate_plan
      gate_spec --revision--^ (loops back to write_spec with reviewer feedback)
      gate_plan --approved--> implement_task (self-loop, one task at a time)
      gate_plan --revision--> write_plan (with reviewer feedback)
    implement_task -> verify --passed--> finish --open PR--> END
                   verify --failed--> END

Phase 0: gates auto-approve (human_gates=False).
Phase 1: human_gates=True swaps in LangGraph interrupt() for real approval.
Phase 4: verify runs the real VerifyAgent (generated pytest tests + compliance
         report) and finish opens the pull request via GitHub MCP.
"""
import os
import time
import asyncio
from typing import Optional

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import interrupt, Command

from core.state import (
    SDDState,
    STATUS_SPEC_DRAFTING,
    STATUS_PENDING_SPEC_APPROVAL,
    STATUS_PLANNING,
    STATUS_PENDING_PLAN_APPROVAL,
    STATUS_IMPLEMENTING,
    STATUS_VERIFYING,
    STATUS_COMPLETED,
    STATUS_FAILED,
)
from core.artifacts import write_artifact, artifact_root
from tools.ticket_manager import TicketManager
from agents.environment_agent import EnvironmentAgent
from agents.spec_agent import SpecAgent
from agents.plan_agent import PlanAgent
from agents.task_agent import TaskAgent
from agents.local_developer_agent import LocalDeveloperAgent
from agents.developer_agent import RemoteDeveloperAgent
from agents.verify_agent import VerifyAgent


def _safe_id(ticket_id: str) -> str:
    return ticket_id.replace("/", "-").replace("#", "-")


def _render_tasks_md(tasks: list, title: str) -> str:
    lines = [f"# Tasks: {title}", ""]
    for t in tasks:
        lines.append(f"## {t.get('id')}: {t.get('title')}")
        lines.append(t.get("description", ""))
        for ac in t.get("acceptance_criteria", []):
            lines.append(f"- [ ] {ac}")
        lines.append("")
    return "\n".join(lines)


def _build_pr_body(state: SDDState, verification: dict) -> str:
    """Builds the markdown body of the pull request opened at pipeline end."""
    spec = state.get("spec", "")
    tasks = state.get("tasks", [])
    pytest_result = verification.get("pytest", {})

    lines = ["## Summary", "", spec[:1500], "", "## Tasks", ""]
    for t in tasks:
        lines.append(f"- [x] {t.get('id')}: {t.get('title')}")
    lines += [
        "",
        "## Verification",
        f"pytest exit code: {pytest_result.get('returncode')}",
        f"{verification.get('message', '')}",
        "",
    ]
    return "\n".join(lines)


def build_sdd_graph(human_gates: bool = False, checkpointer=None):
    """Compiles and returns the SDD StateGraph. Uses the given checkpointer (MemorySaver by default)."""
    ticket_manager = TicketManager()
    environment = EnvironmentAgent()
    spec_agent = SpecAgent()
    plan_agent = PlanAgent()
    task_agent = TaskAgent()
    local_developer = LocalDeveloperAgent()
    remote_developer = RemoteDeveloperAgent()
    verifier = VerifyAgent()

    # ---------------- Nodes ----------------

    async def fetch_ticket(state: SDDState) -> dict:
        ticket_id = state["ticket_id"]
        print(f"[Pipeline] Fetching ticket {ticket_id}...")
        ticket = await ticket_manager.get_ticket_details(ticket_id)
        if not ticket or not ticket.get("title"):
            return {"status": STATUS_FAILED, "error": f"Could not fetch ticket {ticket_id}"}
        await ticket_manager.transition_ticket(ticket_id, "In Progress")
        return {"ticket": ticket, "status": STATUS_SPEC_DRAFTING}

    async def prepare_env(state: SDDState) -> dict:
        print("[Pipeline] Preparing environment (clone/pull)...")
        result = await asyncio.to_thread(environment.prepare_environment, state["ticket"])
        if result.get("status") != "success":
            return {"status": STATUS_FAILED, "error": result.get("message", "Environment preparation failed")}
        prefix = "feature-local" if state.get("mode") == "local" else "feature"
        branch_name = f"{prefix}/{_safe_id(state['ticket_id'])}"
        return {
            "workspace_path": result["workspace_path"],
            "repo_full_name": result["repo_full_name"],
            "branch_name": branch_name,
            "status": STATUS_SPEC_DRAFTING,
        }

    async def write_spec(state: SDDState) -> dict:
        spec = await spec_agent.write_spec(
            state["ticket"], state["workspace_path"], feedback=state.get("spec_feedback", "")
        )
        repo_name = state["repo_full_name"].split("/")[-1]
        write_artifact(repo_name, state["ticket_id"], "spec.md", spec)
        return {"spec": spec, "spec_feedback": "", "status": STATUS_PENDING_SPEC_APPROVAL}

    def gate_spec(state: SDDState) -> dict:
        if not human_gates:
            print("[Pipeline] Gate 1 (spec): AUTO-APPROVED (Phase 0)")
            return {"status": STATUS_PLANNING}
        decision = interrupt({
            "gate": "spec",
            "artifact": "spec.md",
            "content": state["spec"],
            "question": "Approuvez la spécification ? (approve, or reject with feedback)",
        })
        if decision.get("approved"):
            return {"status": STATUS_PLANNING}
        print("[Pipeline] Gate 1 (spec): REJECTED — revising with feedback.")
        return {"status": STATUS_SPEC_DRAFTING, "spec_feedback": decision.get("feedback", "")}

    async def write_plan(state: SDDState) -> dict:
        plan = await plan_agent.write_plan(
            state["ticket"], state["spec"], state["workspace_path"], feedback=state.get("plan_feedback", "")
        )
        repo_name = state["repo_full_name"].split("/")[-1]
        write_artifact(repo_name, state["ticket_id"], "plan.md", plan)
        return {"plan": plan, "plan_feedback": "", "status": STATUS_PENDING_PLAN_APPROVAL}

    async def breakdown_tasks(state: SDDState) -> dict:
        tasks = await task_agent.breakdown_tasks(state["ticket"], state["spec"], state["plan"])
        repo_name = state["repo_full_name"].split("/")[-1]
        write_artifact(repo_name, state["ticket_id"], "tasks.md", _render_tasks_md(tasks, state["ticket"].get("title", "")))
        print(f"[Pipeline] Broken down into {len(tasks)} tasks.")
        return {"tasks": tasks, "current_task_index": 0, "status": STATUS_PENDING_PLAN_APPROVAL}

    def gate_plan(state: SDDState) -> dict:
        if not human_gates:
            print("[Pipeline] Gate 2 (plan/tasks): AUTO-APPROVED (Phase 0)")
            return {"status": STATUS_IMPLEMENTING}
        tasks_md = _render_tasks_md(state.get("tasks", []), state["ticket"].get("title", ""))
        decision = interrupt({
            "gate": "plan_tasks",
            "artifacts": ["plan.md", "tasks.md"],
            "content": f"{state['plan']}\n\n---\n\n{tasks_md}",
            "question": "Approuvez le plan et la décomposition en tâches ? (approve, or reject with feedback)",
        })
        if decision.get("approved"):
            return {"status": STATUS_IMPLEMENTING}
        print("[Pipeline] Gate 2 (plan/tasks): REJECTED — re-planning with feedback.")
        return {"status": STATUS_PLANNING, "plan_feedback": decision.get("feedback", "")}

    async def implement_task(state: SDDState) -> dict:
        tasks = state.get("tasks", [])
        idx = state.get("current_task_index", 0)
        if not tasks or idx >= len(tasks):
            return {"status": STATUS_FAILED, "error": "No task available for implementation."}
        task = tasks[idx]
        print(f"[Pipeline] Implementing task {task.get('id')} ({idx + 1}/{len(tasks)}): {task.get('title')}")

        if state.get("mode") == "local":
            result = await local_developer.implement_task(
                state["ticket"], state["spec"], state["plan"], task, state["branch_name"], state["workspace_path"]
            )
        else:
            result = await remote_developer.implement_task(
                state["ticket"], state["spec"], state["plan"], task, state["branch_name"], state["workspace_path"]
            )

        if result.get("status") != "success":
            return {
                "status": STATUS_FAILED,
                "error": f"Task {task.get('id')} failed: {result.get('message', '')}",
                "implementation_log": [f"{task.get('id')}: FAILED"],
            }
        return {
            "current_task_index": idx + 1,
            "implementation_log": [f"{task.get('id')} {task.get('title')}: done"],
            "status": STATUS_IMPLEMENTING,
        }

    async def verify(state: SDDState) -> dict:
        print("[Pipeline] Running verification (test generation + pytest + compliance report)...")
        result = await verifier.verify(
            state["ticket"], state["spec"], state["plan"], state.get("tasks", []),
            state["workspace_path"], state["branch_name"],
        )
        repo_name = state["repo_full_name"].split("/")[-1]
        write_artifact(repo_name, state["ticket_id"], "verification.md", result.get("report", ""))
        if result.get("status") != "passed":
            return {
                "verification": result,
                "status": STATUS_FAILED,
                "error": f"Verification failed: {result.get('message', '')}",
            }
        return {"verification": result, "status": STATUS_VERIFYING}

    async def finish(state: SDDState) -> dict:
        ticket_id = state["ticket_id"]
        print(f"[Pipeline] Finishing — opening PR and transitioning {ticket_id} to In Review...")

        # PR creation is non-fatal: the code is already pushed, so a failed MCP
        # call must not block the Jira transition (graceful degradation).
        pr_url = None
        try:
            verification = state.get("verification", {})
            result = await remote_developer.open_pull_request(
                state["ticket"], state["branch_name"], _build_pr_body(state, verification)
            )
            pr_url = result.get("pr_url")
            if not pr_url:
                print(f"[Pipeline] PR creation returned no URL: {result.get('message', '')}")
        except Exception as e:
            print(f"[Pipeline] PR creation failed (non-fatal): {e}")

        await ticket_manager.transition_ticket(ticket_id, "In Review")
        return {"status": STATUS_COMPLETED, "pr_url": pr_url}

    # ---------------- Routing ----------------

    def route_after_fetch(state: SDDState):
        return END if state.get("status") == STATUS_FAILED else "prepare_env"

    def route_after_env(state: SDDState):
        return END if state.get("status") == STATUS_FAILED else "write_spec"

    def route_after_spec_gate(state: SDDState):
        if state.get("status") == STATUS_SPEC_DRAFTING:
            return "write_spec"  # revision loop
        if state.get("status") == STATUS_FAILED:
            return END
        return "write_plan"

    def route_after_plan_gate(state: SDDState):
        if state.get("status") == STATUS_PLANNING:
            return "write_plan"  # re-plan loop
        if state.get("status") == STATUS_FAILED:
            return END
        return "implement_task"

    def route_after_implement(state: SDDState):
        if state.get("status") == STATUS_FAILED:
            return END
        if state.get("current_task_index", 0) < len(state.get("tasks", [])):
            return "implement_task"  # next task
        return "verify"

    def route_after_verify(state: SDDState):
        return END if state.get("status") == STATUS_FAILED else "finish"

    # ---------------- Graph assembly ----------------

    graph = StateGraph(SDDState)
    graph.add_node("fetch_ticket", fetch_ticket)
    graph.add_node("prepare_env", prepare_env)
    graph.add_node("write_spec", write_spec)
    graph.add_node("gate_spec", gate_spec)
    graph.add_node("write_plan", write_plan)
    graph.add_node("breakdown_tasks", breakdown_tasks)
    graph.add_node("gate_plan", gate_plan)
    graph.add_node("implement_task", implement_task)
    graph.add_node("verify", verify)
    graph.add_node("finish", finish)

    graph.add_edge(START, "fetch_ticket")
    graph.add_conditional_edges("fetch_ticket", route_after_fetch)
    graph.add_conditional_edges("prepare_env", route_after_env)
    graph.add_edge("write_spec", "gate_spec")
    graph.add_conditional_edges("gate_spec", route_after_spec_gate)
    graph.add_edge("write_plan", "breakdown_tasks")
    graph.add_conditional_edges("breakdown_tasks", lambda _: "gate_plan")
    graph.add_conditional_edges("gate_plan", route_after_plan_gate)
    graph.add_conditional_edges("implement_task", route_after_implement)
    graph.add_conditional_edges("verify", route_after_verify)
    graph.add_edge("finish", END)

    return graph.compile(checkpointer=checkpointer or MemorySaver())


async def drive_graph_with_gates(graph, initial_state: dict, config: dict, on_gate=None) -> dict:
    """Drives a compiled graph to completion, bridging human gates.

    Each time the graph pauses on an interrupt, `on_gate` (async callable:
    payload -> decision dict) is called and the graph resumes with
    Command(resume=decision). If `on_gate` is None, the first paused state is
    returned so a caller can resume it later on the same thread_id.
    """
    state = initial_state
    while True:
        state = await graph.ainvoke(state, config)
        interrupts = state.get("__interrupt__")
        if not interrupts:
            return state
        payload = interrupts[0].value
        if on_gate is None:
            print(f"[Pipeline] Paused at gate '{payload.get('gate')}' — awaiting external resume.")
            return state
        decision = await on_gate(payload)
        state = Command(resume=decision)


async def run_sdd_pipeline(ticket_id: str, mode: Optional[str] = None, human_gates: Optional[bool] = None, on_gate=None) -> dict:
    """Runs the SDD pipeline and returns the final state.

    Checkpoints are persisted to SQLite (CHECKPOINT_DB env or
    ./workspaces/.sdd/checkpoints.sqlite). With human gates enabled the graph
    pauses at each gate; `on_gate` is an async callable (payload) -> decision
    dict used to resume it. If `on_gate` is None, the first paused state is
    returned so a caller (e.g. the web backend) can resume later via
    Command(resume=...) on the same thread_id.
    """
    if mode is None:
        mode = os.environ.get("AGENT_MODE", "remote")
    if human_gates is None:
        human_gates = os.environ.get("HUMAN_GATES", "0") == "1"

    checkpoint_path = os.environ.get("CHECKPOINT_DB", os.path.join(artifact_root(), "checkpoints.sqlite"))
    print(f"[Pipeline] Starting SDD pipeline for {ticket_id} (mode={mode}, human_gates={human_gates})")

    async with AsyncSqliteSaver.from_conn_string(checkpoint_path) as checkpointer:
        graph = build_sdd_graph(human_gates=human_gates, checkpointer=checkpointer)
        config = {
            "configurable": {"thread_id": f"sdd-{_safe_id(ticket_id)}-{int(time.time())}"},
            "recursion_limit": 100,
        }

        initial_state: SDDState = {"ticket_id": ticket_id, "mode": mode}
        return await drive_graph_with_gates(graph, initial_state, config, on_gate=on_gate)
