"""
SupervisorAgent — backend-wired orchestrator (Story 5.2).

Responsibilities:
- Load ticket records and current project state from PostgreSQL via project_store.
- Delegate implementation work to LocalDeveloperAgent (AGENT_MODE=local) or
  RemoteDeveloperAgent (AGENT_MODE=remote).
- Publish progress events to the SSE stream via publish_event() after each
  meaningful action so the Chat View receives live updates.
- Enforce the agent hierarchy: no sub-agent may call another sub-agent directly.

Architecture rules (project-context.md):
- All agent invocations use:  await agent_executor.ainvoke({"messages": [("user", prompt)]})
- Configuration is read exclusively from os.environ.get(...) — never hard-coded.
- MCPManager is a singleton; access via await MCPManager.get_instance().
- LLM content may be a list when using Gemini multimodal responses — always guard.
"""

from __future__ import annotations

import os
import uuid
from typing import Sequence

from agents import token_tracker
from agents.environment_agent import EnvironmentAgent
from agents.local_developer_agent import LocalDeveloperAgent
from agents.developer_agent import RemoteDeveloperAgent
from agents.tester_agent import TesterAgent
from backend.api.sse import publish_event
from backend.store import project_store
from backend.store.errors import TestArtifactMissingError


class SupervisorAgent:
    """Backend-facing orchestrator that drives ticket execution end-to-end.

    This class is intentionally separate from the chat-oriented ``main_agent.py``
    so that the execution loop in ``execute.py`` has a clean, testable entry point
    that does not depend on MCP or interactive tooling.
    """

    def __init__(self) -> None:
        self.mode: str = os.environ.get("AGENT_MODE", "remote")

        # Sub-agent registry — only SupervisorAgent may invoke these.
        self.environment: EnvironmentAgent = EnvironmentAgent()
        self.local_developer: LocalDeveloperAgent = LocalDeveloperAgent()
        self.remote_developer: RemoteDeveloperAgent = RemoteDeveloperAgent()
        self.tester: TesterAgent = TesterAgent()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_tickets(
        self,
        project_id: str,
        ticket_ids: Sequence[str],
    ) -> dict:
        """Execute a sequence of tickets for *project_id*.

        Steps for each ticket:
        1. Load project state and ticket record from PostgreSQL.
        2. Publish a ``agent_log`` SSE event to notify the frontend.
        3. Delegate implementation to the appropriate developer sub-agent.
        4. Delegate test-writing to the TesterAgent.
        5. Update ticket status in the project store.
        6. Publish a completion event.

        Returns a summary dict ``{"project_id": ..., "results": [...]}``.
        """
        # Story 6.1: wire per-run token tracking ContextVars BEFORE any downstream
        # work. Every awaited call chain inherits the same Context (PEP 567), so
        # sub-agents' `tracked_ainvoke` calls read these transparently.
        session_id = str(uuid.uuid4())
        token_tracker.CURRENT_PROJECT_ID.set(project_id)
        token_tracker.CURRENT_SESSION_ID.set(session_id)
        token_tracker.reset_session(session_id)

        results = []

        for ticket_id in ticket_ids:
            result = await self._execute_ticket(project_id, ticket_id, ticket_ids)
            results.append(result)

        return {"project_id": project_id, "results": results}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _execute_ticket(
        self,
        project_id: str,
        ticket_id: str,
        ticket_ids: Sequence[str],
    ) -> dict:
        """Run the full lifecycle for a single ticket."""

        # --- AC-1: Load ticket record and project state from PostgreSQL -------
        await publish_event(
            project_id,
            "agent_log",
            {"message": f"[Supervisor] Loading project context for ticket {ticket_id}…"},
        )

        project = await project_store.get_project(project_id)
        if project is None:
            msg = f"[Supervisor] Project {project_id} not found — aborting ticket {ticket_id}."
            await publish_event(project_id, "agent_log", {"message": msg})
            return {"ticket_id": ticket_id, "status": "error", "reason": "project_not_found"}

        ticket = self._find_ticket(project, ticket_id)
        if ticket is None:
            msg = f"[Supervisor] Ticket {ticket_id} not found in project {project_id}."
            await publish_event(project_id, "agent_log", {"message": msg})
            return {"ticket_id": ticket_id, "status": "error", "reason": "ticket_not_found"}

        story_details = {
            "id": ticket_id,
            "title": ticket.get("title", ""),
            "description": ticket.get("description", ""),
            "project_id": project_id,
            "agent_memory": project.get("agent_memory"),
        }

        # Story 5.3 (AC-1, AC-2, AC-3): inject accumulated context from prior
        # completed tickets. Pure Python — no extra LLM or DB calls.
        accumulated_context = self._build_accumulated_context(
            project, ticket_ids, ticket_id
        )
        story_details["accumulated_context"] = accumulated_context

        # Story 5.10 (FR-21): inject default logging scaffold instruction on the
        # first ticket of any newly generated project. Pure Python — no LLM or
        # DB calls. Empty string on all subsequent tickets (uniform key shape).
        scaffold_instruction = ""
        if self._is_first_ticket(project, ticket_ids, ticket_id):
            scaffold_instruction = self._build_logging_scaffold_instruction(story_details)
            await publish_event(
                project_id,
                "agent_log",
                {
                    "message": (
                        f"[Supervisor] Injecting default logging scaffold "
                        f"instruction for first ticket {ticket_id} (FR-21)."
                    )
                },
            )
        story_details["logging_scaffold_instruction"] = scaffold_instruction

        description_parts = [
            part
            for part in (scaffold_instruction, accumulated_context, story_details["description"])
            if part
        ]
        story_details["description"] = "\n\n".join(description_parts)

        # --- AC-4: Publish progress after each meaningful action --------------
        await publish_event(
            project_id,
            "agent_log",
            {"message": f"[Supervisor] Preparing environment for ticket {ticket_id}…"},
        )

        # Environment setup (always synchronous; EnvironmentAgent.prepare_environment
        # returns a plain dict — no await needed per existing contract).
        env_result = self.environment.prepare_environment(story_details)
        if env_result.get("status") != "success":
            msg = f"[Supervisor] Environment preparation failed for ticket {ticket_id}."
            await publish_event(project_id, "agent_log", {"message": msg})
            await project_store.update_ticket_status(project_id, ticket_id, "Failed")
            return {"ticket_id": ticket_id, "status": "error", "reason": "environment_failed"}

        workspace_path = env_result.get("workspace_path")
        story_details["repo_full_name"] = env_result.get("repo_full_name")

        # Story 6.3 AC-6: persist workspace_path into agent_memory (JSONB
        # merge) so GET /projects/{id}/workspace/tree can locate the workspace
        # on demand. Fire-and-forget; failure here must not abort the ticket.
        if workspace_path:
            try:
                await project_store.update_agent_memory(
                    project_id,
                    {"workspace_path": workspace_path},
                )
            except Exception:
                pass

        # --- AC-2 & AC-3: Delegate to the correct developer sub-agent --------
        # (AC-3 is enforced structurally: only SupervisorAgent calls sub-agents)
        await publish_event(
            project_id,
            "agent_log",
            {
                "message": (
                    f"[Supervisor] Delegating to {self.mode.capitalize()}DeveloperAgent "
                    f"for ticket {ticket_id}…"
                )
            },
        )

        # AC-5: all agent invocations must be async (await ainvoke inside each agent)
        dev_result = await self._delegate_to_developer(story_details, workspace_path)

        if dev_result.get("status") != "success":
            msg = f"[Supervisor] Development phase failed for ticket {ticket_id}."
            await publish_event(project_id, "agent_log", {"message": msg})
            await project_store.update_ticket_status(project_id, ticket_id, "Failed")
            return {"ticket_id": ticket_id, "status": "error", "reason": "development_failed"}

        await publish_event(
            project_id,
            "agent_log",
            {"message": f"[Supervisor] Development complete — running tests for ticket {ticket_id}…"},
        )

        test_result = await self.tester.write_and_run_tests(
            story_details, dev_result.get("code_files", []), workspace_path
        )

        # Story 5.7: three-way branch on tester result.
        # Story 5.8 extends it to four-way — insufficient_logs inserted BEFORE
        # regression per FR-19 (instrumentation happens before any fix attempt).
        tester_status = test_result.get("status")
        if tester_status == "success":
            await project_store.update_ticket_status(project_id, ticket_id, "In Review")
            await publish_event(
                project_id,
                "agent_log",
                {"message": f"[Supervisor] Ticket {ticket_id} complete — status set to 'In Review'."},
            )
            return {
                "ticket_id": ticket_id,
                "status": "completed",
                "development": dev_result,
                "testing": test_result,
            }

        if tester_status == "insufficient_logs":
            return await self._handle_insufficient_logs_and_instrument(
                project_id,
                ticket_id,
                story_details,
                dev_result,
                workspace_path,
                test_result,
            )

        if tester_status == "regression":
            return await self._handle_regression_and_maybe_fix(
                project_id,
                ticket_id,
                story_details,
                dev_result,
                workspace_path,
                test_result,
            )

        # Error / unknown — preserve the Story 5.6 defensive branch verbatim.
        await publish_event(
            project_id,
            "agent_log",
            {"message": f"[Supervisor] Testing phase failed for ticket {ticket_id}."},
        )
        await project_store.update_ticket_status(project_id, ticket_id, "Error")
        return {"ticket_id": ticket_id, "status": "error", "reason": "testing_failed"}

    # -------------------------------------------------------------------------
    # Story 5.8: diagnostic logging before escalation (FR-19)
    # -------------------------------------------------------------------------

    async def _handle_insufficient_logs_and_instrument(
        self,
        project_id: str,
        ticket_id: str,
        story_details: dict,
        dev_result: dict,
        workspace_path: str | None,
        initial_test_result: dict,
    ) -> dict:
        """Add diagnostic logging, retest once, escalate if still unresolved."""
        await publish_event(
            project_id,
            "agent_log",
            {
                "message": (
                    f"[Supervisor] Insufficient log coverage for ticket {ticket_id} — "
                    f"adding diagnostic logging."
                ),
            },
        )

        instrumentation_targets = initial_test_result.get("instrumentation_targets") or []
        for target in instrumentation_targets:
            await publish_event(
                project_id,
                "agent_log",
                {"message": f"Adding diagnostic logging to {target}\u2026"},
            )

        # Shallow copy — never mutate caller's story_details (Story 5.3 guard).
        failures = initial_test_result.get("failures") or []
        failure_lines = "\n".join(
            f"- {f.get('test', '?')}: {f.get('message', '')}" for f in failures
        ) or "- (no per-test detail available)"
        targets_lines = "\n".join(f"- {t}" for t in instrumentation_targets) or "- (no targets)"
        instrumentation_block = (
            "--- Diagnostic logging report ---\n"
            f"Ticket: {ticket_id}\n"
            f"Failing tests:\n{failure_lines}\n"
            f"Files to instrument:\n{targets_lines}\n"
            f"Test artifact: {initial_test_result.get('test_artifact_ref', '')}\n"
            "Instruction: Add structured logging (Python `logging` module at INFO "
            "level for .py files, or the equivalent for the target stack) to the "
            "listed files. Preserve the additions — do NOT remove them after "
            "diagnosis. Commit and push to the existing branch.\n"
            "---------------------------------"
        )
        instr_story = dict(story_details)
        instr_story["description"] = (
            f"{instrumentation_block}\n\n{story_details.get('description', '')}"
        )

        branch_name = dev_result.get("branch") or f"feature/{ticket_id}"
        if self.mode == "local":
            fix_result = await self.local_developer.implement_pr_recommendations(
                instr_story, branch_name, workspace_path,
            )
        else:
            fix_result = await self.remote_developer.implement_pr_recommendations(
                instr_story, branch_name, workspace_path,
            )

        if fix_result.get("status") != "success":
            await publish_event(
                project_id,
                "agent_log",
                {
                    "message": (
                        f"[Supervisor] Diagnostic instrumentation attempt errored for "
                        f"ticket {ticket_id} — escalating."
                    ),
                },
            )
            return await self._escalate_diagnostic_logging(
                project_id,
                ticket_id,
                initial_test_result,
                instrumentation_attempt_summary=(
                    fix_result.get("message")
                    or fix_result.get("reason")
                    or "instrumentation attempt failed"
                ),
                retest_status=fix_result.get("status", "error"),
                story_details=story_details,
                dev_result=dev_result,
                workspace_path=workspace_path,
            )

        await publish_event(
            project_id,
            "agent_log",
            {
                "message": (
                    f"[Supervisor] Diagnostic logging committed for ticket {ticket_id} — "
                    f"re-running test suite."
                ),
            },
        )
        retest_result = await self.tester.write_and_run_tests(
            story_details, dev_result.get("code_files", []), workspace_path,
        )
        retest_status = retest_result.get("status")

        if retest_status == "success":
            await publish_event(
                project_id,
                "agent_log",
                {
                    "message": (
                        f"[Supervisor] Diagnostic logging resolved the issue for ticket "
                        f"{ticket_id} — proceeding to In Review."
                    ),
                },
            )
            await project_store.update_ticket_status(project_id, ticket_id, "In Review")
            return {
                "ticket_id": ticket_id,
                "status": "completed",
                "development": dev_result,
                "testing": retest_result,
                "diagnostic_logging": {
                    "attempted": True,
                    "outcome": "success",
                    "instrumentation_targets": instrumentation_targets,
                },
            }

        if retest_status == "regression":
            # Story 5.9 AC-6: forward diagnostic-instrumentation attempt into the
            # regression handler so its error report includes both attempts in order.
            prior = dev_result.get("_prior_attempts") or []
            dev_result = dict(dev_result)  # Story 5.3 leakage guard.
            dev_result["_prior_attempts"] = prior + [{
                "kind": "diagnostic_instrumentation",
                "summary": (
                    fix_result.get("message")
                    or fix_result.get("pr_url")
                    or "instrumentation committed"
                ),
                "test_artifact_ref": initial_test_result.get("test_artifact_ref", ""),
            }]
            regression_outcome = await self._handle_regression_and_maybe_fix(
                project_id, ticket_id, story_details, dev_result, workspace_path, retest_result,
            )
            regression_outcome["diagnostic_logging"] = {
                "attempted": True,
                "outcome": "regression_after_instrumentation",
                "instrumentation_targets": instrumentation_targets,
            }
            return regression_outcome

        return await self._escalate_diagnostic_logging(
            project_id,
            ticket_id,
            initial_test_result,
            instrumentation_attempt_summary=(
                fix_result.get("message")
                or fix_result.get("pr_url")
                or "instrumentation committed"
            ),
            retest_status=retest_status,
            story_details=story_details,
            dev_result=dev_result,
            workspace_path=workspace_path,
        )

    async def _escalate_diagnostic_logging(
        self,
        project_id: str,
        ticket_id: str,
        initial_test_result: dict,
        instrumentation_attempt_summary: str,
        retest_status: str,
        story_details: dict,
        dev_result: dict,
        workspace_path: str | None,
    ) -> dict:
        """Publish diagnostic_logging_escalation SSE, write error report, flip ticket to Error."""
        initial_failures = initial_test_result.get("failures") or []
        instrumentation_targets = initial_test_result.get("instrumentation_targets") or []

        log_references = [initial_test_result.get("test_artifact_ref", "")]
        attempted_fixes = [{
            "kind": "diagnostic_instrumentation",
            "summary": instrumentation_attempt_summary,
            "test_artifact_ref": initial_test_result.get("test_artifact_ref", ""),
        }]
        error_report_payload = await self._write_error_report_and_flag_branch(
            project_id, ticket_id, story_details, dev_result, workspace_path,
            failure_kind="diagnostic_logging_unresolved",
            description="Diagnostic logging did not restore log coverage",
            initial_failures=initial_failures,
            attempted_fixes=attempted_fixes,
            log_references=log_references,
        )

        payload = {
            "ticket_id": ticket_id,
            "initial_failures": initial_failures,
            "instrumentation_targets": instrumentation_targets,
            "instrumentation_attempt_summary": instrumentation_attempt_summary,
            "retest_status": retest_status,
            "error_report": error_report_payload,
            "options": ["view_report"],
        }
        await publish_event(project_id, "diagnostic_logging_escalation", payload)
        await publish_event(
            project_id,
            "agent_log",
            {
                "message": (
                    f"[Supervisor] Diagnostic logging did not restore log coverage for ticket "
                    f"{ticket_id} — error report written to project store; branch flagged with "
                    f"[ERROR] commit."
                ),
            },
        )
        await project_store.update_ticket_status(project_id, ticket_id, "Error")
        return {
            "ticket_id": ticket_id,
            "status": "blocked",
            "reason": "diagnostic_logging_unresolved",
            "instrumentation_targets": instrumentation_targets,
            "initial_failures": initial_failures,
            "error_report": error_report_payload,
        }

    # -------------------------------------------------------------------------
    # Story 5.9: shared error-report + flagged-commit helper (FR-20)
    # -------------------------------------------------------------------------

    async def _write_error_report_and_flag_branch(
        self,
        project_id: str,
        ticket_id: str,
        story_details: dict,
        dev_result: dict,
        workspace_path: str | None,
        failure_kind: str,
        description: str,
        initial_failures: list,
        attempted_fixes: list,
        log_references: list,
    ) -> dict:
        """Persist error report, push [ERROR]-flagged commit, best-effort Jira transition.

        Returns the fully-populated ``error_report_payload`` (including
        ``flagged_commit`` and ``jira_transition`` sub-dicts) for the caller
        to embed in the escalation SSE event and the ``_execute_ticket`` return.
        """
        branch_name = dev_result.get("branch") or f"feature/{ticket_id}"

        seen: set = set()
        filtered_refs: list = []
        for ref in log_references:
            if not ref or ref in seen:
                continue
            seen.add(ref)
            filtered_refs.append(ref)

        payload: dict = {
            "ticket_id": ticket_id,
            "failure_kind": failure_kind,
            "description": description,
            "initial_failures": list(initial_failures or []),
            "attempted_fixes": list(attempted_fixes or []),
            "log_references": filtered_refs,
            "branch": branch_name,
        }

        # Persist first — a hard failure here MUST propagate (system error).
        await project_store.write_error_report(project_id, ticket_id, payload)

        failure_lines = "\n".join(
            f"- {f.get('test', '?')}: {f.get('message', '')}"
            for f in payload["initial_failures"]
        ) or "- (no per-test detail available)"
        attempted_lines = "\n".join(
            f"- {a.get('kind', '?')}: {a.get('summary', '')} "
            f"(artifact: {a.get('test_artifact_ref', '')})"
            for a in payload["attempted_fixes"]
        ) or "- (no fix attempts recorded)"
        log_lines = "\n".join(f"- {p}" for p in payload["log_references"]) or "- (none)"
        flag_block = (
            "--- Error report ---\n"
            f"Ticket: {ticket_id}\n"
            f"Failure: {description}\n"
            f"Kind: {failure_kind}\n"
            f"Initial failures:\n{failure_lines}\n"
            f"Attempted fixes:\n{attempted_lines}\n"
            f"Log references:\n{log_lines}\n"
            "--------------------\n\n"
            f"Instruction: Write the contents above to a file named `ERROR_REPORT.md` "
            f"at the repository root (overwrite if it exists). Then commit ALL changes "
            f"on the existing branch `{branch_name}` with a commit message that starts "
            f"EXACTLY with the literal string `[ERROR] {ticket_id}: ` followed by "
            f"{description}. Push the commit to the same branch. Do NOT create a new "
            f"branch and do NOT open a new pull request."
        )
        flag_story = dict(story_details)  # Story 5.3 shallow-copy guard
        flag_story["description"] = flag_block

        if self.mode == "local":
            push_result = await self.local_developer.implement_pr_recommendations(
                flag_story, branch_name, workspace_path,
            )
        else:
            push_result = await self.remote_developer.implement_pr_recommendations(
                flag_story, branch_name, workspace_path,
            )
        if push_result.get("status") == "success":
            payload["flagged_commit"] = {"pushed": True, "branch": branch_name}
        else:
            await publish_event(project_id, "agent_log", {
                "message": (
                    f"[Supervisor] Failed to push flagged error commit for ticket "
                    f"{ticket_id} — error report persisted to project store only."
                ),
            })
            payload["flagged_commit"] = {
                "pushed": False,
                "reason": (
                    push_result.get("message")
                    or push_result.get("reason")
                    or "push failed"
                ),
            }

        if os.environ.get("TICKET_SYSTEM", "").lower() == "jira":
            # Lazy import — TicketManager pulls MCP tools at construction time.
            from tools.ticket_manager import TicketManager
            try:
                manager = TicketManager()
                jira_ok = bool(await manager.transition_ticket(ticket_id, "Error"))
            except Exception as exc:  # noqa: BLE001 — Jira is optional infrastructure
                await publish_event(project_id, "agent_log", {
                    "message": (
                        f"[Supervisor] Jira transition to Error failed for ticket "
                        f"{ticket_id}: {exc}"
                    ),
                })
                jira_ok = False
            else:
                if jira_ok:
                    await publish_event(project_id, "agent_log", {
                        "message": (
                            f"[Supervisor] Jira ticket {ticket_id} transitioned to Error."
                        ),
                    })
            payload["jira_transition"] = {"attempted": True, "success": jira_ok}
        else:
            payload["jira_transition"] = {"attempted": False, "success": False}

        return payload

    # -------------------------------------------------------------------------
    # Story 5.7: autonomous pre-merge regression fix
    # -------------------------------------------------------------------------

    async def _handle_regression_and_maybe_fix(
        self,
        project_id: str,
        ticket_id: str,
        story_details: dict,
        dev_result: dict,
        workspace_path: str | None,
        initial_test_result: dict,
    ) -> dict:
        """Attempt ONE autonomous fix for a regression, retest, escalate on failure."""
        await publish_event(
            project_id,
            "agent_log",
            {
                "message": (
                    f"[Supervisor] Regression detected for ticket {ticket_id} — "
                    f"attempting autonomous fix."
                ),
            },
        )

        # Build regression report on a SHALLOW COPY — never mutate the caller's
        # story_details, or Story 5.3 accumulated context will leak the report.
        failures = initial_test_result.get("failures") or []
        failure_lines = "\n".join(
            f"- {f.get('test', '?')}: {f.get('message', '')}" for f in failures
        ) or "- (no per-test detail available)"
        regression_block = (
            "--- Regression report ---\n"
            f"Ticket: {ticket_id}\n"
            f"Failing tests:\n{failure_lines}\n"
            f"Test artifact: {initial_test_result.get('test_artifact_ref', '')}\n"
            "-------------------------"
        )
        fix_story = dict(story_details)
        fix_story["description"] = (
            f"{regression_block}\n\n{story_details.get('description', '')}"
        )

        branch_name = dev_result.get("branch") or f"feature/{ticket_id}"
        if self.mode == "local":
            fix_result = await self.local_developer.implement_pr_recommendations(
                fix_story, branch_name, workspace_path,
            )
        else:
            fix_result = await self.remote_developer.implement_pr_recommendations(
                fix_story, branch_name, workspace_path,
            )

        if fix_result.get("status") != "success":
            await publish_event(
                project_id,
                "agent_log",
                {
                    "message": (
                        f"[Supervisor] Autonomous fix attempt errored for ticket "
                        f"{ticket_id} — escalating."
                    ),
                },
            )
            return await self._escalate_regression(
                project_id,
                ticket_id,
                initial_test_result,
                attempted_fix_summary=(
                    fix_result.get("message")
                    or fix_result.get("reason")
                    or "fix attempt failed"
                ),
                retest_result={"status": fix_result.get("status", "error"), "failures": []},
                story_details=story_details,
                dev_result=dev_result,
                workspace_path=workspace_path,
            )

        await publish_event(
            project_id,
            "agent_log",
            {"message": f"[Supervisor] Fix committed for ticket {ticket_id} — re-running test suite."},
        )
        retest_result = await self.tester.write_and_run_tests(
            story_details, dev_result.get("code_files", []), workspace_path,
        )

        if retest_result.get("status") == "success":
            await publish_event(
                project_id,
                "agent_log",
                {
                    "message": (
                        f"[Supervisor] Autonomous fix succeeded for ticket {ticket_id} "
                        f"— proceeding to Done."
                    ),
                },
            )
            close_result = await self.close_ticket_as_done(project_id, ticket_id)
            if close_result.get("status") != "done":
                # AD-6 gate refused — must not report success upstream.
                return await self._escalate_regression(
                    project_id,
                    ticket_id,
                    initial_test_result,
                    attempted_fix_summary=(
                        fix_result.get("message")
                        or "fix attempt succeeded but Done gate refused"
                    ),
                    retest_result=retest_result,
                    story_details=story_details,
                    dev_result=dev_result,
                    workspace_path=workspace_path,
                )
            return {
                "ticket_id": ticket_id,
                "status": "completed",
                "development": dev_result,
                "testing": retest_result,
                "regression_fix": {"attempted": True, "outcome": "success"},
            }

        return await self._escalate_regression(
            project_id,
            ticket_id,
            initial_test_result,
            attempted_fix_summary=(
                fix_result.get("message") or fix_result.get("pr_url") or "fix committed"
            ),
            retest_result=retest_result,
            story_details=story_details,
            dev_result=dev_result,
            workspace_path=workspace_path,
        )

    async def _escalate_regression(
        self,
        project_id: str,
        ticket_id: str,
        initial_test_result: dict,
        attempted_fix_summary: str,
        retest_result: dict,
        story_details: dict,
        dev_result: dict,
        workspace_path: str | None,
    ) -> dict:
        """Publish structured escalation SSE, write error report, flip ticket to Error."""
        initial_failures = initial_test_result.get("failures") or []
        retest_failures = retest_result.get("failures") or []

        log_references = [
            initial_test_result.get("test_artifact_ref", ""),
            retest_result.get("test_artifact_ref", ""),
        ]
        prior_attempts = (
            dev_result.get("_prior_attempts", []) if isinstance(dev_result, dict) else []
        )
        attempted_fixes = list(prior_attempts) + [{
            "kind": "autonomous_fix",
            "summary": attempted_fix_summary,
            "test_artifact_ref": retest_result.get("test_artifact_ref", ""),
        }]
        error_report_payload = await self._write_error_report_and_flag_branch(
            project_id, ticket_id, story_details, dev_result, workspace_path,
            failure_kind="regression_unfixed",
            description="Autonomous fix could not resolve regression",
            initial_failures=initial_failures,
            attempted_fixes=attempted_fixes,
            log_references=log_references,
        )

        payload = {
            "ticket_id": ticket_id,
            "initial_failures": initial_failures,
            "attempted_fix_summary": attempted_fix_summary,
            "retest_failures": retest_failures,
            "error_report": error_report_payload,
            "options": ["view_report"],
        }
        await publish_event(project_id, "regression_escalation", payload)
        await publish_event(
            project_id,
            "agent_log",
            {
                "message": (
                    f"[Supervisor] Autonomous fix failed for ticket {ticket_id} — "
                    "error report written to project store; branch flagged with [ERROR] commit."
                ),
            },
        )
        await project_store.update_ticket_status(project_id, ticket_id, "Error")
        return {
            "ticket_id": ticket_id,
            "status": "blocked",
            "reason": "regression_unfixed",
            "initial_failures": initial_failures,
            "retest_failures": retest_failures,
            "error_report": error_report_payload,
        }

    # --- AC-2: Route to the correct developer based on AGENT_MODE ------------

    async def _delegate_to_developer(
        self,
        story_details: dict,
        workspace_path: str | None,
    ) -> dict:
        """Delegate implementation to LocalDeveloperAgent or RemoteDeveloperAgent.

        AC-2: AGENT_MODE=local → LocalDeveloperAgent
              AGENT_MODE=remote (default) → RemoteDeveloperAgent
        AC-5: Both calls are awaited (async).
        """
        if self.mode == "local":
            return await self.local_developer.implement_feature(story_details, workspace_path)
        return await self.remote_developer.implement_feature(story_details, workspace_path)

    # -------------------------------------------------------------------------

    @staticmethod
    def _find_ticket(project: dict, ticket_id: str) -> dict | None:
        """Return the matching ticket record from the project's ticket_history."""
        history = project.get("ticket_history") or []
        for ticket in history:
            if isinstance(ticket, dict) and ticket.get("id") == ticket_id:
                return ticket
        return None

    # -------------------------------------------------------------------------
    # Story 5.10: default logging scaffold in generated projects (FR-21)
    # -------------------------------------------------------------------------

    @staticmethod
    def _is_first_ticket(
        project: dict, ticket_ids: Sequence[str], current_ticket_id: str
    ) -> bool:
        """FR-21: True iff this is the first ever ticket in the project.

        Positional (queue[0]) AND persistent (no prior Done/In Review in
        ``project.ticket_history``). Cross-session safe: on a re-run after a
        failed first ticket, this still returns True until at least one
        ticket has been closed successfully.
        """
        ticket_list = list(ticket_ids)
        if not ticket_list or ticket_list[0] != current_ticket_id:
            return False
        history = project.get("ticket_history") or []
        if not isinstance(history, list):
            return False
        closed = {"Done", "In Review"}
        for t in history:
            if isinstance(t, dict) and t.get("status") in closed:
                return False
        return True

    @staticmethod
    def _build_logging_scaffold_instruction(story_details: dict) -> str:
        """FR-21: static prompt block instructing the developer agent to
        include a working structured-logging scaffold in the generated repo.

        ``story_details`` is accepted for future per-project language
        overrides but is not consulted in the current implementation — the
        returned block is static.
        """
        return (
            "--- Logging scaffold requirement (FR-21) ---\n"
            "This is the FIRST ticket implemented in a newly generated project. "
            "In addition to the ticket's own acceptance criteria, the generated "
            "codebase MUST include a working structured logging scaffold. All "
            "subsequent tickets will import and reuse this scaffold — do NOT "
            "postpone it.\n\n"
            "Required elements:\n"
            "- Structured logging setup: configure Python's standard `logging` "
            "module (or the target stack's idiomatic equivalent if the project "
            "is not Python) at level `INFO` by default. Use "
            "`logging.basicConfig(level=..., format=\"%(asctime)s %(levelname)s "
            "%(name)s: %(message)s\")` or an equivalent framework-native "
            "configuration. Do NOT use `print()` as the diagnostic surface.\n"
            "- Reusable module logger: expose a module-level logger via "
            "`logger = logging.getLogger(__name__)` in each generated source "
            "module. The scaffold module itself MUST be importable by every "
            "subsequently generated module without requiring extra setup calls "
            "at import time (no `configure_logging()` call must be forced on "
            "downstream modules).\n"
            "- Env-var-driven level: read the log level from environment "
            "variable `LOG_LEVEL` with default `\"INFO\"`. Use "
            "`logging.getLevelName(os.environ.get(\"LOG_LEVEL\", \"INFO\").upper())` "
            "(or the target-stack equivalent) so `LOG_LEVEL=DEBUG`, `WARNING`, "
            "etc. all work. Invalid values MUST fall back to `INFO` — never "
            "raise at import time.\n"
            "- Passing pytest test: add a test file at `tests/test_logging.py` "
            "(or the project's existing test directory if one exists) "
            "containing at minimum a test named "
            "`test_logger_initializes_without_error` that (a) imports the "
            "logging scaffold module, (b) asserts "
            "`logging.getLogger(\"<scaffold_module_name>\")` returns a "
            "`logging.Logger` instance, and (c) asserts the configured level "
            "matches the default (`logging.INFO`) when `LOG_LEVEL` is unset. "
            "The test MUST pass under `pytest` with zero warnings introduced "
            "by the scaffold itself.\n"
            "- No hard-coded credentials, no external log sinks (no Sentry, "
            "Datadog, cloud logging clients) — stdout/stderr only. Any "
            "transport upgrade is a future ticket.\n"
            "- Idempotency: if a logging scaffold already exists in the target "
            "repo (a module already defines `logging.basicConfig` at import "
            "time, OR a file named `logging_config.py` / `logger.py` already "
            "lives at the repo root or `src/`), you MUST reuse and extend it "
            "rather than creating a parallel scaffold. Detection is best-effort "
            "file-existence + string-scan; on ambiguity, prefer reuse.\n"
            "--------------------------------------------"
        )

    # -------------------------------------------------------------------------
    # Story 5.3: cross-ticket accumulated context
    # -------------------------------------------------------------------------

    @staticmethod
    def _build_accumulated_context(
        project: dict,
        ticket_ids: Sequence[str],
        current_ticket_id: str,
    ) -> str:
        """Build a compact markdown summary of prior completed tickets.

        Only tickets whose id appears in ``ticket_ids`` *before* ``current_ticket_id``
        and whose status is ``Done`` or ``In Review`` are included. Returns ``""``
        when no such tickets exist. Pure Python — no LLM or DB calls (AC-3).
        """
        try:
            current_index = list(ticket_ids).index(current_ticket_id)
        except ValueError:
            return ""

        prior_ids = set(list(ticket_ids)[:current_index])
        if not prior_ids:
            return ""

        history = project.get("ticket_history") or []
        eligible_statuses = {"Done", "In Review"}

        entries: list[str] = []
        # Preserve execution-queue order rather than ticket_history order.
        history_by_id = {
            t.get("id"): t
            for t in history
            if isinstance(t, dict) and t.get("id") in prior_ids
        }
        for tid in list(ticket_ids)[:current_index]:
            ticket = history_by_id.get(tid)
            if ticket is None:
                continue
            if ticket.get("status") not in eligible_statuses:
                continue

            title = ticket.get("title", "") or ""
            file_list = ticket.get("file_list") or []
            notes = ticket.get("completion_notes") or ""

            lines = [f"[{tid}] {title}".rstrip()]
            if file_list:
                files_str = ", ".join(str(p) for p in file_list)
                lines.append(f"  Files: {files_str}")
            if notes:
                lines.append(f"  Notes: {notes}")
            else:
                lines.append("  Notes: (none)")
            entries.append("\n".join(lines))

        if not entries:
            return ""

        header = "--- Previously Completed Tickets ---"
        footer = "-------------------------------------"
        return f"{header}\n" + "\n\n".join(entries) + f"\n{footer}"

    # -------------------------------------------------------------------------
    # Story 5.6: gated Done transition (AD-6 / FR-17)
    # -------------------------------------------------------------------------

    async def close_ticket_as_done(
        self, project_id: str, ticket_id: str
    ) -> dict:
        """Gated Done transition — enforces AD-6 / FR-17.

        Wraps ``project_store.mark_ticket_done`` so callers never see an
        unhandled ``TestArtifactMissingError``. On a missing artifact the
        ticket is flipped to ``Error`` and an SSE ``agent_log`` event is
        published; on success an SSE confirmation is published and the
        caller receives ``{"status": "done"}``.
        """
        try:
            await project_store.mark_ticket_done(project_id, ticket_id)
        except TestArtifactMissingError:
            await publish_event(
                project_id,
                "agent_log",
                {
                    "message": (
                        f"[Supervisor] Test artifact missing for ticket {ticket_id} — "
                        f"cannot mark Done. FR-17/AD-6 violated."
                    ),
                },
            )
            await project_store.update_ticket_status(project_id, ticket_id, "Error")
            return {
                "ticket_id": ticket_id,
                "status": "error",
                "reason": "test_artifact_missing",
            }
        await publish_event(
            project_id,
            "agent_log",
            {
                "message": (
                    f"[Supervisor] Ticket {ticket_id} closed as Done "
                    f"(test artifact verified)."
                ),
            },
        )
        return {"ticket_id": ticket_id, "status": "done"}

