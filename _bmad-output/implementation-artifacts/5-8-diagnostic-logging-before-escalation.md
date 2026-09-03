---
baseline_commit: b873c0bec72ac891aa89d1b0fcf39a979992fbc7
---

# Story 5.8: Diagnostic Logging Before Escalation

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want the agent team to add structured logging instrumentation to the code and re-run the test suite before attempting any fix or escalating to the user,
so that every error escalation includes complete log coverage of the failure path — no blind guesses (FR-19 / Epic 5 / project-context.md "Default Logging Scaffold" rules).

## Acceptance Criteria

1. **Given** `TesterAgent.write_and_run_tests` returns a result with `status == "insufficient_logs"` (a new, well-defined signal indicating the test run produced failure output that the agent cannot diagnose without additional log statements — distinct from `"regression"` which means the run failed with adequate log coverage, distinct from `"error"` which means the runner itself failed, and distinct from `"success"` which means all tests passed)
   **When** `SupervisorAgent._execute_ticket` receives that result
   **Then** the supervisor MUST publish an SSE `agent_log` event of the form `{"message": "[Supervisor] Insufficient log coverage for ticket <id> — adding diagnostic logging."}` on the project channel, MUST NOT publish any user-facing "notify me" event, MUST NOT transition the ticket to `Error` or `Agent Blocked` at this point, and MUST NOT invoke the Story 5.7 regression handler yet (per FR-19 the instrumentation step comes BEFORE any fix attempt).

2. **And** for every entry in `test_result["instrumentation_targets"]` (a list of file paths, guaranteed non-empty when the tester emits `status="insufficient_logs"`; see AC-8) the supervisor MUST publish an SSE `agent_log` event of the exact form `{"message": "Adding diagnostic logging to <file>…"}` (the ellipsis is a literal `…` U+2026 character to match the epic wording verbatim), preserving list order and publishing each event before delegating the actual instrumentation work.

3. **And** the supervisor MUST delegate the instrumentation work to the same developer sub-agent that implemented the ticket (respecting `AGENT_MODE` — `LocalDeveloperAgent` for `local`, `RemoteDeveloperAgent` for `remote`) by calling `implement_pr_recommendations(instrumentation_story, branch_name, workspace_path)` where `branch_name` is `dev_result.get("branch")` (the ORIGINAL branch — no new branch, no new PR) and `instrumentation_story` is a **shallow copy** of `story_details` whose `description` is augmented with a `"--- Diagnostic logging report ---\n"` block containing the ticket id, the failing test file list from the tester's initial result, the `instrumentation_targets` list, and the exact instruction: `"Add structured logging (Python `logging` module at INFO level for .py files, or the equivalent for the target stack) to the listed files. Preserve the additions — do NOT remove them after diagnosis. Commit and push to the existing branch."`. The original `story_details` MUST NOT be mutated (same Story 5.3 accumulated-context guard as Story 5.7).

4. **And** after `implement_pr_recommendations` returns `status == "success"` the supervisor MUST re-invoke `await self.tester.write_and_run_tests(story_details, dev_result.get("code_files", []), workspace_path)` exactly once. The retest MUST receive the ORIGINAL `story_details` (not the instrumentation-augmented copy) so accumulated context stays clean.

5. **Given** the retest returns `status == "success"`
   **When** the retest completes
   **Then** the supervisor MUST publish `agent_log` `{"message": "[Supervisor] Diagnostic logging resolved the issue for ticket <id> — proceeding to In Review."}`, MUST call `await project_store.update_ticket_status(project_id, ticket_id, "In Review")` (matching the Story 5.6 first-pass-success invariant — a run whose only remediation was better logging is still a "first pass" for the code-review gate; the Done gate is intentionally NOT auto-triggered here), and MUST return `{"ticket_id": ticket_id, "status": "completed", "development": dev_result, "testing": retest_result, "diagnostic_logging": {"attempted": True, "outcome": "success", "instrumentation_targets": [...]}}` from `_execute_ticket`.

6. **Given** the retest returns `status == "regression"`
   **When** the retest completes
   **Then** the supervisor MUST fall through to the Story 5.7 regression handler by calling `await self._handle_regression_and_maybe_fix(project_id, ticket_id, story_details, dev_result, workspace_path, retest_result)` and returning whatever it returns. The instrumentation attempt is recorded in the returned dict by adding `"diagnostic_logging": {"attempted": True, "outcome": "regression_after_instrumentation", "instrumentation_targets": [...]}` to the returned dict (do not overwrite Story 5.7's `regression_fix` key — both keys coexist). The one-shot Story 5.7 fix attempt is preserved: instrumentation + fix together constitute AT MOST two mutating passes on the branch (instrumentation pass + optional fix pass).

7. **Given** the retest returns `status == "insufficient_logs"` again OR `status == "error"` OR `implement_pr_recommendations` itself returned `status != "success"`
   **When** the escalation condition is reached
   **Then** the supervisor MUST publish a structured SSE event on channel `diagnostic_logging_escalation` with payload:
   ```json
   {
     "ticket_id": "<id>",
     "initial_failures": <the initial tester result's failures list or []>,
     "instrumentation_targets": <the initial tester result's instrumentation_targets list>,
     "instrumentation_attempt_summary": <one-line string from fix_result.get("message") or fix_result.get("reason") or "instrumentation attempt failed">,
     "retest_status": <the retest result's status, or the same as instrumentation_attempt failure if no retest ran>,
     "options": ["continue", "abandon"]
   }
   ```
   AND MUST also publish an `agent_log` event `{"message": "[Supervisor] Diagnostic logging did not restore log coverage for ticket <id> — user input required. Options: continue / abandon."}`, AND MUST call `await project_store.update_ticket_status(project_id, ticket_id, "Agent Blocked")` (same state machine value as Story 5.7 — the ticket is agent-blocked, not infrastructure-errored), AND MUST return `{"ticket_id": ticket_id, "status": "blocked", "reason": "diagnostic_logging_unresolved", "instrumentation_targets": [...], "initial_failures": [...]}` from `_execute_ticket`. The ticket does NOT transition to `Error` or `Done`. The developer-error short-circuit case (fix_result status != success) MUST NOT run the retest — per Story 5.7's precedent, no point re-running against unchanged code.

8. **And** `TesterAgent.write_and_run_tests` MUST expose the ability to return `status == "insufficient_logs"` for tests to drive. Extend the existing `TESTER_MOCK_MODE` env-var mock introduced by Story 5.7. New accepted values:
   - `"insufficient_logs"` (new): always emits `status="insufficient_logs"` with `instrumentation_targets=["src/scaffold.py"]` and a `failures` list identical in shape to the regression path (`[{"test": str, "message": str}, ...]`). Also writes a real log artifact + calls `project_store.write_test_artifact` (AD-6 gate applies to insufficient-log runs too — the artifact IS the evidence that logs were captured and found lacking). The log-file `summary` line reads `"pytest: {N} passed, 1 failed, 0 skipped (log coverage insufficient)"`.
   - `"insufficient_logs_then_success"` (new): first invocation of a given `TesterAgent` instance emits `insufficient_logs`, all subsequent invocations emit `success`. Enables the AC-5 happy path without patching.
   - `"insufficient_logs_then_regression"` (new): first invocation emits `insufficient_logs`, second invocation emits `regression`. Enables the AC-6 fall-through path without patching. On the second call the counter is `2`; use `self._invocation_count == 1` for the insufficient branch and `self._invocation_count == 2` for the regression branch inside this mode.
   - `"insufficient_logs_then_insufficient_logs"` (new): first two invocations emit `insufficient_logs`. Enables the AC-7 escalation path without patching.
   - Existing modes (`"success"`, `"regression"`, `"regression_then_success"`, any unknown) are UNCHANGED. Fall-open default remains `"success"`.
   The mock is read at method-invocation time via `os.environ.get("TESTER_MOCK_MODE", "success")` — same pattern Story 5.7 established (do NOT read at import time; tests need `monkeypatch.setenv`).

9. **And** the diagnostic-instrumentation step is attempted AT MOST ONCE per ticket per execution — there is no configurable retry count, no infinite loop. The one-shot invariant is enforced structurally (no loop around the instrumentation path in `_execute_ticket`), matching Story 5.7's approach. If the retest yields another `insufficient_logs`, the escalation is AC-7 — the supervisor does NOT re-instrument.

10. **And** the SSE event type `"diagnostic_logging_escalation"` MUST be a NEW dedicated event type distinct from `"regression_escalation"` (Story 5.7) so the frontend can eventually route the two to different escalation surfaces. `publish_event(project_id, event_type, payload)` already accepts arbitrary event types (verified in Story 5.7) — this is a data-only addition, no plumbing change.

11. **And** the diagnostic logging added by the developer MUST be preserved in the codebase — the story does NOT introduce any cleanup step, "revert instrumentation" branch, or `try/finally` that removes the added logging. The instrumentation prompt to the developer (AC-3) explicitly instructs preservation. FR-19 wording: "the added logging is preserved in the codebase — it is not removed after diagnosis." This is a design invariant, not a runtime check.

## Tasks / Subtasks

- [x] 1. Extend `TesterAgent` with an insufficient-logs signal (AC: 1, 8)
  - [x] 1.1 In `agents/tester_agent.py`, keep the existing `__init__` (`self._invocation_count = 0`) — no change.
  - [x] 1.2 At the top of `write_and_run_tests`, after the existing `mock_mode = os.environ.get(...)` and `self._invocation_count += 1`, extend the `effective_mode` resolution to add the four new modes BEFORE the final `else` fallback:
    ```python
    if mock_mode == "regression":
        effective_mode = "regression"
    elif mock_mode == "regression_then_success" and self._invocation_count == 1:
        effective_mode = "regression"
    elif mock_mode == "insufficient_logs":
        effective_mode = "insufficient_logs"
    elif mock_mode == "insufficient_logs_then_success" and self._invocation_count == 1:
        effective_mode = "insufficient_logs"
    elif mock_mode == "insufficient_logs_then_regression" and self._invocation_count == 1:
        effective_mode = "insufficient_logs"
    elif mock_mode == "insufficient_logs_then_regression" and self._invocation_count == 2:
        effective_mode = "regression"
    elif mock_mode == "insufficient_logs_then_insufficient_logs" and self._invocation_count <= 2:
        effective_mode = "insufficient_logs"
    else:
        effective_mode = "success"
    ```
    Order matters: the `regression_then_success` branch stays where it is (Story 5.7 tests assert on its behavior). Add the new branches AFTER the existing two conditions and BEFORE the terminal `else`.
  - [x] 1.3 Amend the log-file `summary` line to include the insufficient-logs case. Extend the existing `if effective_mode == "regression": ... else: ...` block to a three-way:
    ```python
    if effective_mode == "regression":
        passed = max(0, len(test_files) - 1)
        summary = f"pytest: {passed} passed, 1 failed, 0 skipped"
    elif effective_mode == "insufficient_logs":
        passed = max(0, len(test_files) - 1)
        summary = f"pytest: {passed} passed, 1 failed, 0 skipped (log coverage insufficient)"
    else:
        summary = f"pytest: {len(test_files)} passed, 0 failed, 0 skipped"
    ```
    The `(log coverage insufficient)` suffix is asserted by Task 4.1.5.
  - [x] 1.4 Do NOT alter the log write path, the forward-slash normalisation, the `os.makedirs(exist_ok=True)` calls, or the `if project_id: await project_store.write_test_artifact(...)` gate — the insufficient-logs path writes the artifact unconditionally too (AD-6).
  - [x] 1.5 Extend the final return-dict construction. The existing structure is `if effective_mode == "regression": return {...}; return <success dict>`. Insert an `insufficient_logs` branch BEFORE the regression branch (order does not functionally matter but reads better top-down):
    ```python
    if effective_mode == "insufficient_logs":
        return {
            "status": "insufficient_logs",
            "test_files": test_files,
            "coverage": "0%",
            "message": "1 test failed; log coverage insufficient to diagnose.",
            "failures": [
                {
                    "test": "tests/test_scaffold.py::test_perform_action",
                    "message": "AssertionError: mocked insufficient logs (TESTER_MOCK_MODE=insufficient_logs)",
                }
            ],
            "instrumentation_targets": ["src/scaffold.py"],
            "test_artifact_ref": artifact_ref,
            "artifact_log_path": log_path,
        }
    if effective_mode == "regression":
        return {
            # ... existing regression dict UNCHANGED ...
        }
    # existing success dict UNCHANGED
    ```
    The `instrumentation_targets` list is a NEW key. Its shape (`list[str]`) is the contract Task 2 relies on. Do NOT change it or bury it under a nested dict.
  - [x] 1.6 Do NOT touch the `status == "error"` path (still not emitted by the mock; still intentional).

- [x] 2. Add the insufficient-logs handler in `SupervisorAgent._execute_ticket` (AC: 1, 2, 3, 4, 5, 6, 7, 9, 10, 11)
  - [x] 2.1 In `agents/supervisor_agent.py`, expand the Story 5.7 three-way branch to a **four-way** branch on `test_result.get("status")`. The current shape is:
    ```python
    tester_status = test_result.get("status")
    if tester_status == "success":  # In Review path
        ...
    if tester_status == "regression":
        return await self._handle_regression_and_maybe_fix(...)
    # error / unknown branch: publish agent_log, set Error, return "testing_failed"
    ```
    Insert the insufficient-logs branch BETWEEN the success check and the regression check (per FR-19: instrumentation happens BEFORE the fix attempt):
    ```python
    if tester_status == "insufficient_logs":
        return await self._handle_insufficient_logs_and_instrument(
            project_id, ticket_id, story_details, dev_result, workspace_path, test_result,
        )
    ```
    Do NOT convert the sequence to `elif` — the existing code uses independent `if` statements with early `return`. Match the surrounding style.
  - [x] 2.2 Add a new private method `_handle_insufficient_logs_and_instrument` on `SupervisorAgent`, placed IMMEDIATELY BELOW `_execute_ticket` and ABOVE the Story 5.7 `_handle_regression_and_maybe_fix` method (keeps orchestration methods grouped in flow order — instrumentation runs before regression fix). Signature:
    ```python
    async def _handle_insufficient_logs_and_instrument(
        self,
        project_id: str,
        ticket_id: str,
        story_details: dict,
        dev_result: dict,
        workspace_path: str | None,
        initial_test_result: dict,
    ) -> dict:
    ```
  - [x] 2.3 First action — publish AC-1's SSE event:
    ```python
    await publish_event(project_id, "agent_log", {
        "message": (
            f"[Supervisor] Insufficient log coverage for ticket {ticket_id} — "
            f"adding diagnostic logging."
        ),
    })
    ```
  - [x] 2.4 Publish the per-file `Adding diagnostic logging to <file>…` events (AC-2). The `…` is a literal U+2026 ELLIPSIS character (do NOT use three ASCII dots; the epic wording is verbatim):
    ```python
    instrumentation_targets = initial_test_result.get("instrumentation_targets") or []
    for target in instrumentation_targets:
        await publish_event(project_id, "agent_log", {
            "message": f"Adding diagnostic logging to {target}\u2026",
        })
    ```
    If `instrumentation_targets` is empty (defensive — the tester contract guarantees non-empty on `insufficient_logs`, but the supervisor must not crash), fall through with no per-file events and continue to Task 2.5.
  - [x] 2.5 Build the instrumentation report on a SHALLOW COPY of `story_details` — never mutate the caller's dict (Story 5.3 leakage guard, identical rationale to Story 5.7 Task 2.4):
    ```python
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
    ```
  - [x] 2.6 Delegate to the developer via `implement_pr_recommendations`, using the ORIGINAL branch from `dev_result` (no new branch — same convention as Story 5.7 Task 2.5):
    ```python
    branch_name = dev_result.get("branch") or f"feature/{ticket_id}"
    if self.mode == "local":
        fix_result = await self.local_developer.implement_pr_recommendations(
            instr_story, branch_name, workspace_path,
        )
    else:
        fix_result = await self.remote_developer.implement_pr_recommendations(
            instr_story, branch_name, workspace_path,
        )
    ```
  - [x] 2.7 If `fix_result.get("status") != "success"` — developer itself errored (Context7 grounding failure, MCP timeout, etc.). Skip the retest entirely and escalate immediately as an AC-7 outcome (mirror Story 5.7 Task 2.6):
    ```python
    if fix_result.get("status") != "success":
        await publish_event(project_id, "agent_log", {
            "message": (
                f"[Supervisor] Diagnostic instrumentation attempt errored for "
                f"ticket {ticket_id} — escalating."
            ),
        })
        return await self._escalate_diagnostic_logging(
            project_id, ticket_id, initial_test_result,
            instrumentation_attempt_summary=(
                fix_result.get("message")
                or fix_result.get("reason")
                or "instrumentation attempt failed"
            ),
            retest_status=fix_result.get("status", "error"),
        )
    ```
    No retest against unchanged code (same rationale as Story 5.7).
  - [x] 2.8 Otherwise re-run the tester ONCE with the ORIGINAL `story_details` (never `instr_story` — the instrumentation block has no place in the test-artifact context, same guard as Story 5.7 Task 2.7):
    ```python
    await publish_event(project_id, "agent_log", {
        "message": (
            f"[Supervisor] Diagnostic logging committed for ticket {ticket_id} — "
            f"re-running test suite."
        ),
    })
    retest_result = await self.tester.write_and_run_tests(
        story_details, dev_result.get("code_files", []), workspace_path,
    )
    retest_status = retest_result.get("status")
    ```
  - [x] 2.9 Three-way branch on `retest_status`:
    - `"success"` → AC-5 happy path:
      ```python
      await publish_event(project_id, "agent_log", {
          "message": (
              f"[Supervisor] Diagnostic logging resolved the issue for ticket "
              f"{ticket_id} — proceeding to In Review."
          ),
      })
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
      ```
      DO NOT call `close_ticket_as_done` here. Rationale: a run whose only remediation was adding logging still counts as a "first pass" for code-review purposes — the Story 5.6 gate remains code-review-driven. This is a deliberate divergence from Story 5.7's autonomous-fix-success path (which DOES call `close_ticket_as_done` because the fix path re-tested successful code that the tester previously flagged as broken).
    - `"regression"` → AC-6 fall-through to Story 5.7 regression handler:
      ```python
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
      Mutating the returned dict from `_handle_regression_and_maybe_fix` is safe — that dict is freshly constructed inside the callee and returned by value to us; we own it. The `regression_fix` key stays intact (Story 5.7 tests assert on it) and we ADD `diagnostic_logging` alongside it.
    - Any other value (`"insufficient_logs"` again, `"error"`, unknown) → AC-7 escalation:
      ```python
      return await self._escalate_diagnostic_logging(
          project_id, ticket_id, initial_test_result,
          instrumentation_attempt_summary=(
              fix_result.get("message")
              or fix_result.get("pr_url")
              or "instrumentation committed"
          ),
          retest_status=retest_status,
      )
      ```
  - [x] 2.10 Add a helper `_escalate_diagnostic_logging` IMMEDIATELY BELOW `_handle_insufficient_logs_and_instrument` and ABOVE `_handle_regression_and_maybe_fix`:
    ```python
    async def _escalate_diagnostic_logging(
        self,
        project_id: str,
        ticket_id: str,
        initial_test_result: dict,
        instrumentation_attempt_summary: str,
        retest_status: str,
    ) -> dict:
        initial_failures = initial_test_result.get("failures") or []
        instrumentation_targets = initial_test_result.get("instrumentation_targets") or []
        payload = {
            "ticket_id": ticket_id,
            "initial_failures": initial_failures,
            "instrumentation_targets": instrumentation_targets,
            "instrumentation_attempt_summary": instrumentation_attempt_summary,
            "retest_status": retest_status,
            "options": ["continue", "abandon"],
        }
        await publish_event(project_id, "diagnostic_logging_escalation", payload)
        await publish_event(project_id, "agent_log", {
            "message": (
                f"[Supervisor] Diagnostic logging did not restore log coverage "
                f"for ticket {ticket_id} — user input required. "
                f"Options: continue / abandon."
            ),
        })
        await project_store.update_ticket_status(project_id, ticket_id, "Agent Blocked")
        return {
            "ticket_id": ticket_id,
            "status": "blocked",
            "reason": "diagnostic_logging_unresolved",
            "instrumentation_targets": instrumentation_targets,
            "initial_failures": initial_failures,
        }
    ```
    Two events (`diagnostic_logging_escalation` + `agent_log`) are intentional and parallel to Story 5.7's escalation. The structured event powers the future dedicated UI; the log line keeps plain-chat users informed.
  - [x] 2.11 Do NOT modify `close_ticket_as_done`, `_handle_regression_and_maybe_fix`, `_escalate_regression`, `_delegate_to_developer`, or `_build_accumulated_context`. Do NOT touch the environment-failed / developer-failed branches or the final `error / unknown` fallback in `_execute_ticket`.

- [x] 3. `main_agent.py` — no diagnostic-logging handling on the CLI path (AC: 9, out of scope)
  - [x] 3.1 Confirm by inspection that `agents/main_agent.py` still uses its own inline flow (not `SupervisorAgent._execute_ticket`) and therefore is NOT impacted by this story. Document this in Dev Notes but change no code in `main_agent.py`. Same rationale as Story 5.7 Task 3.1.

- [x] 4. Tests (AC: 1–11)
  - [x] 4.1 Extend `tests/test_tester_regression_signal.py` — DO NOT create a new file; keep the tester-mock tests co-located with the existing Story 5.7 tester tests for future maintainers.
    - [x] 4.1.1 `test_tester_returns_insufficient_logs_when_env_set` (monkeypatched `TESTER_MOCK_MODE=insufficient_logs`): assert `result["status"] == "insufficient_logs"`, `result["failures"]` is a non-empty list of `{"test": str, "message": str}`, `result["instrumentation_targets"] == ["src/scaffold.py"]`, `result["test_artifact_ref"]` is a non-empty string, `result["artifact_log_path"]` exists on disk.
    - [x] 4.1.2 `test_tester_insufficient_logs_still_writes_artifact` (`TESTER_MOCK_MODE=insufficient_logs`, `project_id="proj-1"`): patch `backend.store.project_store.write_test_artifact` with `AsyncMock`; assert the patch was awaited exactly once with `(project_id, ticket_id, test_artifact_ref)` — AD-6 applies to insufficient-log runs too.
    - [x] 4.1.3 `test_tester_insufficient_logs_then_success_toggles` (`TESTER_MOCK_MODE=insufficient_logs_then_success`, same `TesterAgent()` instance called twice): assert first call `status=="insufficient_logs"`, second call `status=="success"`.
    - [x] 4.1.4 `test_tester_insufficient_logs_then_regression_chain` (`TESTER_MOCK_MODE=insufficient_logs_then_regression`, same instance called three times): assert first call `status=="insufficient_logs"`, second call `status=="regression"`, third call `status=="success"` (falls through to the `else` fallback).
    - [x] 4.1.5 `test_tester_insufficient_logs_log_summary_reflects_coverage_gap`: with `TESTER_MOCK_MODE=insufficient_logs`, run against a tmp workspace with `code_files=["a.py"]`; open the file at `result["artifact_log_path"]`; assert its content contains the substring `"log coverage insufficient"` AND `"1 failed"`.
    - [x] 4.1.6 `test_tester_insufficient_logs_then_insufficient_logs_stays_insufficient` (`TESTER_MOCK_MODE=insufficient_logs_then_insufficient_logs`, same instance called twice, then a third time): assert first two calls return `status=="insufficient_logs"`, third call returns `status=="success"` (only two invocations qualify per the `<= 2` guard).
    - [x] 4.1.7 Verify existing Story 5.7 tests in the same file are NOT modified and still pass unchanged — the new modes are additive.
  - [x] 4.2 Add `tests/test_supervisor_diagnostic_logging.py` — heavily mocked, no real MCP, no real store. Follow the fixture patterns already established in `tests/test_supervisor_regression_fix.py`.
    - [x] 4.2.1 `test_insufficient_logs_triggers_instrumentation_then_success`:
      - Patch `tester.write_and_run_tests` with `AsyncMock` whose `side_effect` returns two values: first an `insufficient_logs` dict (`status="insufficient_logs"`, `failures=[{"test": "t", "message": "m"}]`, `instrumentation_targets=["src/a.py", "src/b.py"]`, `test_artifact_ref="logs/x.log"`), then a success dict (`status="success"`, `test_artifact_ref="logs/y.log"`).
      - Patch `remote_developer.implement_pr_recommendations` with `AsyncMock(return_value={"status": "success", "branch": "feature/tkt-1", "message": "instrumented"})`.
      - Patch `remote_developer.implement_feature` with `AsyncMock(return_value={"status": "success", "branch": "feature/tkt-1", "code_files": ["src/a.py"], "message": "ok"})`.
      - Patch `environment.prepare_environment` with `MagicMock` returning `{"status": "success", "workspace_path": "/tmp/ws", "repo_full_name": "o/r"}`.
      - Patch `backend.store.project_store.get_project` with `AsyncMock` returning `{"ticket_history": [{"id": "tkt-1", "title": "T", "description": "D", "status": "In Progress"}]}`.
      - Patch `backend.store.project_store.update_ticket_status` and `backend.store.project_store.mark_ticket_done` with `AsyncMock`.
      - Patch `backend.api.sse.publish_event` with `AsyncMock`.
      - Call `await supervisor._execute_ticket("proj-1", "tkt-1", ["tkt-1"])`.
      - Assert return dict has `status="completed"` AND `diagnostic_logging == {"attempted": True, "outcome": "success", "instrumentation_targets": ["src/a.py", "src/b.py"]}`.
      - Assert `implement_pr_recommendations` was awaited exactly once with the ORIGINAL branch `"feature/tkt-1"` and a `story_details` whose `description` contains `"--- Diagnostic logging report ---"` AND contains `"src/a.py"` AND `"src/b.py"` in the "Files to instrument" section.
      - Assert `tester.write_and_run_tests` was awaited exactly twice, and the second call's `story_details` arg did NOT contain `"--- Diagnostic logging report ---"` (retest sees clean story).
      - Assert `update_ticket_status` was awaited with `("proj-1", "tkt-1", "In Review")` — NOT `mark_ticket_done`. This encodes the AC-5 divergence from Story 5.7.
      - Assert `publish_event` was awaited with an `agent_log` whose message equals `"Adding diagnostic logging to src/a.py\u2026"` AND with a second one equal to `"Adding diagnostic logging to src/b.py\u2026"`. Both in order.
      - Assert NO `diagnostic_logging_escalation` event was published and NO `regression_escalation` event was published.
    - [x] 4.2.2 `test_insufficient_logs_then_regression_falls_through_to_regression_handler`:
      - Patch tester with `side_effect` returning: `insufficient_logs` → `regression` → `success` (three calls: initial, retest after instrumentation, retest after regression fix).
      - Patch `implement_pr_recommendations` to return success on both calls.
      - Assert `tester.write_and_run_tests` was awaited exactly THREE times.
      - Assert `implement_pr_recommendations` was awaited exactly TWICE (once for instrumentation, once for regression fix).
      - Assert `mark_ticket_done` was awaited exactly once with `("proj-1", "tkt-1")` — the regression handler's success path invokes `close_ticket_as_done` (Story 5.7 behavior, preserved).
      - Assert the return dict has `status="completed"`, `regression_fix == {"attempted": True, "outcome": "success"}`, AND `diagnostic_logging == {"attempted": True, "outcome": "regression_after_instrumentation", "instrumentation_targets": ["src/scaffold.py"]}`. Both keys coexist.
      - Assert the first `implement_pr_recommendations` call received a `story_details` whose description contains `"--- Diagnostic logging report ---"`.
      - Assert the second `implement_pr_recommendations` call received a `story_details` whose description contains `"--- Regression report ---"` (NOT `"--- Diagnostic logging report ---"` — Story 5.7 handler builds its own report on a fresh shallow copy).
    - [x] 4.2.3 `test_insufficient_logs_persists_after_instrumentation_escalates`:
      - Tester returns `insufficient_logs` on both calls. `implement_pr_recommendations` returns success.
      - Assert return dict is `{"ticket_id": "tkt-1", "status": "blocked", "reason": "diagnostic_logging_unresolved", "instrumentation_targets": ["src/scaffold.py"], "initial_failures": [...]}`.
      - Assert `publish_event` was awaited with `("proj-1", "diagnostic_logging_escalation", <payload>)` where payload has keys `ticket_id`, `initial_failures`, `instrumentation_targets`, `instrumentation_attempt_summary`, `retest_status == "insufficient_logs"`, `options == ["continue", "abandon"]`.
      - Assert `update_ticket_status` was awaited with `("proj-1", "tkt-1", "Agent Blocked")` — NOT `"Error"`.
      - Assert `mark_ticket_done` was NOT called.
      - Assert NO `regression_escalation` event was published.
    - [x] 4.2.4 `test_insufficient_logs_developer_error_escalates_without_retest`:
      - Tester's first call returns `insufficient_logs`. `implement_pr_recommendations` returns `{"status": "error", "reason": "context7_grounding_failed", "message": "boom"}`.
      - Assert `tester.write_and_run_tests` was awaited exactly ONCE (no retest — AC-7 short-circuit).
      - Assert return dict is a `status="blocked"` escalation with `reason="diagnostic_logging_unresolved"` and the `diagnostic_logging_escalation` payload has `instrumentation_attempt_summary == "boom"` and `retest_status == "error"`.
      - Assert `update_ticket_status` was awaited with `("proj-1", "tkt-1", "Agent Blocked")`.
    - [x] 4.2.5 `test_insufficient_logs_report_is_shallow_copied_not_mutated`:
      - Patch `implement_feature` to capture the `story_details` arg it received (append to a list closure). After `_execute_ticket` returns, assert that captured `story_details["description"]` does NOT contain `"--- Diagnostic logging report ---"`.
      - The instrumentation report must appear ONLY in the `story_details` arg passed to `implement_pr_recommendations` — captured similarly.
      - This is the Story 5.3 accumulated-context leakage guard, identical rationale to Story 5.7 Task 4.2.4.
    - [x] 4.2.6 `test_first_pass_success_does_not_invoke_diagnostic_handler`:
      - Tester returns `success` on the first (and only) call.
      - Assert `implement_pr_recommendations` was NEVER awaited.
      - Assert `update_ticket_status` was awaited with `"In Review"` (Story 5.6 first-pass invariant, preserved).
      - Assert NO `diagnostic_logging_escalation` event was published.
      - Assert NO `Adding diagnostic logging to …` `agent_log` event was published.
    - [x] 4.2.7 `test_regression_without_insufficient_logs_uses_story_5_7_handler_directly`:
      - Tester returns `regression` on the first call (skipping the insufficient-logs step entirely).
      - Assert `_handle_insufficient_logs_and_instrument` was NOT invoked (patch it with an `AsyncMock` and assert `assert_not_awaited()`).
      - Assert `_handle_regression_and_maybe_fix` WAS invoked (patch it similarly and assert `assert_awaited_once()`). This confirms the four-way branch preserves Story 5.7's direct-regression path.
  - [x] 4.3 Regression run: `python -m pytest tests/ -q` MUST show all previously-passing tests still passing. Existing Story 5.7 tests (`tests/test_supervisor_regression_fix.py`, `tests/test_tester_regression_signal.py`) MUST pass unchanged — the four-way branch preserves Story 5.7 semantics because `insufficient_logs` is a NEW status value not previously emitted.
  - [x] 4.4 Audit `tests/test_supervisor_test_artifact_gate.py`, `tests/test_supervisor_regression_fix.py`, and `tests/test_supervisor_agent.py` for any test that patches `tester.write_and_run_tests` with a mock returning `{"status": "success", ...}` or `{"status": "regression", ...}` — those tests must continue to pass unchanged. Document in Dev Notes that you verified each `write_and_run_tests` mock in those files does NOT emit `insufficient_logs`.

- [x] 5. Documentation & schema notes
  - [x] 5.1 Do NOT create a new markdown doc for this story unless the user asks — per repo convention.
  - [x] 5.2 Do NOT modify `backend/store/migrations.py`. `"Agent Blocked"` (Story 5.7) is already in circulation. No new column, no CHECK constraint change.
  - [x] 5.3 Do NOT touch `.env.example`. The new `TESTER_MOCK_MODE` values are test-only. Documenting them in `.env.example` would risk users setting them in real deployments.
  - [x] 5.4 Do NOT alter `backend/api/sse.py` or add a new endpoint. `publish_event` already accepts arbitrary event types (verified in Story 5.7); the new `"diagnostic_logging_escalation"` event type is a data-only addition.
  - [x] 5.5 Do NOT modify `agents/developer_agent.py` or `agents/local_developer_agent.py`. The instrumentation instruction is embedded in the augmented `story_details["description"]` (Task 2.5); `implement_pr_recommendations` already reads that field and passes it to the LLM prompt.

## Dev Notes

### What Stories 5.1–5.7 Built (Must Not Break)

- **Story 5.1** — `execution_lock.py` sequential lock. The diagnostic-logging handler runs INSIDE `_execute_ticket`, already lock-scoped. No lock code changes.
- **Story 5.2** — `SupervisorAgent._execute_ticket` sets `"In Review"` after tests pass. Story 5.8 preserves that transition AND extends it: a run whose only remediation was diagnostic logging ALSO lands on `"In Review"` (not `Done`). Rationale in AC-5: instrumentation is not a code fix; the code-review gate still owns the Done transition on this path.
- **Story 5.3** — `_build_accumulated_context` reads `ticket_history[].description`. Story 5.8 augments `story_details["description"]` in a SHALLOW COPY (`dict(story_details)`), never mutates the caller's dict. Same guard as Story 5.7. Verified by Task 4.2.5.
- **Story 5.4** — chat/agent_memory JSONB round-tripping. Untouched.
- **Story 5.5** — Context7 grounding runs at the top of `implement_pr_recommendations`. If grounding fails during the instrumentation call, the developer returns `{"status": "error", "reason": "context7_grounding_failed"}` — Task 2.7 catches this and escalates immediately without a retest. AD-8 preserved.
- **Story 5.6** — `close_ticket_as_done` is the AD-6-gated Done transition. Story 5.8 does NOT invoke it on the instrumentation-success path (AC-5): that path goes to `"In Review"`, matching Story 5.6's first-pass-success invariant. `close_ticket_as_done` remains invoked ONLY on the Story 5.7 autonomous-fix-success path.
- **Story 5.7** — regression handler, `TESTER_MOCK_MODE`, `Agent Blocked` state, `regression_escalation` SSE event type. Story 5.8 extends `TESTER_MOCK_MODE` with additive values (existing modes unchanged), REUSES the `Agent Blocked` state, ADDS a new SSE event type `diagnostic_logging_escalation` alongside `regression_escalation`, and INSERTS the insufficient-logs branch BEFORE the regression branch in `_execute_ticket`. On the insufficient_logs → regression fall-through (AC-6), the Story 5.7 handler is invoked with the ORIGINAL `story_details` — its shallow-copy guard runs cleanly on a description that has NEVER been mutated by the Story 5.8 handler.

### Architecture Compliance

- **AD-1 (agent hierarchy):** All instrumentation delegation goes through `SupervisorAgent`. Sub-agents remain unaware of each other. `_handle_insufficient_logs_and_instrument` calls `self.local_developer` or `self.remote_developer` via the same routing pattern as `_delegate_to_developer` and `_handle_regression_and_maybe_fix`. No new peer visibility.
- **AD-2 (sequential lock):** Instrumentation, retest, and any subsequent regression fix all happen inside the same `_execute_ticket` call under the existing sequential lock. No parallel work.
- **AD-3 (MCPManager singleton):** `implement_pr_recommendations` reuses the singleton via existing `load_dev_tools()` / `load_context7_mcp_tools()` context managers. No ad-hoc MCP instantiation.
- **AD-4 (LLM-as-last-resort):** The insufficient-logs detection uses NO LLM (mocked signal from tester). Only the instrumentation step invokes the LLM (already-LLM-driven `implement_pr_recommendations`). Escalation invokes NO LLM — structured SSE + status update only.
- **AD-5 (project isolation):** All operations scoped by `project_id`. No cross-project reads.
- **AD-6 (test artifact gate):** The insufficient-logs path STILL writes a test artifact (Task 1.4) — failed-with-poor-coverage runs are still verifiable evidence. `close_ticket_as_done` is NOT invoked on the AC-5 success path (that path stops at In Review); the gate remains code-review-driven for logging-only remediations.
- **AD-7 (streaming over polling):** `diagnostic_logging_escalation` and the per-file `Adding diagnostic logging to <file>…` events are structured SSE, published as they happen. No batching, no polling.
- **AD-8 (Context7 grounding):** Grounding runs inside `implement_pr_recommendations` (existing behavior). AC-7's short-circuit correctly handles the grounding-failed case as a developer error.
- **AD-9 (async throughout):** Every new method (`_handle_insufficient_logs_and_instrument`, `_escalate_diagnostic_logging`) is `async def`. All calls use `await`.
- **AD-13 (env vars only):** `TESTER_MOCK_MODE` new values read via the SAME `os.environ.get("TESTER_MOCK_MODE", "success")` call at method-invocation time. No import-time reads, no hardcoded fallbacks. Same rationale as Story 5.7.
- **Ticket state machine (Consistency Conventions):** `Pending → In Progress → Done | Error | Agent Blocked`. Instrumentation-success path uses `In Review` (an interim state, not a terminal state — `In Review` is legitimate per Story 5.2 semantics). Escalation path uses `Agent Blocked` (identical to Story 5.7). No new state value introduced.
- **FR-19 preservation invariant:** Diagnostic logging added to the codebase is NEVER removed. This is enforced by (a) the prompt to the developer explicitly instructing preservation (Task 2.5's instrumentation_block), (b) the absence of any cleanup step in this story, and (c) the epic's explicit wording repeated in AC-11. There is no runtime check — this is a design invariant.
- **project-context.md — "Default Logging Scaffold in Generated Projects" (Story 5.10, future):** Story 5.10 will make the default `logging` module available in every generated project so the developer agent can add `INFO`-level statements without additional configuration. Story 5.8 does NOT depend on 5.10 — the instrumentation prompt says "structured logging (Python `logging` module at INFO level for .py files, or the equivalent for the target stack)" so it works both before and after 5.10 lands.

### Files Being Modified — Current State and Change Scope

**`agents/tester_agent.py`** (current state: 116 lines, async, mock scaffold with Story 5.7 `TESTER_MOCK_MODE`; returns `success` | `regression`)
- Current: `write_and_run_tests` reads `TESTER_MOCK_MODE`, increments `_invocation_count`, resolves `effective_mode` via a small if/elif chain, writes a log artifact + calls `write_test_artifact` unconditionally, returns either the regression dict or the success dict.
- Change: `effective_mode` resolution gains four new branches (`insufficient_logs`, `insufficient_logs_then_success`, `insufficient_logs_then_regression`, `insufficient_logs_then_insufficient_logs`); the log-file `summary` line gains an `insufficient_logs` case with a `(log coverage insufficient)` suffix; the return-dict construction gains an `insufficient_logs` branch inserted BEFORE the regression branch. Existing `success` and `regression` branches are UNCHANGED.
- Must preserve: the exact `success` return-dict shape (Story 5.6 tests). The exact `regression` return-dict shape (Story 5.7 tests). The scaffold-file generation. Both `print` statements. Forward-slash normalisation of `artifact_ref`. The `project_id` truthy guard around `write_test_artifact`. The `__init__` counter (Story 5.7).

**`agents/supervisor_agent.py`** (current state: ~510 lines including `close_ticket_as_done`, `_handle_regression_and_maybe_fix`, `_escalate_regression`; Stories 5.1–5.7)
- Current: `_execute_ticket` has a three-way branch on `test_result.status`: `success` → In Review; `regression` → `_handle_regression_and_maybe_fix`; else → Error/testing_failed.
- Change: insert an `insufficient_logs` branch BETWEEN the `success` check and the `regression` check, dispatching to a new `_handle_insufficient_logs_and_instrument`. Add `_handle_insufficient_logs_and_instrument` and `_escalate_diagnostic_logging` private methods, positioned IMMEDIATELY BELOW `_execute_ticket` and ABOVE `_handle_regression_and_maybe_fix` (flow order: instrumentation → regression fix → escalation). Add ONE new SSE event type (`diagnostic_logging_escalation`) — data-only, no plumbing change.
- Must preserve: the entire `_execute_ticket` shape up to and including the tester call. The `In Review` transition on first-pass success. `_handle_regression_and_maybe_fix` (unchanged — Story 5.7 tests assert on it). `_escalate_regression` (unchanged). `close_ticket_as_done` (unchanged — Story 5.6 tests). `_delegate_to_developer`. `_build_accumulated_context` (Story 5.3). The environment failure branch. The developer failure branch. The `error / unknown` fallback branch.

**`agents/main_agent.py`** — NOT modified. CLI path does not use `SupervisorAgent._execute_ticket`.

**`agents/developer_agent.py` / `agents/local_developer_agent.py`** — NOT modified. `implement_pr_recommendations` on both sides accepts arbitrary `description` strings and forwards them to the LLM prompt; the instrumentation instruction is delivered via the augmented description.

**`backend/store/project_store.py`** — NOT modified. `update_ticket_status` accepts arbitrary string status values (JSONB, no CHECK constraint).

**`backend/api/sse.py`** — NOT modified. `publish_event(project_id, event_type, payload)` already accepts arbitrary event types.

**NEW files:**
- `tests/test_supervisor_diagnostic_logging.py`

**MODIFIED test files:**
- `tests/test_tester_regression_signal.py` — extended with the six new insufficient-logs tests in Task 4.1.

**DO NOT modify:**
- `backend/store/errors.py`, `backend/store/database.py`, `backend/store/migrations.py`
- `backend/api/routes/execute.py`
- `backend/execution_lock.py`
- `agents/environment_agent.py`, `agents/context7_grounding.py`
- Existing Story 5.5 grounding tests, Story 5.6 gate tests, Story 5.7 regression tests

### Windows / Path Notes

- No new path operations introduced. The tester log-write reuses the Story 5.6 code path (already `os.sep`-normalised).
- All new file writes are inside existing `os.makedirs(exist_ok=True)`-scoped directories.
- The literal U+2026 ELLIPSIS character (`…`) in the `Adding diagnostic logging to <file>…` SSE message is UTF-8 encoded when Python writes to the SSE payload — no special handling needed. In the source code use the escape `\u2026` for clarity (Task 2.4). Tests assert on the same escape.

### Reference Implementation Sketch (non-normative)

Supervisor four-way branch:
```python
tester_status = test_result.get("status")
if tester_status == "success":
    await project_store.update_ticket_status(project_id, ticket_id, "In Review")
    await publish_event(project_id, "agent_log", {
        "message": f"[Supervisor] Ticket {ticket_id} complete — status set to 'In Review'.",
    })
    return {"ticket_id": ticket_id, "status": "completed", "development": dev_result, "testing": test_result}

if tester_status == "insufficient_logs":
    return await self._handle_insufficient_logs_and_instrument(
        project_id, ticket_id, story_details, dev_result, workspace_path, test_result,
    )

if tester_status == "regression":
    return await self._handle_regression_and_maybe_fix(
        project_id, ticket_id, story_details, dev_result, workspace_path, test_result,
    )

# Error / unknown — preserve the Story 5.6/5.7 defensive branch verbatim.
await publish_event(project_id, "agent_log", {
    "message": f"[Supervisor] Testing phase failed for ticket {ticket_id}.",
})
await project_store.update_ticket_status(project_id, ticket_id, "Error")
return {"ticket_id": ticket_id, "status": "error", "reason": "testing_failed"}
```

Tester insufficient-logs branch (skeleton, additive):
```python
if effective_mode == "insufficient_logs":
    return {
        "status": "insufficient_logs",
        "test_files": test_files,
        "coverage": "0%",
        "message": "1 test failed; log coverage insufficient to diagnose.",
        "failures": [
            {
                "test": "tests/test_scaffold.py::test_perform_action",
                "message": "AssertionError: mocked insufficient logs (TESTER_MOCK_MODE=insufficient_logs)",
            }
        ],
        "instrumentation_targets": ["src/scaffold.py"],
        "test_artifact_ref": artifact_ref,
        "artifact_log_path": log_path,
    }
```

### Project Structure Notes

- Alignment with unified project structure: new supervisor methods live in `agents/supervisor_agent.py` alongside the existing Story 5.7 handlers. Test files under `tests/` prefixed `test_`. New test file `tests/test_supervisor_diagnostic_logging.py` mirrors the naming of `tests/test_supervisor_regression_fix.py`.
- Detected conflicts or variances: none. The four-way branch in `_execute_ticket` is a pure superset of the Story 5.7 three-way branch — any status value other than `insufficient_logs` behaves identically to the Story 5.7 code path.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.8: Diagnostic Logging Before Escalation]
- [Source: _bmad-output/planning-artifacts/epics.md#FR-19: Diagnostic Logging Before Escalation]
- [Source: _bmad-output/implementation-artifacts/5-7-autonomous-pre-merge-regression-fix.md#Tasks / Subtasks] — precedent for the `TESTER_MOCK_MODE` extension pattern and shallow-copy story_details pattern.
- [Source: _bmad-output/implementation-artifacts/5-6-mandatory-test-artifact-gate.md] — precedent for `close_ticket_as_done` and the AD-6 gate. Story 5.8 respects but does not invoke this gate on the instrumentation-success path.
- [Source: _bmad-output/project-context.md#Testing Rules] — `TesterAgent` scaffold-only rule; real pytest wiring remains out of scope.
- [Source: agents/supervisor_agent.py#_execute_ticket] — current three-way branch (post-Story 5.7).
- [Source: agents/tester_agent.py#write_and_run_tests] — current `TESTER_MOCK_MODE` resolution (post-Story 5.7).
- [Source: agents/developer_agent.py#implement_pr_recommendations] — reused for instrumentation delegation.
- [Source: agents/local_developer_agent.py#implement_pr_recommendations] — reused for instrumentation delegation.

## Dev Agent Record

### Agent Model Used

GitHub Copilot (Claude Opus 4.7) — bmad-dev-story workflow.

### Debug Log References

- `pytest tests/test_tester_regression_signal.py tests/test_supervisor_diagnostic_logging.py -q` → 19 passed.
- `pytest tests/ -q` → 105 passed, 6 pre-existing warnings (unchanged), 0 regressions.

### Completion Notes List

- **Task 1 (TesterAgent):** Added four new `TESTER_MOCK_MODE` branches (`insufficient_logs`, `insufficient_logs_then_success`, `insufficient_logs_then_regression`, `insufficient_logs_then_insufficient_logs`) between the existing `regression_then_success` branch and the terminal `else`. Log-summary block gained an `insufficient_logs` case emitting the `(log coverage insufficient)` suffix. Return-dict construction gained an `insufficient_logs` branch inserted BEFORE the regression branch — the returned dict exposes `instrumentation_targets: ["src/scaffold.py"]` per the contract Task 2 relies on. `success` and `regression` dicts unchanged; artifact write path unchanged (AD-6 applies to insufficient-log runs).
- **Task 2 (SupervisorAgent):** Extended `_execute_ticket`'s three-way branch to four-way — `insufficient_logs` inserted between `success` and `regression` per FR-19 (instrumentation happens BEFORE any fix attempt). Added `_handle_insufficient_logs_and_instrument` and `_escalate_diagnostic_logging` private methods immediately below `_execute_ticket` and above `_handle_regression_and_maybe_fix`. Instrumentation uses a shallow-copy `dict(story_details)` (Story 5.3 leakage guard). Developer error short-circuits without retest (AC-7). Retest uses ORIGINAL `story_details` (accumulated-context cleanliness). AC-5 success path lands on `In Review` (NOT `Done`) — the code-review gate stays authoritative for logging-only remediations. AC-6 regression fall-through delegates to Story 5.7 handler and merges `diagnostic_logging` key alongside `regression_fix`. AC-7 escalation publishes new `diagnostic_logging_escalation` SSE event (data-only addition — `publish_event` already accepts arbitrary event types).
- **Task 3 (main_agent.py):** Verified by inspection that `agents/main_agent.py` still uses its own inline flow (line 76 & 198 `await self.tester.write_and_run_tests(...)`) and does not call `SupervisorAgent._execute_ticket`. No changes required. Same conclusion as Story 5.7 Task 3.1.
- **Task 4 (Tests):** Extended `tests/test_tester_regression_signal.py` with six new tests (4.1.1–4.1.6) — no existing Story 5.7 tests were modified. Added `tests/test_supervisor_diagnostic_logging.py` with seven tests (4.2.1–4.2.7). Full suite: 105 passed. Audit of `tests/test_supervisor_test_artifact_gate.py`, `tests/test_supervisor_regression_fix.py`, `tests/test_supervisor_agent.py`, `tests/test_tester_agent_artifact.py`, `tests/test_project_store_test_artifact.py` confirmed no existing `write_and_run_tests` mock emits `insufficient_logs` — all continue to pass.
- **Task 5 (Docs & schema):** No markdown doc created (repo convention). No changes to `backend/store/migrations.py` (Agent Blocked already in circulation). `.env.example` untouched (test-only env values). `backend/api/sse.py` untouched. `agents/developer_agent.py` / `agents/local_developer_agent.py` untouched — instrumentation instruction reaches the LLM via the augmented `story_details["description"]`.
- **Invariants preserved:** Story 5.3 shallow-copy guard (verified by test 4.2.5). Story 5.6 `close_ticket_as_done` gate — NOT invoked on the AC-5 logging-only success path (deliberate divergence from Story 5.7). Story 5.7 `_handle_regression_and_maybe_fix` behavior — untouched; verified by test 4.2.7. AD-6 artifact gate — insufficient-log runs still write artifacts. FR-19 preservation invariant — instrumentation prompt explicitly instructs preservation, no cleanup step introduced.

### File List

- `agents/tester_agent.py` (modified — Task 1)
- `agents/supervisor_agent.py` (modified — Task 2)
- `tests/test_tester_regression_signal.py` (modified — Task 4.1: six new tests appended)
- `tests/test_supervisor_diagnostic_logging.py` (new — Task 4.2)
- `_bmad-output/implementation-artifacts/5-8-diagnostic-logging-before-escalation.md` (story file — status, checkboxes, dev record)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status transition ready-for-dev → review)

## Change Log

| Date       | Change                                                                                          |
| ---------- | ----------------------------------------------------------------------------------------------- |
| 2026-08-31 | Story 5.8 implemented: `insufficient_logs` tester signal + supervisor instrumentation handler.  |
| 2026-08-31 | New SSE event type `diagnostic_logging_escalation`; four new `TESTER_MOCK_MODE` values.         |
| 2026-08-31 | 13 new tests added (6 tester, 7 supervisor); 105/105 tests pass.                                |
