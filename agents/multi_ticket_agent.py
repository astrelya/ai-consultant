import asyncio
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from agents.main_agent import SupervisorAgent
from tools.dependency_analyzer import DependencyAnalyzer
from tools.mcp_loader import MCPManager
from backend.websocket import broadcast_log, broadcast_input_required
import os


class MultiTicketOrchestrator:
    def __init__(self):
        self.supervisor = SupervisorAgent()
        self.dependency_analyzer = DependencyAnalyzer()

    # ------------------------------------------------------------------
    # Branch resolution helpers
    # ------------------------------------------------------------------

    def _get_parents(self, tid: str, adj_list: dict) -> list:
        """Returns the list of tickets that tid directly depends on."""
        return [p for p, children in adj_list.items() if tid in children]

    async def _try_merge_branches(
        self,
        owner: str,
        repo: str,
        parent_branches: list,
        integration_branch: str,
        default_branch: str,
        job_id: str,
    ) -> bool:
        """
        Creates an integration branch from the default branch and merges all
        parent_branches into it via the GitHub MCP tool 'merge_branches'.
        Returns True on full success, False if any merge fails.
        """
        manager = await MCPManager.get_instance()
        github_tools = manager.github_tools
        if not github_tools:
            return False

        model_name = os.environ.get("TICKET_MODEL", "gemini-2.5-flash")
        llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

        prompt = f"""You are a Git integration agent.

Repository: owner='{owner}', repo='{repo}'

You must create an integration branch and merge several feature branches into it.
Follow these steps exactly:

1. Create branch '{integration_branch}' from '{default_branch}' using create_branch.
2. For each branch in {parent_branches}, call merge_branches (or the equivalent tool) to merge it into '{integration_branch}'.
3. If any merge fails due to a conflict, stop immediately and report the failing branch.

At the end, output a raw JSON object (no markdown):
{{"success": true, "failed_branch": null}}
or
{{"success": false, "failed_branch": "<name of branch that caused the conflict>"}}
"""
        agent = create_agent(llm, github_tools)
        result = await agent.ainvoke({"messages": [("user", prompt)]})
        content_raw = result["messages"][-1].content
        if isinstance(content_raw, list):
            content = "".join(
                p.get("text", "") if isinstance(p, dict) else str(p) for p in content_raw
            ).strip()
        else:
            content = str(content_raw).strip()

        # Strip markdown if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        try:
            data = json.loads(content)
            if data.get("success"):
                return True
            failed = data.get("failed_branch", "unknown")
            await broadcast_log(
                f"  Merge conflict on branch '{failed}' into '{integration_branch}'.",
                job_id, "WARNING",
            )
            return False
        except Exception:
            # Can't parse result — assume failure to be safe
            return False

    async def _resolve_base_branch(
        self,
        tid: str,
        adj_list: dict,
        ticket_branches: dict,
        owner: str,
        repo: str,
        default_branch: str,
        job_id: str,
    ) -> str | None:
        """
        Returns the base branch that tid should branch from.
        - No parents → default_branch
        - 1 parent → that parent's feature branch
        - N parents → try to create an integration branch; if merge fails return None
        """
        parents = self._get_parents(tid, adj_list)

        if not parents:
            return default_branch

        if len(parents) == 1:
            parent = parents[0]
            branch = ticket_branches.get(parent)
            if branch:
                await broadcast_log(
                    f"  {tid} will branch from '{branch}' (dependency on {parent}).",
                    job_id,
                )
                return branch
            return default_branch

        # Multiple parents
        parent_branches = [ticket_branches.get(p) for p in parents if ticket_branches.get(p)]
        if not parent_branches:
            return default_branch

        integration_branch = f"integration/{tid}-deps"
        await broadcast_log(
            f"  {tid} has multiple dependencies ({parents}). "
            f"Attempting to create integration branch '{integration_branch}'...",
            job_id, "WARNING",
        )

        success = await self._try_merge_branches(
            owner, repo, parent_branches, integration_branch, default_branch, job_id
        )
        if success:
            await broadcast_log(
                f"  Integration branch '{integration_branch}' ready for {tid}.", job_id
            )
            return integration_branch

        return None  # Caller must handle the unresolvable case

    # ------------------------------------------------------------------
    # Main orchestration
    # ------------------------------------------------------------------

    async def execute_tickets(self, ticket_ids: list, job_id: str) -> dict:
        """
        Executes a list of tickets respecting their dependency graph.
        Tickets in the same layer run in parallel.
        Dependent tickets branch from their parent's feature branch.
        Multi-parent tickets get an auto-merged integration branch,
        or the user is asked to merge manually if there are conflicts.
        """
        await broadcast_log(f"Starting multi-ticket orchestrator for {ticket_ids}...", job_id)

        # 1. Build DAG
        dag = await self.dependency_analyzer.build_dag(ticket_ids)

        # 2. Topological sort → parallelizable layers
        in_degree = {node: 0 for node in ticket_ids}
        adj_list = {node: [] for node in ticket_ids}

        for node, successors in dag.items():
            if node not in adj_list:
                adj_list[node] = []
            for successor in successors:
                if successor in in_degree:
                    adj_list[node].append(successor)
                    in_degree[successor] += 1

        layers = []
        visited = set()
        while len(visited) < len(ticket_ids):
            current_layer = [
                node for node in ticket_ids if in_degree[node] == 0 and node not in visited
            ]
            if not current_layer:
                remaining = [node for node in ticket_ids if node not in visited]
                await broadcast_log(
                    f"Warning: Circular dependency detected. Scheduling {remaining} sequentially.",
                    job_id, "WARNING",
                )
                layers.append(remaining)
                break
            layers.append(current_layer)
            for node in current_layer:
                visited.add(node)
                for successor in adj_list[node]:
                    in_degree[successor] -= 1

        await broadcast_log(f"Topological sorting produced {len(layers)} layer(s):", job_id)
        for idx, layer in enumerate(layers):
            await broadcast_log(f"  Layer {idx}: {layer}", job_id)

        # Determine repo owner/name from environment (needed for integration branches)
        default_branch = os.environ.get("GITHUB_DEFAULT_BRANCH", "main")
        github_owner = os.environ.get("GITHUB_OWNER", "")
        github_repo = os.environ.get("GITHUB_REPO", "")

        # 3. Execute layer by layer
        results = {}
        failed_tickets = set()
        ticket_branches: dict[str, str] = {}  # tid → feature branch name after implementation

        for idx, layer in enumerate(layers):
            await broadcast_log(f"--- Executing Layer {idx} ({len(layer)} ticket(s)) ---", job_id)

            # Filter tickets whose dependencies failed
            runnable = []
            for tid in layer:
                has_failed_dep = any(
                    tid in children and parent in failed_tickets
                    for parent, children in adj_list.items()
                )
                if has_failed_dep:
                    results[tid] = {"status": "skipped", "message": "Prerequisite ticket failed."}
                    await broadcast_log(f"⏩ {tid} skipped (dependency failed).", job_id, "WARNING")
                else:
                    runnable.append(tid)

            if not runnable:
                continue

            # Resolve base branches for each runnable ticket
            base_branches: dict[str, str] = {}
            blocked_for_merge: list[str] = []

            for tid in runnable:
                base = await self._resolve_base_branch(
                    tid, adj_list, ticket_branches, github_owner, github_repo, default_branch, job_id
                )
                if base is None:
                    # Integration branch merge failed — ask user
                    parents = self._get_parents(tid, adj_list)
                    parent_branches = [ticket_branches.get(p, p) for p in parents]
                    await broadcast_log(
                        f"⚠️  Cannot auto-merge dependencies for {tid}. "
                        f"Please merge these branches manually before continuing: {parent_branches}",
                        job_id, "WARNING",
                    )
                    blocked_for_merge.append(tid)
                else:
                    base_branches[tid] = base

            # If some tickets are blocked on manual merges, ask the user
            if blocked_for_merge:
                prompt_msg = (
                    f"Tickets {blocked_for_merge} require manual branch merges before they can be implemented. "
                    f"Please merge the required branches in GitHub, then reply **continue** to proceed "
                    f"or **skip** to skip these tickets."
                )
                user_answer = await broadcast_input_required(prompt_msg, job_id, timeout=300)
                user_answer = (user_answer or "").strip().lower()

                if user_answer == "continue":
                    # Re-attempt with default branch (user should have merged already)
                    for tid in blocked_for_merge:
                        base_branches[tid] = default_branch
                else:
                    for tid in blocked_for_merge:
                        results[tid] = {
                            "status": "skipped",
                            "message": "Skipped: user chose not to merge dependencies.",
                        }
                        failed_tickets.add(tid)
                        await broadcast_log(f"⏩ {tid} skipped by user.", job_id, "WARNING")
                    runnable = [t for t in runnable if t not in blocked_for_merge]

            if not runnable:
                continue

            await broadcast_log(f"Running tickets in parallel: {runnable}", job_id)

            async def run_ticket_logged(tid):
                await broadcast_log(f"🚀 Triggering development flow for {tid}...", job_id)
                base = base_branches.get(tid, default_branch)
                try:
                    res = await self.supervisor.run(tid, job_id, base_branch=base)
                    return tid, res
                except Exception as e:
                    return tid, {"status": "failed", "message": str(e)}

            tasks = [run_ticket_logged(tid) for tid in runnable]
            layer_results = await asyncio.gather(*tasks)

            for tid, res in layer_results:
                if isinstance(res, dict):
                    status = res.get("status", "success")
                    # Track feature branch for downstream tickets
                    branch = res.get("branch") or res.get("development", {}).get("branch")
                    if branch:
                        ticket_branches[tid] = branch
                else:
                    status = "failed"
                    res = {"status": "failed", "message": str(res)}

                results[tid] = res

                if status in ("success", "completed"):
                    await broadcast_log(f"✅ Ticket {tid} succeeded.", job_id, "SUCCESS")
                else:
                    failed_tickets.add(tid)
                    await broadcast_log(f"❌ Ticket {tid} failed: {res}", job_id, "ERROR")

        # Summary
        success_count = sum(
            1 for res in results.values()
            if isinstance(res, dict) and res.get("status") in ("success", "completed")
        )
        fail_count = len(failed_tickets)
        skip_count = sum(
            1 for res in results.values()
            if isinstance(res, dict) and res.get("status") == "skipped"
        )

        summary_msg = f"Orchestrator Summary: {success_count} succeeded, {fail_count} failed, {skip_count} skipped."
        await broadcast_log(summary_msg, job_id, "SUCCESS" if fail_count == 0 else "ERROR")
        await broadcast_log("[Orchestrator] Job execution complete.", job_id, "ERROR" if fail_count else "SUCCESS")

        return {
            "status": "success" if fail_count == 0 else "failed",
            "message": summary_msg,
            "results": results,
        }


    async def execute_tickets(self, ticket_ids: list, job_id: str) -> dict:
        """
        Executes a list of tickets, analyzing their dependencies first,
        sorting them topologically, and running independent tickets in parallel.
        """
        await broadcast_log(f"Starting multi-ticket orchestrator for {ticket_ids}...", job_id)
        
        # 1. Build DAG
        dag = await self.dependency_analyzer.build_dag(ticket_ids)
        
        # 2. Topologically sort the DAG into parallelizable layers
        # In-degree of each node
        in_degree = {node: 0 for node in ticket_ids}
        # Successors list
        adj_list = {node: [] for node in ticket_ids}
        
        for node, successors in dag.items():
            if node not in adj_list:
                adj_list[node] = []
            for successor in successors:
                if successor in in_degree:
                    adj_list[node].append(successor)
                    in_degree[successor] += 1

        # Build layers
        layers = []
        visited = set()
        
        while len(visited) < len(ticket_ids):
            # Nodes with in-degree 0 that haven't been visited yet
            current_layer = [node for node in ticket_ids if in_degree[node] == 0 and node not in visited]
            
            if not current_layer:
                # Loop detected or orphaned nodes
                remaining = [node for node in ticket_ids if node not in visited]
                await broadcast_log(f"Warning: Circular dependency or orphaned nodes detected in DAG. Scheduling remaining tickets {remaining} sequentially.", job_id, "WARNING")
                layers.append(remaining)
                break
                
            layers.append(current_layer)
            for node in current_layer:
                visited.add(node)
                for successor in adj_list[node]:
                    in_degree[successor] -= 1

        await broadcast_log(f"Topological sorting produced {len(layers)} execution layer(s):", job_id)
        for idx, layer in enumerate(layers):
            await broadcast_log(f"  Layer {idx}: {layer}", job_id)

        # 3. Execute layer by layer
        results = {}
        failed_tickets = set()
        
        for idx, layer in enumerate(layers):
            await broadcast_log(f"--- Executing Layer {idx} ({len(layer)} ticket(s)) ---", job_id)
            
            # Filter tickets whose dependencies failed
            runnable = []
            for tid in layer:
                # Check if any parent/dependency failed
                has_failed_dep = False
                for parent, children in adj_list.items():
                    if tid in children and parent in failed_tickets:
                        has_failed_dep = True
                        break
                        
                if has_failed_dep:
                    results[tid] = {
                        "status": "skipped",
                        "message": "Prerequisite ticket execution failed."
                    }
                    await broadcast_log(f"⏩ Ticket {tid} skipped due to dependency failure.", job_id, "WARNING")
                else:
                    runnable.append(tid)

            if not runnable:
                continue

            # Run runnable tickets in parallel
            await broadcast_log(f"Running tickets in parallel: {runnable}", job_id)
            
            async def run_ticket_logged(tid):
                await broadcast_log(f"🚀 Triggering development flow for {tid}...", job_id)
                try:
                    res = await self.supervisor.run(tid, job_id)
                    return tid, res
                except Exception as e:
                    return tid, {"status": "failed", "message": str(e)}

            tasks = [run_ticket_logged(tid) for tid in runnable]
            layer_results = await asyncio.gather(*tasks)
            
            for tid, res in layer_results:
                results[tid] = res
                if isinstance(res, dict):
                    status = res.get("status", "success")
                else:
                    # supervisor.run() returns a plain string only on early-exit errors
                    status = "failed"
                    results[tid] = {"status": "failed", "message": str(res)}
                
                if status in ("success", "completed"):
                    await broadcast_log(f"✅ Ticket {tid} succeeded.", job_id, "SUCCESS")
                else:
                    failed_tickets.add(tid)
                    await broadcast_log(f"❌ Ticket {tid} failed: {res}", job_id, "ERROR")

        # Summarize
        success_count = sum(1 for res in results.values() if isinstance(res, dict) and res.get("status") in ("success", "completed"))
        fail_count = len(failed_tickets)
        skip_count = sum(1 for res in results.values() if isinstance(res, dict) and res.get("status") == "skipped")
        
        summary_msg = f"Orchestrator Summary: {success_count} succeeded, {fail_count} failed, {skip_count} skipped."
        await broadcast_log(summary_msg, job_id, "SUCCESS" if fail_count == 0 else "ERROR")
        
        return {
            "status": "success" if fail_count == 0 else "failed",
            "message": summary_msg,
            "results": results
        }
