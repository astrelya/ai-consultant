---
baseline_commit: b873c0bec72ac891aa89d1b0fcf39a979992fbc7
---

# Story 5.9: Error Report and Flagged Commit

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want to receive a full error report and see the branch pushed with a clearly flagged commit when the agent cannot resolve a failure,
so that I can diagnose the problem myself, CI systems can detect the error state automatically, and the queue keeps moving instead of stalling on a single unresolvable ticket (FR-20 / Epic 5).

## Acceptance Criteria

1. **Given** `SupervisorAgent._handle_regression_and_maybe_fix` reaches its escalation path (Story 5.7: the one-shot autonomous fix either errored out or the retest still returned `status == "regression"`) OR `SupervisorAgent._handle_insufficient_logs_and_instrument` reaches its escalation path (Story 5.8: the instrumentation attempt errored out, or the retest returned `insufficient_logs` again, or the retest returned `error`/unknown)
   **When** the escalation is triggered
   **Then** the supervisor MUST invoke a new private helper `await self._write_error_report_and_flag_branch(project_id, ticket_id, story_details, dev_result, workspace_path, failure_kind, error_report_payload)` BEFORE calling `project_store.update_ticket_status` and BEFORE publishing the existing `regression_escalation` / `diagnostic_logging_escalation` structured SSE event. `failure_kind` is a string literal — `"regression_unfixed"` (from Story 5.7) or `"diagnostic_logging_unresolved"` (from Story 5.8) — used verbatim in the error report and returned in the escalation dict. `error_report_payload` is the structured dict described in AC-2.

2. **And** `_write_error_report_and_flag_branch` MUST build an `error_report_payload` dict with EXACTLY these keys (order not significant; extra keys forbidden):
   - `ticket_id` (str): the ticket id.
   - `failure_kind` (str): `"regression_unfixed"` or `"diagnostic_logging_unresolved"` — matches AC-1.
   - `description` (str): a one-line human-readable summary (e.g. `"Autonomous fix could not resolve regression"` or `"Diagnostic logging did not restore log coverage"`). The exact strings are asserted by tests — see Task 4 for the required values per failure_kind.
   - `initial_failures` (list): copied from the initial tester result. `[]` if none.
   - `attempted_fixes` (list[dict]): each dict has `{"kind": <str>, "summary": <str>, "test_artifact_ref": <str or empty>}`. The regression path emits one entry with `kind="autonomous_fix"`; the diagnostic-logging path emits one entry with `kind="diagnostic_instrumentation"`; the diagnostic-logging → regression fall-through path (Story 5.8 AC-6) is HANDLED BY THE STORY 5.7 REGRESSION ESCALATION PATH — it emits TWO entries in order: `[{"kind": "diagnostic_instrumentation", ...}, {"kind": "autonomous_fix", ...}]` (see AC-6 below for how the diagnostic-logging handler forwards its context into the regression handler).
   - `log_references` (list[str]): file paths of every `test_artifact_ref` collected during this ticket's execution (initial run + retest(s)), in chronological order. Empty strings and duplicates are filtered out.
   - `branch` (str): the branch name from `dev_result.get("branch")` (fall back to `f"feature/{ticket_id}"` — same convention as the existing escalation code).

3. **And** `_write_error_report_and_flag_branch` MUST persist the full report to the project store via a new async helper `project_store.write_error_report(project_id, ticket_id, error_report_payload)` (see AC-8). The call MUST use `await`. The helper MUST NOT raise on well-formed input; a `ValueError` propagates only if `error_report_payload` is not a dict or is missing the required keys listed in AC-2.

4. **And** `_write_error_report_and_flag_branch` MUST delegate a flagged-commit push to the developer agent by calling `implement_pr_recommendations(flag_story, branch_name, workspace_path)` on the same routing pattern as Stories 5.7 and 5.8 (`self.local_developer` if `self.mode == "local"`, else `self.remote_developer`). `flag_story` is a **shallow copy** of `story_details` (Story 5.3 leakage guard) whose `description` is REPLACED (not appended) with the following block, built verbatim from `error_report_payload`:
   ```
   --- Error report ---
   Ticket: <ticket_id>
   Failure: <description>
   Kind: <failure_kind>
   Initial failures:
   - <test>: <message>
   ...
   Attempted fixes:
   - <kind>: <summary> (artifact: <test_artifact_ref>)
   ...
   Log references:
   - <path>
   ...
   --------------------

   Instruction: Write the contents above to a file named `ERROR_REPORT.md` at the repository root (overwrite if it exists). Then commit ALL changes on the existing branch `<branch>` with a commit message that starts EXACTLY with the literal string `[ERROR] <ticket_id>: ` followed by <description>. Push the commit to the same branch. Do NOT create a new branch and do NOT open a new pull request.
   ```
   The `[ERROR] ` prefix is a bracketed literal followed by a single space — no leading whitespace, no ANSI codes, no ellipsis. The prompt above uses `<...>` placeholders — substitute the concrete values before sending. Description-replacement (not append) is deliberate: the original story context is irrelevant to the flagged-commit step and would waste tokens.

5. **And** if `implement_pr_recommendations` for the flagged-commit push returns `status != "success"`, the supervisor MUST NOT retry, MUST NOT raise, MUST publish an `agent_log` SSE event `{"message": "[Supervisor] Failed to push flagged error commit for ticket <id> — error report persisted to project store only."}`, and MUST set `error_report_payload["flagged_commit"] = {"pushed": False, "reason": <fix_result.get("message") or fix_result.get("reason") or "push failed">}` on the payload before it is included in the escalation SSE event (AC-9). On success, set `error_report_payload["flagged_commit"] = {"pushed": True, "branch": branch_name}`. The push failure MUST NOT change the ticket state transition (AC-7) or the queue-continuation invariant (AC-10) — the persisted `error_report` in the store is still authoritative.

6. **And** the diagnostic-logging → regression fall-through path (Story 5.8 AC-6, `_handle_insufficient_logs_and_instrument` returning `_handle_regression_and_maybe_fix(...)`) MUST propagate the diagnostic-instrumentation attempt into the regression handler's error report. Implementation: `_handle_insufficient_logs_and_instrument` MUST stash the instrumentation attempt on the passed `dev_result` dict — specifically `dev_result["_prior_attempts"] = [{"kind": "diagnostic_instrumentation", "summary": <summary>, "test_artifact_ref": <initial_test_result.get("test_artifact_ref", "")>}]` — BEFORE calling `_handle_regression_and_maybe_fix`. `_handle_regression_and_maybe_fix` (when it in turn escalates) MUST prepend `dev_result.get("_prior_attempts", [])` to its own `attempted_fixes` list when building the payload. The `_prior_attempts` key is transient (in-memory only, never persisted) — it is NEVER passed to `write_error_report` and is NEVER included in the SSE event. Tests assert that the final report contains BOTH entries in order (see Task 4).

7. **And** after `_write_error_report_and_flag_branch` returns, the supervisor MUST call `await project_store.update_ticket_status(project_id, ticket_id, "Error")` — REPLACING the `"Agent Blocked"` transition that Stories 5.7 and 5.8 currently perform. `"Error"` is already declared in the architecture ticket state machine (spine §"Ticket state machine"). `"Agent Blocked"` remains a valid state but is no longer written on the unresolvable-failure path — the "Continue / Abandon" user-interactive gate is deferred to a future story (out of scope). Both escalation SSE events (`regression_escalation`, `diagnostic_logging_escalation`) MUST STILL be published — they now inform the user of a completed error transition rather than requesting input. The `options` field in each existing payload MUST be replaced with `["view_report"]` (single-element list). No new SSE event type is introduced by this story — the existing event types remain the discovery surface; consumers already know how to route them.

8. **And** if `TICKET_SYSTEM == "jira"` (read via `os.environ.get("TICKET_SYSTEM", "").lower() == "jira"` at method-invocation time — same env-read pattern as Story 5.7's `TESTER_MOCK_MODE` and Story 5.8's, NEVER at import time), the supervisor MUST additionally attempt a best-effort Jira transition. Implementation: `_write_error_report_and_flag_branch` MUST import `tools.ticket_manager.TicketManager` lazily inside the method (avoid top-level import — `TicketManager` pulls MCP tools and is expensive to construct at supervisor import time), construct `TicketManager()` once, and call `await manager.transition_ticket(ticket_id, "Error")`. Wrap the call in a broad `try/except Exception` — the Jira MCP is optional infrastructure and a network/auth failure MUST NOT prevent the PostgreSQL transition, the flagged-commit push, or the queue continuation. On exception, publish an `agent_log` event `{"message": "[Supervisor] Jira transition to Error failed for ticket <id>: <str(exc)>"}` and continue. On success (return value truthy), publish `{"message": "[Supervisor] Jira ticket <id> transitioned to Error."}`. Store the outcome on `error_report_payload["jira_transition"] = {"attempted": True, "success": <bool>}` for the SSE payload. If `TICKET_SYSTEM != "jira"`, set `error_report_payload["jira_transition"] = {"attempted": False, "success": False}` and skip the import and construction entirely (no MCP subprocess spawned).

9. **And** the existing `regression_escalation` and `diagnostic_logging_escalation` SSE payloads MUST be extended with `"error_report": <error_report_payload>` (the full dict from AC-2 including the AC-5 `flagged_commit` and AC-8 `jira_transition` fields) and MUST have their `options` list REPLACED with `["view_report"]` per AC-7. All existing keys in each payload (`ticket_id`, `initial_failures`, `attempted_fix_summary` for regression, `instrumentation_targets` / `instrumentation_attempt_summary` / `retest_status` for diagnostic-logging) are PRESERVED unchanged — this is an ADDITIVE payload extension. The `agent_log` messages that currently follow each structured event (`"user input required. Options: continue / abandon."`) MUST be replaced with `"error report written to project store; branch flagged with [ERROR] commit."` (regression) and `"error report written to project store; branch flagged with [ERROR] commit."` (diagnostic-logging) — same wording, different upstream callers. Both messages are asserted verbatim by tests.

10. **And** `SupervisorAgent.run_tickets` MUST continue iterating to the next `ticket_id` after any `_execute_ticket` return dict whose `status` is `"error"` or `"blocked"` — the failed ticket does not halt the queue. This is the CURRENT behavior of `run_tickets` (a plain `for` loop appending each `_execute_ticket` result to a `results` list) and MUST be preserved verbatim — Story 5.9 does NOT modify `run_tickets`. A test asserts this by driving two tickets through `run_tickets` where the first hits an escalation and the second executes normally.

11. **And** the `_execute_ticket` return dict on the escalation paths MUST now include `"error_report": <error_report_payload>` at the top level (alongside the existing `ticket_id`, `status`, `reason`, `initial_failures`, and — on the regression path — `retest_failures`, and — on the diagnostic-logging path — `instrumentation_targets`). `status` remains `"blocked"` for backward compatibility with Stories 5.7 and 5.8 test assertions (any test asserting `status == "blocked"` continues to pass), and `reason` remains `"regression_unfixed"` or `"diagnostic_logging_unresolved"`. The change from Story 5.7/5.8 is (a) the ticket state transition is now `"Error"` (was `"Agent Blocked"`), (b) the `options` list in the SSE event is now `["view_report"]` (was `["continue", "abandon"]`), and (c) the new `error_report` key is added to both the SSE payload and the returned dict.

## Tasks / Subtasks

- [x] 1. Add `project_store.write_error_report` (AC: 3, 8)
  - [x] 1.1 In `backend/store/project_store.py`, add a new async helper directly BELOW `write_test_artifact` and ABOVE `mark_ticket_done` (keeps ticket-mutation helpers grouped):
    ```python
    async def write_error_report(
        project_id: str, ticket_id: str, error_report: dict
    ) -> None:
        """FR-20: persist a structured error report on a ticket.

        Called by SupervisorAgent when a ticket transitions to Error after
        exhausting autonomous remediation. Overwrites any prior report on
        the same ticket — the latest attempt is authoritative.
        """
        if not isinstance(error_report, dict):
            raise ValueError("error_report must be a dict")
        required_keys = {
            "ticket_id", "failure_kind", "description",
            "initial_failures", "attempted_fixes",
            "log_references", "branch",
        }
        missing = required_keys - error_report.keys()
        if missing:
            raise ValueError(f"error_report missing keys: {sorted(missing)}")
        pool = database.get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE projects
                SET ticket_history = (
                    SELECT jsonb_agg(
                        CASE WHEN t->>'id' = $2
                        THEN t || $3::jsonb
                        ELSE t
                        END
                    )
                    FROM jsonb_array_elements(ticket_history) AS t
                )
                WHERE id = $1
                """,
                project_id,
                ticket_id,
                json.dumps({"error_report": error_report}),
            )
    ```
  - [x] 1.2 Do NOT add a database migration. `ticket_history` is JSONB — new keys inside a ticket dict are additive, no schema change. `backend/store/migrations.py` is untouched.
  - [x] 1.3 The required-key validation covers only the seven core keys from AC-2. The optional `flagged_commit` (AC-5) and `jira_transition` (AC-8) keys are added by the supervisor after the payload is built and BEFORE `write_error_report` is called; they pass through the JSONB serialisation without validation. If either is missing, the persisted report simply lacks that field — no error. Consumers must treat both as optional.

- [x] 2. Refactor supervisor escalation paths to unified error-report flow (AC: 1, 4, 5, 7, 9, 11)
  - [x] 2.1 In `agents/supervisor_agent.py`, add a new private method `_write_error_report_and_flag_branch` positioned IMMEDIATELY BELOW `_escalate_diagnostic_logging` and ABOVE `_handle_regression_and_maybe_fix` (keeps the shared helper adjacent to both callers — both `_escalate_regression` and `_escalate_diagnostic_logging` will call it). Signature:
    ```python
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

        Returns the fully-populated `error_report_payload` (including
        `flagged_commit` and `jira_transition` sub-dicts) for the caller to
        embed in the escalation SSE event and the `_execute_ticket` return.
        """
    ```
  - [x] 2.2 Build the payload:
    ```python
    branch_name = dev_result.get("branch") or f"feature/{ticket_id}"
    seen = set()
    filtered_refs = []
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
    ```
  - [x] 2.3 Persist the report:
    ```python
    await project_store.write_error_report(project_id, ticket_id, payload)
    ```
    Do NOT wrap this in try/except — a persistence failure is a hard system error and MUST propagate (same reasoning as Story 5.6's AD-6 gate; the caller of the supervisor is the execute endpoint which will surface the exception).
  - [x] 2.4 Build the flag-commit description (AC-4). Use `\n` for all newlines. The instruction sentence is a single-line string; use Python line continuations to keep source readable. Reference implementation:
    ```python
    failure_lines = "\n".join(
        f"- {f.get('test', '?')}: {f.get('message', '')}" for f in payload["initial_failures"]
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
    ```
  - [x] 2.5 Delegate to the developer (AC-4/5):
    ```python
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
    ```
  - [x] 2.6 Best-effort Jira transition (AC-8):
    ```python
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
                    "message": f"[Supervisor] Jira ticket {ticket_id} transitioned to Error.",
                })
        payload["jira_transition"] = {"attempted": True, "success": jira_ok}
    else:
        payload["jira_transition"] = {"attempted": False, "success": False}

    return payload
    ```
  - [x] 2.7 Refactor `_escalate_regression` to call the new helper. Current signature stays unchanged (backward-compat for internal callers within `_handle_regression_and_maybe_fix`). Inside the method, BEFORE the current `publish_event(..., "regression_escalation", ...)` call:
    ```python
    # Collect log references from initial + retest (both may have written artifacts).
    log_references = [
        initial_test_result.get("test_artifact_ref", ""),
        retest_result.get("test_artifact_ref", ""),
    ]
    prior_attempts = dev_result.get("_prior_attempts", []) if isinstance(dev_result, dict) else []
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
    ```
    Note: the method currently does NOT receive `story_details`, `dev_result`, or `workspace_path` — it needs them for the helper call. UPDATE the signature of `_escalate_regression` to add these three parameters (positional, after `retest_result`), and UPDATE the two call sites in `_handle_regression_and_maybe_fix` (there are two — the early developer-error escalation and the terminal retest-failure escalation) to pass them:
    ```python
    return await self._escalate_regression(
        project_id, ticket_id, initial_test_result,
        attempted_fix_summary=..., retest_result=...,
        story_details=story_details,
        dev_result=dev_result,
        workspace_path=workspace_path,
    )
    ```
    Do NOT change `_escalate_regression`'s docstring beyond adding a one-line note about writing the error report.
  - [x] 2.8 In `_escalate_regression`, REPLACE the existing payload construction:
    ```python
    payload = {
        "ticket_id": ticket_id,
        "initial_failures": initial_failures,
        "attempted_fix_summary": attempted_fix_summary,
        "retest_failures": retest_failures,
        "error_report": error_report_payload,
        "options": ["view_report"],
    }
    ```
    REPLACE the `agent_log` "user input required" line with:
    ```python
    await publish_event(project_id, "agent_log", {
        "message": (
            f"[Supervisor] Autonomous fix failed for ticket {ticket_id} — "
            "error report written to project store; branch flagged with [ERROR] commit."
        ),
    })
    ```
    REPLACE `update_ticket_status(..., "Agent Blocked")` with `update_ticket_status(..., "Error")`.
    EXTEND the returned dict to include `"error_report": error_report_payload`:
    ```python
    return {
        "ticket_id": ticket_id,
        "status": "blocked",
        "reason": "regression_unfixed",
        "initial_failures": initial_failures,
        "retest_failures": retest_failures,
        "error_report": error_report_payload,
    }
    ```
    Keep `status == "blocked"` and `reason == "regression_unfixed"` for backward compat (existing Story 5.7 tests assert on these values).
  - [x] 2.9 Refactor `_escalate_diagnostic_logging` symmetrically. UPDATE its signature to add `story_details`, `dev_result`, `workspace_path` after `retest_status` (positional). UPDATE the three call sites in `_handle_insufficient_logs_and_instrument` (early developer-error escalation, retest-error/insufficient escalation — the return-in-Task-2.9 line — total 2 real sites; audit the file to confirm) to pass the new arguments.
    Inside `_escalate_diagnostic_logging`, BEFORE `publish_event(..., "diagnostic_logging_escalation", ...)`:
    ```python
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
    ```
    REPLACE the existing payload construction to add `"error_report": error_report_payload` and set `"options": ["view_report"]` (keep all existing keys otherwise). REPLACE the "user input required" `agent_log` line with:
    ```python
    await publish_event(project_id, "agent_log", {
        "message": (
            f"[Supervisor] Diagnostic logging did not restore log coverage for ticket "
            f"{ticket_id} — error report written to project store; branch flagged with "
            f"[ERROR] commit."
        ),
    })
    ```
    REPLACE `update_ticket_status(..., "Agent Blocked")` with `update_ticket_status(..., "Error")`. EXTEND the returned dict to include `"error_report": error_report_payload`.
  - [x] 2.10 Insufficient-logs → regression fall-through (AC-6): in `_handle_insufficient_logs_and_instrument`, in the `retest_status == "regression"` branch (Task 2.9 of Story 5.8), BEFORE calling `_handle_regression_and_maybe_fix`, stash the diagnostic-instrumentation attempt on `dev_result`:
    ```python
    if retest_status == "regression":
        # Story 5.9 AC-6: forward diagnostic-instrumentation attempt into the
        # regression handler so its error report includes both attempts in order.
        prior = dev_result.get("_prior_attempts") or []
        dev_result = dict(dev_result)  # Story 5.3 leakage guard applies here too.
        dev_result["_prior_attempts"] = prior + [{
            "kind": "diagnostic_instrumentation",
            "summary": fix_result.get("message") or fix_result.get("pr_url") or "instrumentation committed",
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
    ```
    NOTE: shallow-copying `dev_result` here is a NEW step (Story 5.8 mutated it in place — the caller of `_execute_ticket` did not care). Story 5.9 requires the copy because `_write_error_report_and_flag_branch` will read `_prior_attempts` off whichever `dev_result` is threaded through, and we do NOT want the `_prior_attempts` key to leak back into the outer `_execute_ticket` scope where it could pollute future logic.
  - [x] 2.11 Do NOT modify `close_ticket_as_done`, `_handle_regression_and_maybe_fix`'s success path, `_delegate_to_developer`, `_build_accumulated_context`, or the environment-failed / developer-failed / final-fallback branches of `_execute_ticket`. Do NOT introduce new SSE event types (AC-7 explicit — reuse existing ones).

- [x] 3. `main_agent.py` — no changes (AC: 10, out of scope)
  - [x] 3.1 Confirm by inspection that `agents/main_agent.py` still uses its own inline CLI flow and does NOT call `SupervisorAgent._execute_ticket`. No changes required. Document in Dev Notes — same rationale as Stories 5.7 Task 3.1 and 5.8 Task 3.1.

- [x] 4. Tests (AC: 1–11)
  - [x] 4.1 Add `tests/test_project_store_error_report.py`. Follow the fixture patterns in `tests/test_project_store_test_artifact.py` (mock `database.get_pool` with an `AsyncMock` acquire context).
    - [x] 4.1.1 `test_write_error_report_persists_json_on_ticket`: build a well-formed payload with all seven required keys plus `flagged_commit` and `jira_transition`; call `await write_error_report("proj-1", "tkt-1", payload)`; assert the connection's `execute` was awaited with a SQL string containing `"ticket_history"` and `"jsonb_array_elements"`, and that the third parameter is a JSON-encoded string decoding to `{"error_report": <payload>}`.
    - [x] 4.1.2 `test_write_error_report_rejects_non_dict`: `await write_error_report("proj-1", "tkt-1", "not a dict")` MUST raise `ValueError` matching `"error_report must be a dict"`. Assert `database.get_pool` was NOT called (validation runs before pool acquisition).
    - [x] 4.1.3 `test_write_error_report_rejects_missing_keys`: pass a dict missing `attempted_fixes`; assert `ValueError` with message containing `"attempted_fixes"`. Assert pool not called.
    - [x] 4.1.4 `test_write_error_report_allows_extra_keys`: payload with all seven required keys plus a made-up `"foo": "bar"` key MUST persist without error — validation is `required_keys - error_report.keys()`, not the other way around.
  - [x] 4.2 Add `tests/test_supervisor_error_report.py`. Follow the fixture patterns in `tests/test_supervisor_regression_fix.py` and `tests/test_supervisor_diagnostic_logging.py`.
    - [x] 4.2.1 `test_regression_escalation_writes_error_report_and_pushes_flagged_commit`:
      - Patch `tester.write_and_run_tests` with an `AsyncMock` whose `side_effect` returns `[regression_result, regression_result]` (initial + retest — same failing outcome so the Story 5.7 fix "succeeded" but retest still fails).
      - Patch `remote_developer.implement_feature` → `{"status": "success", "branch": "feature/tkt-1", "code_files": ["src/a.py"], "message": "ok"}`.
      - Patch `remote_developer.implement_pr_recommendations` with an `AsyncMock` whose `side_effect` is `[fix_success, push_success]` where `push_success = {"status": "success", "message": "flagged commit pushed"}` and `fix_success = {"status": "success", "branch": "feature/tkt-1", "message": "fix committed"}`.
      - Patch `environment.prepare_environment` → `{"status": "success", "workspace_path": "/tmp/ws", "repo_full_name": "o/r"}`.
      - Patch `backend.store.project_store.get_project` → `{"ticket_history": [{"id": "tkt-1", "title": "T", "description": "D", "status": "In Progress"}]}`.
      - Patch `backend.store.project_store.write_error_report`, `backend.store.project_store.update_ticket_status`, `backend.store.project_store.mark_ticket_done` with `AsyncMock`.
      - Patch `backend.api.sse.publish_event` with `AsyncMock`.
      - Ensure `os.environ.get("TICKET_SYSTEM", "")` returns `""` (monkeypatch `TICKET_SYSTEM=""` or delete it) so the Jira branch is skipped.
      - Call `await supervisor._execute_ticket("proj-1", "tkt-1", ["tkt-1"])`.
      - Assert `write_error_report` was awaited exactly once with `("proj-1", "tkt-1", <payload>)` where:
        - `payload["failure_kind"] == "regression_unfixed"`
        - `payload["description"] == "Autonomous fix could not resolve regression"`
        - `payload["attempted_fixes"]` is a one-element list with `[0]["kind"] == "autonomous_fix"`
        - `payload["branch"] == "feature/tkt-1"`
        - `payload["flagged_commit"] == {"pushed": True, "branch": "feature/tkt-1"}`
        - `payload["jira_transition"] == {"attempted": False, "success": False}`
      - Assert `implement_pr_recommendations` was awaited exactly TWICE — the second call's `story_details["description"]` MUST contain the literal `"--- Error report ---"`, `"[ERROR] tkt-1: "`, and `"Autonomous fix could not resolve regression"`.
      - Assert `update_ticket_status` was awaited with `("proj-1", "tkt-1", "Error")` — NOT `"Agent Blocked"`.
      - Assert `publish_event` was awaited with `("proj-1", "regression_escalation", <payload>)` where the payload has `options == ["view_report"]` and contains an `error_report` sub-dict.
      - Assert `publish_event` was awaited with an `agent_log` message containing `"error report written to project store; branch flagged with [ERROR] commit."`.
      - Assert `mark_ticket_done` was NOT called.
      - Assert the return dict has `status == "blocked"`, `reason == "regression_unfixed"`, and an `error_report` key matching the payload.
    - [x] 4.2.2 `test_diagnostic_logging_escalation_writes_error_report_and_pushes_flagged_commit`:
      - Same fixture skeleton, but tester `side_effect` is `[insufficient_logs_result, insufficient_logs_result]` (initial + retest — instrumentation "committed" but retest STILL insufficient).
      - `implement_pr_recommendations` side_effect: `[instrumentation_success, push_success]` where `instrumentation_success = {"status": "success", "branch": "feature/tkt-1", "message": "instrumented"}`.
      - Assert `write_error_report` was awaited once with `payload["failure_kind"] == "diagnostic_logging_unresolved"` and `payload["description"] == "Diagnostic logging did not restore log coverage"` and `payload["attempted_fixes"][0]["kind"] == "diagnostic_instrumentation"`.
      - Assert the second `implement_pr_recommendations` call (the flag-commit push) received a `story_details["description"]` containing `"[ERROR] tkt-1: "` and `"Diagnostic logging did not restore log coverage"`.
      - Assert `update_ticket_status` was awaited with `("proj-1", "tkt-1", "Error")`.
      - Assert `publish_event` was awaited with `("proj-1", "diagnostic_logging_escalation", <payload>)` where `options == ["view_report"]`.
      - Assert NO `regression_escalation` event was published.
    - [x] 4.2.3 `test_flagged_commit_push_failure_still_persists_report_and_transitions_ticket`:
      - Same regression setup as 4.2.1 but the SECOND `implement_pr_recommendations` call (the flag-commit push) returns `{"status": "error", "message": "git push rejected", "reason": "push failed"}`.
      - Assert `write_error_report` STILL awaited once (report persisted before push attempt).
      - Assert `update_ticket_status` STILL awaited with `("proj-1", "tkt-1", "Error")`.
      - Assert the persisted payload's `flagged_commit == {"pushed": False, "reason": "git push rejected"}`.
      - Assert `publish_event` was awaited with an `agent_log` message containing `"Failed to push flagged error commit for ticket tkt-1"`.
      - Assert the return dict has `status == "blocked"`, `reason == "regression_unfixed"`.
    - [x] 4.2.4 `test_insufficient_logs_then_regression_fall_through_reports_both_attempts_in_order`:
      - Tester `side_effect`: `[insufficient_logs_result, regression_result, regression_result]` (initial insufficient_logs → retest after instrumentation returns regression → retest after regression fix still regression).
      - `implement_pr_recommendations` side_effect (four calls): `[instrumentation_success, fix_success, push_success]` — actually only three calls (instrumentation, autonomous fix, error-flag push) since the fix's retest fails without a re-attempt.
      - Assert `write_error_report` was awaited once with `payload["attempted_fixes"]` a TWO-ELEMENT list: `[0]["kind"] == "diagnostic_instrumentation"`, `[1]["kind"] == "autonomous_fix"`. Order matters — the diagnostic attempt comes first.
      - Assert `payload["failure_kind"] == "regression_unfixed"` (the final failure was the regression path, not the diagnostic path).
      - Assert `update_ticket_status` was awaited with `("proj-1", "tkt-1", "Error")` — NOT `"Agent Blocked"`.
      - Assert the return dict has `status == "blocked"`, `reason == "regression_unfixed"`, AND `diagnostic_logging == {"attempted": True, "outcome": "regression_after_instrumentation", ...}` (Story 5.8 key still coexists per Story 5.8 AC-6), AND an `error_report` key.
    - [x] 4.2.5 `test_error_report_flag_prompt_is_shallow_copied`:
      - Patch `implement_feature` to capture its `story_details` arg to a closure list. After `_execute_ticket` returns, assert the captured dict's `description` does NOT contain `"--- Error report ---"`.
      - Same for the initial call of `implement_pr_recommendations` (the Story 5.7 fix) — its captured description contains `"--- Regression report ---"` (Story 5.7 wording) but NOT `"--- Error report ---"`.
      - The `"--- Error report ---"` block appears ONLY in the FINAL `implement_pr_recommendations` call (the flag-commit push).
    - [x] 4.2.6 `test_jira_transition_attempted_when_ticket_system_is_jira`:
      - Same regression setup as 4.2.1.
      - Monkeypatch `TICKET_SYSTEM=jira`.
      - Patch `tools.ticket_manager.TicketManager` (using `unittest.mock.patch("tools.ticket_manager.TicketManager")`) — configure the class to return an instance whose `transition_ticket` is an `AsyncMock(return_value=True)`.
      - Assert `TicketManager()` was constructed exactly once.
      - Assert `transition_ticket` was awaited once with `("tkt-1", "Error")`.
      - Assert the persisted payload has `jira_transition == {"attempted": True, "success": True}`.
      - Assert `publish_event` was awaited with an `agent_log` message equal to `"[Supervisor] Jira ticket tkt-1 transitioned to Error."`.
    - [x] 4.2.7 `test_jira_transition_failure_does_not_block_error_transition`:
      - Monkeypatch `TICKET_SYSTEM=jira`.
      - Patch `TicketManager.transition_ticket` to raise `RuntimeError("mcp unavailable")`.
      - Assert `update_ticket_status(..., "Error")` was STILL awaited.
      - Assert `write_error_report` was STILL awaited.
      - Assert the persisted payload has `jira_transition == {"attempted": True, "success": False}`.
      - Assert `publish_event` was awaited with an `agent_log` message containing `"Jira transition to Error failed for ticket tkt-1: mcp unavailable"`.
    - [x] 4.2.8 `test_ticket_system_not_jira_skips_manager_import`:
      - Monkeypatch `TICKET_SYSTEM=github` (or delete the env var).
      - Patch `tools.ticket_manager.TicketManager` and assert its class-object was NEVER accessed (use `unittest.mock.patch("tools.ticket_manager.TicketManager")` and assert `assert_not_called()` on the class mock).
      - Assert the persisted payload has `jira_transition == {"attempted": False, "success": False}`.
    - [x] 4.2.9 `test_queue_continues_after_error_ticket`:
      - Set up two tickets in `ticket_history`: `tkt-1` (regression-escalation path) and `tkt-2` (first-pass success path).
      - Tester `side_effect`: `[regression_result, regression_result, success_result]` — first two calls resolve the failure path for `tkt-1`, third call is `tkt-2`'s clean run.
      - `implement_pr_recommendations` side_effect: `[fix_success, push_success]`.
      - `implement_feature` returns `{"status": "success", ...}` on both invocations.
      - Call `await supervisor.run_tickets("proj-1", ["tkt-1", "tkt-2"])`.
      - Assert the returned dict has `results` list of length 2. `results[0]["status"] == "blocked"`; `results[1]["status"] == "completed"`.
      - Assert `write_error_report` was awaited exactly once (only for `tkt-1`).
      - Assert `update_ticket_status` was awaited with `("proj-1", "tkt-1", "Error")` AND with `("proj-1", "tkt-2", "In Review")`.
      - This is the FR-20 queue-continuation invariant (AC-10).
  - [x] 4.3 Regression run: `python -m pytest tests/ -q` MUST show all previously-passing tests still passing. Existing Story 5.7 and 5.8 tests that assert `status == "blocked"`/`reason == "regression_unfixed"` / `reason == "diagnostic_logging_unresolved"` MUST continue to pass — those return-dict shapes are preserved (Story 5.9 only ADDS the `error_report` key). Tests that assert on the OLD `options == ["continue", "abandon"]` MUST be updated to expect `options == ["view_report"]`; tests that assert on the OLD `update_ticket_status(..., "Agent Blocked")` MUST be updated to expect `("Error")`. Grep first — see Task 4.4 for the audit list.
  - [x] 4.4 Test audit: BEFORE running the full suite, grep the tests directory for these three literals and update every hit:
    ```bash
    grep -rn "Agent Blocked" tests/
    grep -rn 'continue.*abandon' tests/
    grep -rn 'user input required' tests/
    ```
    Expected hits from Story 5.7 (`tests/test_supervisor_regression_fix.py`) and Story 5.8 (`tests/test_supervisor_diagnostic_logging.py`). Each hit becomes a test surface for Story 5.9's behavior change — update the assertion, do NOT delete the test. The test-count in the sprint suite may INCREASE (new tests) but the number of previously-passing tests MUST NOT DECREASE.

- [x] 5. Documentation & schema notes (AC: n/a)
  - [x] 5.1 Do NOT create a new markdown doc for this story unless the user asks — per repo convention.
  - [x] 5.2 Do NOT modify `backend/store/migrations.py`. `error_report` lives inside the `ticket_history` JSONB dict — schemaless. `"Error"` is already declared in the state machine.
  - [x] 5.3 Do NOT touch `.env.example`. `TICKET_SYSTEM` is already documented there (from Story 5.7 baseline).
  - [x] 5.4 Do NOT alter `backend/api/sse.py`. The two existing event types (`regression_escalation`, `diagnostic_logging_escalation`) already carry the new payload shape — data-only additive change (`publish_event` accepts arbitrary dicts, verified in Stories 5.7 and 5.8).
  - [x] 5.5 Do NOT modify `agents/developer_agent.py` or `agents/local_developer_agent.py`. The `[ERROR]` commit message and `ERROR_REPORT.md` file write are instructed via the `flag_story["description"]` prompt; both existing `implement_pr_recommendations` implementations already forward `description` verbatim to the LLM prompt.
  - [x] 5.6 Do NOT modify `tools/ticket_manager.py`. `TicketManager.transition_ticket(ticket_id, to_status)` already accepts arbitrary status strings and best-effort-transitions via the Jira MCP.

## Dev Notes

### What Stories 5.1–5.8 Built (Must Not Break)

- **Story 5.1** — Sequential execution lock. Unchanged. The error-report flow runs INSIDE `_execute_ticket`, already lock-scoped. `run_tickets` releases the lock between tickets (per-ticket scope in Story 5.1).
- **Story 5.2** — `_execute_ticket` "In Review" transition on first-pass success. Preserved unchanged. Story 5.9 only refactors the two escalation terminals.
- **Story 5.3** — Accumulated-context leakage guard (`_build_accumulated_context` reads `ticket_history[].description`). Story 5.9 uses shallow-copy `dict(story_details)` for the flag-commit prompt (Task 2.4) and shallow-copies `dev_result` before adding `_prior_attempts` (Task 2.10). Same rationale as Stories 5.7 and 5.8. `_prior_attempts` is NEVER persisted — it lives only inside the in-memory `dev_result` for the duration of one ticket.
- **Story 5.4** — chat/agent_memory JSONB round-tripping. Untouched.
- **Story 5.5** — Context7 grounding at the top of `implement_pr_recommendations`. The flag-commit push (AC-4) STILL runs grounding; if grounding fails at that stage, the push fails and AC-5 handles it (`flagged_commit.pushed = False`). No change to AD-8.
- **Story 5.6** — `close_ticket_as_done` / AD-6 gate. UNCHANGED and NOT invoked on the error-report path — the ticket goes to `Error`, not `Done`. The AD-6 gate remains authoritative for the `Done` transition only.
- **Story 5.7** — Regression handler. Story 5.9 CHANGES the terminal transition from `Agent Blocked` to `Error`, adds an `error_report` key to the SSE payload and return dict, replaces the `options` list content, and reroutes `_escalate_regression` through the shared `_write_error_report_and_flag_branch` helper. The one-shot fix-attempt invariant is preserved. The escalation SSE event TYPE (`regression_escalation`) is unchanged (data-only additive extension).
- **Story 5.8** — Diagnostic-logging handler. Same shape of changes as Story 5.7: transition to `Error`, `options == ["view_report"]`, new `error_report` key, shared helper for the flag-commit. The fall-through-to-regression path (Story 5.8 AC-6) now forwards `_prior_attempts` so the regression handler's error report includes BOTH the instrumentation attempt and the autonomous fix attempt, in order (AC-6).

### Architecture Compliance

- **AD-1 (agent hierarchy):** The flag-commit push and the Jira transition BOTH flow through the Supervisor. Sub-agents remain unaware of each other. `_write_error_report_and_flag_branch` dispatches to `self.local_developer` / `self.remote_developer` via the same routing pattern as Stories 5.7/5.8. `TicketManager` is a Supervisor-owned utility (constructed lazily inside the helper), not a peer of the developer/tester agents.
- **AD-2 (sequential lock):** The entire error-report flow (report write, flag-commit push, Jira transition, escalation SSE) runs inside a single `_execute_ticket` invocation under the existing lock. No parallel work introduced. Queue continuation happens BETWEEN tickets, after the lock releases — matching Story 5.1's per-ticket scope.
- **AD-3 (MCPManager singleton):** `TicketManager` uses the MCP singleton via its existing `manager.jira_tools` accessor. The lazy import in Task 2.6 does NOT open a new MCP connection — construction is cheap; the connection is only established the first time `manager.jira_tools` is dereferenced (Story 5.7 baseline behavior).
- **AD-4 (LLM-as-last-resort):** The error-report BUILD (Task 2.4's `flag_block`) is pure string interpolation — NO LLM. The flag-commit PUSH invokes the developer LLM once (to write `ERROR_REPORT.md` and craft the commit). The Jira transition invokes `TicketManager._run_agent` which uses an LLM — this is Story 5.7 baseline behavior for Jira transitions and is NOT introduced by this story. The error-report SSE emission is pure dict construction.
- **AD-5 (project isolation):** All operations scoped by `project_id`. `write_error_report` targets a single ticket in a single project's `ticket_history`.
- **AD-6 (test artifact gate):** The error-report path does NOT invoke `close_ticket_as_done` — the ticket goes to `Error`, and the AD-6 gate is bypassed intentionally (a failed ticket has no `Done` state to gate). This is consistent with Story 5.7's escalation and Story 5.8's escalation baselines.
- **AD-7 (streaming over polling):** Every state transition emits an SSE event as it happens. The extended `regression_escalation` / `diagnostic_logging_escalation` payloads carry the report inline — the frontend does NOT need to re-fetch. Additional `agent_log` events narrate the flag-commit push and the Jira transition.
- **AD-8 (Context7 grounding):** Grounding runs INSIDE `implement_pr_recommendations` for the flag-commit push. If grounding fails, `implement_pr_recommendations` returns `status="error"` and AC-5 handles it as a push failure (report still persisted).
- **AD-9 (async throughout):** All new methods (`_write_error_report_and_flag_branch`, `write_error_report`) are `async def`. All calls use `await`. The `TicketManager` construction is synchronous (baseline behavior) but `manager.transition_ticket` is awaited.
- **AD-13 (env vars only):** `TICKET_SYSTEM` is read via `os.environ.get(...)` at method-invocation time in Task 2.6 — never at import time. Same rationale as Stories 5.7 and 5.8. No hardcoded fallbacks.
- **Ticket state machine (spine §"Ticket state machine"):** `Pending → In Progress → Done | Error | Agent Blocked`. Story 5.9 activates the `Error` terminal for the unresolvable-failure path. `Agent Blocked` remains a valid state; it is currently NO LONGER WRITTEN by the supervisor after this story (a future story may reintroduce it for the human-in-the-loop "continue / abandon" gate).
- **FR-20 preservation invariant:** Queue continuation (AC-10) is guaranteed structurally by the existing `for ticket_id in ticket_ids:` loop in `run_tickets` — `_execute_ticket` returns dicts, never raises for tester/developer/environment failures. The error-report flow adds two new potential failure points: (a) `write_error_report` propagates hard on ValueError/DB failure (deliberate — a hard system error MUST NOT be silently swallowed), (b) the flag-commit push failure is caught and logged (AC-5). Neither prevents the queue from advancing to the next ticket in the NORMAL case; a `write_error_report` propagation would halt the queue, but that only happens on genuine infrastructure failure (DB down, pool exhausted) — which is the correct behavior.
- **project-context.md — Jira MCP rules:** Task 2.6 uses `TicketManager` (baseline), which already respects the `fields=summary,description,status` payload-size rule for Jira MCP calls. No new Jira MCP endpoints introduced.

### Files Being Modified — Current State and Change Scope

**`backend/store/project_store.py`** (current state: ~240 lines, async, JSONB-backed CRUD)
- Current: `write_test_artifact` sits between `overwrite_ticket_history` and `mark_ticket_done`, updating the ticket JSONB with a `test_artifact_ref` key. `update_ticket_fields` is a general-purpose JSONB merge helper.
- Change: add `write_error_report` immediately below `write_test_artifact` and above `mark_ticket_done` — mirrors `write_test_artifact` in shape and validation.
- Must preserve: `write_test_artifact`, `mark_ticket_done`, and `update_ticket_status` exactly. `update_ticket_fields` is NOT used by this story (dedicated helper offers structural validation which the generic helper cannot).

**`agents/supervisor_agent.py`** (current state: ~715 lines with Stories 5.1–5.8; `_execute_ticket` four-way branch, two escalation helpers)
- Current: `_execute_ticket` → `_handle_regression_and_maybe_fix` → `_escalate_regression` (sets `Agent Blocked`, publishes `regression_escalation` with `options == ["continue", "abandon"]`). `_execute_ticket` → `_handle_insufficient_logs_and_instrument` → `_escalate_diagnostic_logging` (sets `Agent Blocked`, publishes `diagnostic_logging_escalation` with same `options`). Both fall-through to `_handle_regression_and_maybe_fix` on the diagnostic → regression path.
- Change: add `_write_error_report_and_flag_branch` positioned immediately below `_escalate_diagnostic_logging` and above `_handle_regression_and_maybe_fix`. Refactor BOTH escalation helpers to call it. Extend both escalation SSE payloads with `error_report` (AC-9). Change both state transitions from `Agent Blocked` to `Error` (AC-7). Replace `options` in both payloads with `["view_report"]` (AC-9). Add `_prior_attempts` forwarding in the diagnostic → regression fall-through (AC-6).
- Must preserve: `_execute_ticket`'s four-way branch and every non-escalation return dict shape. `close_ticket_as_done`. `_delegate_to_developer`. `_build_accumulated_context`. `_handle_regression_and_maybe_fix`'s success path (autonomous-fix-succeeded → `close_ticket_as_done` → return `completed`). `_handle_insufficient_logs_and_instrument`'s success path (retest → `In Review` → return `completed`). The environment-failed / developer-failed / final-fallback branches. The `TesterAgent` contract (no tester changes).

**`agents/main_agent.py`** — NOT modified. CLI path bypasses `SupervisorAgent._execute_ticket`.

**`agents/developer_agent.py` / `agents/local_developer_agent.py`** — NOT modified. `implement_pr_recommendations` reads `story_details["description"]` verbatim; the flag-commit instruction rides in on that field.

**`agents/tester_agent.py`** — NOT modified. No new tester signals introduced by Story 5.9 — the escalation is triggered by existing signals (Story 5.7's regression retest failure, Story 5.8's insufficient-logs retest failure).

**`tools/ticket_manager.py`** — NOT modified. `transition_ticket(ticket_id, "Error")` already handles arbitrary Jira status strings via the LLM-driven MCP flow.

**`backend/api/sse.py`** — NOT modified. `publish_event` accepts arbitrary event types and payload dicts; the extension is data-only.

**NEW files:**
- `tests/test_project_store_error_report.py`
- `tests/test_supervisor_error_report.py`

**MODIFIED test files:**
- `tests/test_supervisor_regression_fix.py` — update assertions per Task 4.4 audit (grep hits): `Agent Blocked` → `Error`, `["continue", "abandon"]` → `["view_report"]`, `"user input required"` → `"error report written to project store; branch flagged with [ERROR] commit."`.
- `tests/test_supervisor_diagnostic_logging.py` — same three-way find/replace.

**DO NOT modify:**
- `backend/store/errors.py`, `backend/store/database.py`, `backend/store/migrations.py`, `backend/store/spec_store.py`, `backend/store/file_ops.py`
- `backend/api/routes/execute.py`, `backend/api/sse.py`
- `backend/execution_lock.py`
- `agents/environment_agent.py`, `agents/context7_grounding.py`, `agents/tester_agent.py`
- Existing Story 5.5 grounding tests, Story 5.6 artifact-gate tests, Story 5.7 regression fix path except assertions per Task 4.4, Story 5.8 diagnostic logging path except assertions per Task 4.4

### Windows / Path Notes

- No new path operations introduced. The `ERROR_REPORT.md` file write happens INSIDE the developer LLM's tool loop (via `local_write_file` or the GitHub MCP `create_or_update_file`), which already handles path normalisation at the tool level (baseline behavior).
- The `[ERROR]` commit message contains a bracketed literal — no shell-escaping concerns because the commit is authored via the git library (`GitPython` in local mode, GitHub MCP in remote mode). Both handle arbitrary UTF-8 in commit messages without escaping.

### Reference Implementation Sketch (non-normative)

Shared error-report helper (skeleton):
```python
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
    branch_name = dev_result.get("branch") or f"feature/{ticket_id}"
    # ...build payload (Task 2.2)...
    await project_store.write_error_report(project_id, ticket_id, payload)
    # ...build flag_block prompt (Task 2.4)...
    flag_story = dict(story_details)
    flag_story["description"] = flag_block
    push_result = await (
        self.local_developer if self.mode == "local" else self.remote_developer
    ).implement_pr_recommendations(flag_story, branch_name, workspace_path)
    if push_result.get("status") == "success":
        payload["flagged_commit"] = {"pushed": True, "branch": branch_name}
    else:
        await publish_event(project_id, "agent_log", {"message": "..."})
        payload["flagged_commit"] = {"pushed": False, "reason": "..."}
    if os.environ.get("TICKET_SYSTEM", "").lower() == "jira":
        from tools.ticket_manager import TicketManager
        try:
            manager = TicketManager()
            jira_ok = bool(await manager.transition_ticket(ticket_id, "Error"))
        except Exception as exc:  # noqa: BLE001
            await publish_event(project_id, "agent_log", {"message": "..."})
            jira_ok = False
        payload["jira_transition"] = {"attempted": True, "success": jira_ok}
    else:
        payload["jira_transition"] = {"attempted": False, "success": False}
    return payload
```

Regression escalation refactor (skeleton):
```python
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
    initial_failures = initial_test_result.get("failures") or []
    retest_failures = retest_result.get("failures") or []
    log_references = [
        initial_test_result.get("test_artifact_ref", ""),
        retest_result.get("test_artifact_ref", ""),
    ]
    prior_attempts = dev_result.get("_prior_attempts", []) if isinstance(dev_result, dict) else []
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
    await publish_event(project_id, "agent_log", {
        "message": (
            f"[Supervisor] Autonomous fix failed for ticket {ticket_id} — "
            "error report written to project store; branch flagged with [ERROR] commit."
        ),
    })
    await project_store.update_ticket_status(project_id, ticket_id, "Error")
    return {
        "ticket_id": ticket_id,
        "status": "blocked",
        "reason": "regression_unfixed",
        "initial_failures": initial_failures,
        "retest_failures": retest_failures,
        "error_report": error_report_payload,
    }
```

### Project Structure Notes

- Alignment with unified project structure: new supervisor helper lives in `agents/supervisor_agent.py` alongside the existing Story 5.7/5.8 handlers. New store helper lives in `backend/store/project_store.py` alongside `write_test_artifact`. Test files under `tests/` prefixed `test_`. New test file names mirror existing patterns (`test_project_store_error_report.py`, `test_supervisor_error_report.py`).
- Detected conflicts or variances: the state-transition CHANGE from `Agent Blocked` to `Error` on the escalation paths supersedes Stories 5.7 and 5.8 explicitly. This is a deliberate refinement — the human-in-the-loop `Agent Blocked` gate is a separate future story. Existing Story 5.7/5.8 test assertions on `Agent Blocked` MUST be updated (Task 4.4 audit).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.9: Error Report and Flagged Commit]
- [Source: _bmad-output/planning-artifacts/epics.md#FR-20: Error Report and Flagged Commit on Unresolvable Failure]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md#Ticket state machine] — `Pending → In Progress → Done | Error | Agent Blocked`.
- [Source: _bmad-output/implementation-artifacts/5-7-autonomous-pre-merge-regression-fix.md#Tasks / Subtasks] — precedent for the escalation-helper shape and shallow-copy `story_details` pattern.
- [Source: _bmad-output/implementation-artifacts/5-8-diagnostic-logging-before-escalation.md#Tasks / Subtasks] — precedent for the diagnostic-logging escalation path being refactored here.
- [Source: _bmad-output/implementation-artifacts/5-6-mandatory-test-artifact-gate.md] — precedent for JSONB validation on `write_test_artifact`; `write_error_report` mirrors it.
- [Source: _bmad-output/project-context.md#Environment & Configuration Rules] — `TICKET_SYSTEM` env var contract; `jira` triggers the Jira MCP path.
- [Source: _bmad-output/project-context.md#Critical Don't-Miss Rules] — `Jira MCP requires 'fields' parameter`; respected by `TicketManager._run_agent` baseline.
- [Source: agents/supervisor_agent.py#_escalate_regression] — current escalation implementation being refactored (Story 5.7 baseline).
- [Source: agents/supervisor_agent.py#_escalate_diagnostic_logging] — current escalation implementation being refactored (Story 5.8 baseline).
- [Source: agents/supervisor_agent.py#run_tickets] — queue loop (per-ticket independent `_execute_ticket` calls) — AC-10 invariant is structural.
- [Source: agents/developer_agent.py#implement_pr_recommendations] — reused for the flag-commit push (remote mode).
- [Source: agents/local_developer_agent.py#implement_pr_recommendations] — reused for the flag-commit push (local mode); `local_git_commit_and_push` handles the actual push.
- [Source: tools/ticket_manager.py#transition_ticket] — reused verbatim for the best-effort Jira `Error` transition.
- [Source: backend/store/project_store.py#write_test_artifact] — shape template for `write_error_report`.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (GitHub Copilot)

### Debug Log References

- Full pytest suite: 118 passed, 6 pre-existing warnings (2.04s).
- Story-scoped subset (`test_project_store_error_report.py`, `test_supervisor_error_report.py`, `test_supervisor_regression_fix.py`, `test_supervisor_diagnostic_logging.py`): 26 passed (2.85s).

### Completion Notes List

- Added `project_store.write_error_report` with structural validation of the seven required keys (AC-2/3). Optional `flagged_commit` and `jira_transition` pass through untyped.
- Introduced shared supervisor helper `_write_error_report_and_flag_branch` placed between `_escalate_diagnostic_logging` and `_handle_regression_and_maybe_fix` (AC-1..5, 8).
- Refactored both `_escalate_regression` and `_escalate_diagnostic_logging` to route through the helper: state transition now `"Error"` (was `"Agent Blocked"`), `options == ["view_report"]`, escalation SSE payload extended with `error_report`, `_execute_ticket` return dict extended with `error_report` (AC-7/9/11).
- Wired the diagnostic-logging → regression fall-through to shallow-copy `dev_result` and stash `_prior_attempts` so the regression handler emits a two-entry `attempted_fixes` list in order (AC-6). `_prior_attempts` is transient (never persisted, never in SSE payload).
- Best-effort Jira transition uses a lazy `from tools.ticket_manager import TicketManager` inside the helper (avoids MCP spawn at import); wraps `manager.transition_ticket(ticket_id, "Error")` in broad `try/except` (AC-8).
- Flag-commit prompt built via pure string interpolation on a shallow copy of `story_details`, with description REPLACED (not appended). Description contains `--- Error report ---` block and the literal `[ERROR] <ticket_id>: <description>` commit-message instruction (AC-4). Description-replacement behaviour verified by `test_error_report_flag_prompt_is_shallow_copied`.
- Push failure is caught, logged via `agent_log`, and recorded on `payload["flagged_commit"]`; ticket transition to `Error` still occurs (AC-5).
- Existing Story 5.7 and 5.8 tests were updated per the Task 4.4 audit: `Agent Blocked` → `Error`, `["continue", "abandon"]` → `["view_report"]`, and `write_error_report` is patched on escalation-path tests. No tests were deleted.
- Test audit `grep -rn "Agent Blocked\|continue.*abandon\|user input required" tests/` now returns zero hits.
- FR-20 queue-continuation invariant covered by `test_queue_continues_after_error_ticket` — a `run_tickets` call over `[tkt-1, tkt-2]` where the first ticket escalates and the second completes cleanly.

### File List

**Modified**

- backend/store/project_store.py — added `write_error_report`.
- agents/supervisor_agent.py — added `_write_error_report_and_flag_branch`; refactored `_escalate_regression` and `_escalate_diagnostic_logging` signatures and bodies; updated three `_escalate_regression` call sites and two `_escalate_diagnostic_logging` call sites; added `_prior_attempts` stash in the diagnostic → regression fall-through with shallow-copy of `dev_result`.
- tests/test_supervisor_regression_fix.py — updated assertions for `Error`, `["view_report"]`, added `error_report` key in payload set, added `write_error_report` patch on escalation-path tests.
- tests/test_supervisor_diagnostic_logging.py — same three-way update as regression tests.
- _bmad-output/implementation-artifacts/sprint-status.yaml — 5-9 status transitions ready-for-dev → in-progress → review.

**New**

- tests/test_project_store_error_report.py — 4 tests covering validation and persistence.
- tests/test_supervisor_error_report.py — 9 tests covering regression + diagnostic-logging escalation paths, push failure, fall-through ordering, shallow-copy guard, Jira attempted/failure/skipped, and queue continuation.

## Change Log

| Date       | Change                                                                                          |
| ---------- | ----------------------------------------------------------------------------------------------- |
| 2026-09-01 | Story 5.9 drafted: error report persistence, [ERROR]-flagged commit push, Error state transition, best-effort Jira transition, queue continuation preserved. |
| 2026-09-01 | Story 5.9 implemented: `write_error_report`, `_write_error_report_and_flag_branch`, both escalation paths refactored to `Error` state with `["view_report"]` options and `error_report` payload key; diagnostic → regression fall-through forwards `_prior_attempts`; existing 5.7/5.8 tests updated; new tests added; full suite 118 passed. |
