---
baseline_commit: HEAD
---

# Story 5.7: Autonomous Pre-Merge Regression Fix

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the agent team to detect regressions before merge and fix them autonomously without interrupting me,
so that only passing code reaches the branch — and I'm only pulled in when the agent genuinely cannot fix it (FR-18 / CAP-6 / Epic 5).

## Acceptance Criteria

1. **Given** `TesterAgent.write_and_run_tests` returns a result with `status == "regression"` (a new, well-defined signal that tests executed but at least one test failed — distinct from `"error"` which means the test runner itself failed and from `"success"` which means all tests passed)
   **When** `SupervisorAgent._execute_ticket` receives that result
   **Then** the supervisor MUST publish an SSE `agent_log` event of the form `{"message": "[Supervisor] Regression detected for ticket <id> — attempting autonomous fix."}` on the project channel, and MUST NOT publish any user-facing "notify me" event, and MUST NOT transition the ticket to `Error` or `Agent Blocked` at this point (the user is not interrupted per FR-18).

2. **And** the supervisor MUST delegate a fix attempt to the same developer sub-agent that implemented the ticket (respecting `AGENT_MODE` — `LocalDeveloperAgent` for `local`, `RemoteDeveloperAgent` for `remote`) by calling `implement_pr_recommendations(story_details, branch_name, workspace_path)` where `branch_name` is taken from the original `dev_result["branch"]` and `story_details["description"]` is augmented with a `"--- Regression report ---\n"` block containing the failing test file list and the failure summary from the tester's initial result. This preserves the existing branch (no new branch — the fix is committed to the SAME branch per Epic wording "the fix is committed and the full test suite re-runs before the merge proceeds").

3. **And** after a successful `implement_pr_recommendations` return, the supervisor MUST re-invoke `await self.tester.write_and_run_tests(story_details, dev_result.get("code_files", []), workspace_path)` exactly once (the test suite re-runs).

4. **Given** the autonomous fix's re-test returns `status == "success"`
   **When** the re-test completes
   **Then** the supervisor MUST publish `agent_log` `{"message": "[Supervisor] Autonomous fix succeeded for ticket <id> — proceeding to Done."}`, MUST call `await self.close_ticket_as_done(project_id, ticket_id)` (the Story 5.6 gated Done transition — enforces AD-6 / FR-17 by requiring the fresh test artifact just written), and MUST return `{"ticket_id": ticket_id, "status": "completed", "development": dev_result, "testing": retest_result, "regression_fix": {"attempted": True, "outcome": "success"}}` from `_execute_ticket`. The ticket ends in `Done`, no user intervention (FR-18 primary path).

5. **Given** the autonomous fix's re-test returns `status == "regression"` OR `status == "error"` (i.e. the fix did not resolve the failure after ONE attempt — per Epic wording "after one attempt")
   **When** the second test run fails
   **Then** the supervisor MUST publish a structured SSE event on channel `regression_escalation` with payload:
   ```json
   {
     "ticket_id": "<id>",
     "initial_failures": <the initial tester result's failures list or summary>,
     "attempted_fix_summary": <one-line summary from dev_result.get("message") or dev_result.get("pr_url")>,
     "retest_failures": <the retest tester result's failures list or summary>,
     "options": ["continue", "abandon"]
   }
   ```
   AND MUST also publish an `agent_log` event `{"message": "[Supervisor] Autonomous fix failed for ticket <id> — user input required. Options: continue / abandon."}` so users on the plain chat stream see the escalation, AND MUST call `await project_store.update_ticket_status(project_id, ticket_id, "Agent Blocked")` (the state machine value per the Consistency Conventions table in ARCHITECTURE-SPINE.md — `Pending → In Progress → Done | Error | Agent Blocked`), AND MUST return `{"ticket_id": ticket_id, "status": "blocked", "reason": "regression_unfixed", "initial_failures": ..., "retest_failures": ...}` from `_execute_ticket`. The ticket does NOT transition to `Error` (that state is reserved for infrastructure/system failures) and does NOT transition to `Done`.

6. **And** the autonomous fix is attempted AT MOST ONCE per ticket per execution — there is no configurable retry count, no infinite loop. This is the exact wording of the Epic ("after one attempt"). A regression counter on the ticket record is NOT introduced (JSONB churn without downstream consumer) — the single-attempt invariant is enforced by the linear structure of `_execute_ticket` (no loop around the fix path).

7. **And** `TesterAgent.write_and_run_tests` MUST expose the ability to return `status == "regression"` for tests to drive. Concretely: the tester reads the environment variable `TESTER_MOCK_MODE` at method-invocation time (`os.environ.get("TESTER_MOCK_MODE", "success")`). Values:
   - `"success"` (default): current behaviour — all tests pass, `status="success"`.
   - `"regression"`: emits `status="regression"` with a `failures=[{"test": "tests/test_scaffold.py::test_perform_action", "message": "AssertionError: mocked regression"}]` list AND still writes a real log artifact + calls `project_store.write_test_artifact` (the AD-6 gate applies to failed test runs too — an artifact of the failure is still verifiable evidence of execution). The `test_artifact_ref` in the returned dict remains a non-empty string.
   - `"regression_then_success"`: emits `regression` on the first invocation of a given `TesterAgent` instance, then `success` on all subsequent invocations. Enables the "autonomous fix succeeded" test path without patching. Tracked via a private counter attribute `self._invocation_count`.
   - Any other value: fall back to `"success"` (fail-open — mocked defensiveness).
   This env-var-driven mock is the ONLY new configuration knob and is DEFAULT-OFF (production behaviour is `"success"` — unchanged). Real pytest execution and real failure detection remain out of scope for this story (project-context.md testing rule: "TesterAgent currently generates scaffold tests only").

8. **And** the SSE `regression_escalation` event MUST use a NEW dedicated event type (not `agent_log`) so the frontend can route it to a dedicated escalation surface in a later story (Epic 6 / Story 6.x). The event type MUST be the exact string `"regression_escalation"`. The `publish_event` function signature is `publish_event(project_id, event_type, payload)` — no changes to the SSE plumbing required, only a new event type in circulation.

## Tasks / Subtasks

- [x] 1. Extend `TesterAgent` with a regression-signal mock (AC: 1, 7)
  - [x] 1.1 In `agents/tester_agent.py`, add an `__init__` body that sets `self._invocation_count = 0`. The class currently has `def __init__(self): pass` — replace with `def __init__(self) -> None: self._invocation_count = 0`.
  - [x] 1.2 At the top of `write_and_run_tests`, immediately after extracting `ticket_id`/`project_id`, read `mock_mode = os.environ.get("TESTER_MOCK_MODE", "success")` and increment `self._invocation_count += 1`. Compute `effective_mode`:
    - if `mock_mode == "regression"` → `effective_mode = "regression"`
    - elif `mock_mode == "regression_then_success"` and `self._invocation_count == 1` → `effective_mode = "regression"`
    - else → `effective_mode = "success"`
  - [x] 1.3 Keep the scaffold test-file generation loop and the log artifact write EXACTLY as-is. The log artifact must always be written (AD-6 applies to failed runs too — a failed pytest still produces a log, and the store gate should never see a missing artifact for a run-that-actually-happened).
  - [x] 1.4 Amend the log file contents: if `effective_mode == "regression"`, change the `summary` line to `f"pytest: {len(test_files) - 1} passed, 1 failed, 0 skipped"` (guard `max(0, len(test_files) - 1)` if `test_files` is empty). All other written lines are unchanged.
  - [x] 1.5 Always call `await project_store.write_test_artifact(project_id, ticket_id, artifact_ref)` when `project_id` is truthy — regardless of `effective_mode`. Do NOT skip the store write on regression: the artifact of a failed test IS the evidence AD-6 requires (per Story 5.6 dev notes, "Ghost validation is detectable at infrastructure level").
  - [x] 1.6 Build the return dict conditionally at the end of the method:
    - If `effective_mode == "success"`: return the EXISTING success dict verbatim — no field renames, no field removals, no reordering. Downstream tests (Story 5.6) assert exact keys.
    - If `effective_mode == "regression"`: return
      ```python
      {
          "status": "regression",
          "test_files": test_files,
          "coverage": "0%",
          "message": "1 test failed.",
          "failures": [
              {
                  "test": "tests/test_scaffold.py::test_perform_action",
                  "message": "AssertionError: mocked regression (TESTER_MOCK_MODE=regression)",
              }
          ],
          "test_artifact_ref": artifact_ref,
          "artifact_log_path": log_path,
      }
      ```
      The `failures` list is a NEW key introduced by this story. Its shape (`[{"test": str, "message": str}, ...]`) is the contract downstream consumers rely on — do NOT change it or bury it under a nested dict.
  - [x] 1.7 Do NOT alter the `status == "error"` path — that would be triggered when the test runner itself fails, which the mock never emits. Real pytest wiring is out of scope; leaving `error` unimplemented is intentional.

- [x] 2. Add the regression handler in `SupervisorAgent._execute_ticket` (AC: 1, 2, 3, 4, 5, 6, 8)
  - [x] 2.1 In `agents/supervisor_agent.py`, replace the current post-tester branch:
    ```python
    if test_result.get("status") != "success":
        await publish_event(project_id, "agent_log", {"message": ...})
        await project_store.update_ticket_status(project_id, ticket_id, "Error")
        return {"ticket_id": ticket_id, "status": "error", "reason": "testing_failed"}
    ```
    with a three-way branch on `test_result.get("status")`:
    - `"success"` → fall through to the existing `In Review` transition (unchanged for the first-pass-happy path — Story 5.6's "In Review is intentional per Story 5.2" invariant is preserved).
    - `"regression"` → call new `await self._handle_regression_and_maybe_fix(project_id, ticket_id, story_details, dev_result, workspace_path, test_result)` and return whatever it returns (its return dict shape is the AC-4 or AC-5 payload).
    - `"error"` or any other value → keep the CURRENT error branch verbatim (publish `agent_log`, set `Error`, return `{"status": "error", "reason": "testing_failed"}`). This preserves the Story 5.6 defensive guard.
    Order matters: check `"success"` first (branch prediction — this is the hot path), then `"regression"`, then fall-through to error.
  - [x] 2.2 Add a new private method `_handle_regression_and_maybe_fix` on `SupervisorAgent`, placed IMMEDIATELY BELOW `_execute_ticket` and ABOVE `_delegate_to_developer` (keeps orchestration methods grouped). Signature:
    ```python
    async def _handle_regression_and_maybe_fix(
        self,
        project_id: str,
        ticket_id: str,
        story_details: dict,
        dev_result: dict,
        workspace_path: str | None,
        initial_test_result: dict,
    ) -> dict:
    ```
  - [x] 2.3 First action in that method — publish AC-1's SSE event (do NOT notify the user yet):
    ```python
    await publish_event(project_id, "agent_log", {
        "message": f"[Supervisor] Regression detected for ticket {ticket_id} — attempting autonomous fix.",
    })
    ```
  - [x] 2.4 Build the regression report augmentation for the fix prompt:
    ```python
    failures = initial_test_result.get("failures") or []
    failure_lines = "\n".join(
        f"- {f.get('test', '?')}: {f.get('message', '')}"
        for f in failures
    ) or "- (no per-test detail available)"
    regression_block = (
        "--- Regression report ---\n"
        f"Ticket: {ticket_id}\n"
        f"Failing tests:\n{failure_lines}\n"
        f"Test artifact: {initial_test_result.get('test_artifact_ref', '')}\n"
        "-------------------------"
    )
    fix_story = dict(story_details)  # shallow copy — never mutate the caller's dict
    fix_story["description"] = f"{regression_block}\n\n{story_details.get('description', '')}"
    ```
    Rationale for the shallow copy: `story_details` is used later in the return payload of `_execute_ticket` and is also referenced by any subsequent accumulated-context builder (Story 5.3). Mutating it in place would leak the regression report into the persistent ticket description for future tickets — a Story-5.3 regression this story must not cause.
  - [x] 2.5 Delegate the fix — respect `AGENT_MODE`, use the ORIGINAL branch from `dev_result`:
    ```python
    branch_name = dev_result.get("branch") or f"feature/{ticket_id}"
    if self.mode == "local":
        fix_result = await self.local_developer.implement_pr_recommendations(
            fix_story, branch_name, workspace_path,
        )
    else:
        fix_result = await self.remote_developer.implement_pr_recommendations(
            fix_story, branch_name, workspace_path,
        )
    ```
    The fallback `f"feature/{ticket_id}"` matches `RemoteDeveloperAgent.implement_feature`'s convention (`branch_name = f"feature/{story_details.get('id', 'new-feature')}"`); the local agent's convention is `feature-local/…` but that path always populates `dev_result["branch"]` so the fallback is only defensive.
  - [x] 2.6 If `fix_result.get("status") != "success"` (the developer itself errored — e.g. Context7 grounding failure, MCP timeout), skip the retest entirely and escalate immediately as an AC-5 outcome:
    ```python
    await publish_event(project_id, "agent_log", {
        "message": f"[Supervisor] Autonomous fix attempt errored for ticket {ticket_id} — escalating.",
    })
    return await self._escalate_regression(
        project_id, ticket_id, initial_test_result,
        attempted_fix_summary=(fix_result.get("message") or fix_result.get("reason") or "fix attempt failed"),
        retest_result={"status": fix_result.get("status", "error"), "failures": []},
    )
    ```
    Rationale: no point re-running tests against unchanged code.
  - [x] 2.7 Otherwise re-run the tester ONCE (AC-3, AC-6):
    ```python
    await publish_event(project_id, "agent_log", {
        "message": f"[Supervisor] Fix committed for ticket {ticket_id} — re-running test suite.",
    })
    retest_result = await self.tester.write_and_run_tests(
        story_details, dev_result.get("code_files", []), workspace_path,
    )
    ```
    Pass the ORIGINAL `story_details` (not `fix_story`) to the retest — the regression report has no place in the test artifact context.
  - [x] 2.8 Branch on `retest_result.get("status")`:
    - `"success"` → AC-4 success path:
      ```python
      await publish_event(project_id, "agent_log", {
          "message": f"[Supervisor] Autonomous fix succeeded for ticket {ticket_id} — proceeding to Done.",
      })
      close_result = await self.close_ticket_as_done(project_id, ticket_id)
      # close_ticket_as_done handles both success and TestArtifactMissingError paths.
      if close_result.get("status") != "done":
          # AD-6 gate flipped — treat as escalation, do NOT report success upstream.
          return await self._escalate_regression(
              project_id, ticket_id, initial_test_result,
              attempted_fix_summary=(fix_result.get("message") or "fix attempt succeeded but Done gate refused"),
              retest_result=retest_result,
          )
      return {
          "ticket_id": ticket_id,
          "status": "completed",
          "development": dev_result,
          "testing": retest_result,
          "regression_fix": {"attempted": True, "outcome": "success"},
      }
      ```
    - Anything else (`"regression"`, `"error"`, or any other value) → AC-5 escalation:
      ```python
      return await self._escalate_regression(
          project_id, ticket_id, initial_test_result,
          attempted_fix_summary=(fix_result.get("message") or fix_result.get("pr_url") or "fix committed"),
          retest_result=retest_result,
      )
      ```
  - [x] 2.9 Add a helper `_escalate_regression` immediately after `_handle_regression_and_maybe_fix`:
    ```python
    async def _escalate_regression(
        self,
        project_id: str,
        ticket_id: str,
        initial_test_result: dict,
        attempted_fix_summary: str,
        retest_result: dict,
    ) -> dict:
        initial_failures = initial_test_result.get("failures") or []
        retest_failures = retest_result.get("failures") or []
        payload = {
            "ticket_id": ticket_id,
            "initial_failures": initial_failures,
            "attempted_fix_summary": attempted_fix_summary,
            "retest_failures": retest_failures,
            "options": ["continue", "abandon"],
        }
        await publish_event(project_id, "regression_escalation", payload)
        await publish_event(project_id, "agent_log", {
            "message": (
                f"[Supervisor] Autonomous fix failed for ticket {ticket_id} — "
                "user input required. Options: continue / abandon."
            ),
        })
        await project_store.update_ticket_status(project_id, ticket_id, "Agent Blocked")
        return {
            "ticket_id": ticket_id,
            "status": "blocked",
            "reason": "regression_unfixed",
            "initial_failures": initial_failures,
            "retest_failures": retest_failures,
        }
    ```
    Two events (`regression_escalation` + `agent_log`) are intentional: the structured event is for the future dedicated escalation UI; the log line keeps existing users on the plain chat stream informed. Both are required by AC-5 / AC-8.
  - [x] 2.10 Do NOT modify `close_ticket_as_done` (Story 5.6) — it is already correctly implemented and gates on the test artifact. Do NOT modify the existing `In Review` transition on the first-pass-success path — that behaviour is preserved (Story 5.2 / Story 5.6 invariant).

- [x] 3. `main_agent.py` — no regression handling on the CLI path (AC: 6, out of scope)
  - [x] 3.1 Confirm by inspection that `agents/main_agent.py` still uses its own inline flow (not `SupervisorAgent._execute_ticket`) and therefore is NOT impacted by this story. Document this in Dev Notes but change no code in `main_agent.py`. Rationale: the CLI path predates the backend store (Story 5.4 dev notes), cannot reach `close_ticket_as_done`, and is only used for smoke testing MCP connectivity per project-context.md.

- [x] 4. Tests (AC: 1–8)
  - [x] 4.1 Add `tests/test_tester_regression_signal.py`:
    - [x] 4.1.1 `test_tester_returns_success_when_env_unset`: unset `TESTER_MOCK_MODE`; assert `result["status"] == "success"` and NO `failures` key in the dict.
    - [x] 4.1.2 `test_tester_returns_regression_when_env_set` (monkeypatched `TESTER_MOCK_MODE=regression`): assert `result["status"] == "regression"`, `result["failures"]` is a non-empty list, each failure has `test` and `message` string keys, `result["test_artifact_ref"]` is a non-empty string, `result["artifact_log_path"]` exists on disk.
    - [x] 4.1.3 `test_tester_regression_still_writes_artifact` (`TESTER_MOCK_MODE=regression`, `project_id="proj-1"`): patch `backend.store.project_store.write_test_artifact` with `AsyncMock`; assert the patch was awaited exactly once with `(project_id, ticket_id, test_artifact_ref)` — the AD-6 gate applies to failed runs too.
    - [x] 4.1.4 `test_tester_regression_then_success_toggles` (`TESTER_MOCK_MODE=regression_then_success`, same `TesterAgent()` instance called twice): assert first call returns `status=="regression"`, second call returns `status=="success"`.
    - [x] 4.1.5 `test_tester_unknown_mode_defaults_to_success` (`TESTER_MOCK_MODE=garbage`): assert `status=="success"`.
    - [x] 4.1.6 `test_tester_regression_log_summary_reflects_failure`: with `TESTER_MOCK_MODE=regression`, run against a tmp workspace with `code_files=["a.py"]`; open the log file at `result["artifact_log_path"]`; assert its content contains `"1 failed"` and NOT `"0 failed"`.
    - Use `monkeypatch.setenv/delenv` for env manipulation (`monkeypatch` fixture is the pytest-preferred pattern — do NOT `os.environ[...] = ...` directly, which leaks across tests).
  - [x] 4.2 Add `tests/test_supervisor_regression_fix.py` — heavily mocked, no real MCP, no real store. Follow the fixture patterns already established in `tests/test_supervisor_test_artifact_gate.py`:
    - [x] 4.2.1 `test_regression_triggers_autonomous_fix_then_success`:
      - Patch `SupervisorAgent`'s `tester.write_and_run_tests` with an `AsyncMock` whose `side_effect` returns two values in sequence: first a regression dict (`status="regression"`, `failures=[{"test": "t", "message": "m"}]`, `test_artifact_ref="logs/x.log"`), then a success dict (`status="success"`, `test_artifact_ref="logs/y.log"`).
      - Patch `remote_developer.implement_pr_recommendations` with `AsyncMock(return_value={"status": "success", "branch": "feature/tkt-1", "message": "fixed"})`.
      - Patch `remote_developer.implement_feature` with `AsyncMock(return_value={"status": "success", "branch": "feature/tkt-1", "code_files": ["src/a.py"], "message": "ok"})`.
      - Patch `environment.prepare_environment` with a `MagicMock` (sync) returning `{"status": "success", "workspace_path": "/tmp/ws", "repo_full_name": "o/r"}`.
      - Patch `backend.store.project_store.get_project` with `AsyncMock` returning `{"ticket_history": [{"id": "tkt-1", "title": "T", "description": "D", "status": "In Progress"}]}`.
      - Patch `backend.store.project_store.mark_ticket_done` and `backend.store.project_store.update_ticket_status` with `AsyncMock`.
      - Patch `backend.api.sse.publish_event` with `AsyncMock`.
      - Call `await supervisor._execute_ticket("proj-1", "tkt-1", ["tkt-1"])`.
      - Assert return dict has `status="completed"` AND `regression_fix == {"attempted": True, "outcome": "success"}`.
      - Assert `implement_pr_recommendations` was awaited exactly once with the ORIGINAL branch `"feature/tkt-1"` and a `story_details` whose `description` contains `"--- Regression report ---"`.
      - Assert `tester.write_and_run_tests` was awaited exactly twice.
      - Assert `mark_ticket_done` was awaited exactly once with `("proj-1", "tkt-1")`.
      - Assert NO `regression_escalation` event was published (`assert_not_called` on filtered awaits).
      - Assert the "In Review" `update_ticket_status` was NOT called on the happy autonomous-fix path (the Story 5.6 In-Review-only-on-first-pass invariant).
    - [x] 4.2.2 `test_regression_fix_fails_escalates_to_agent_blocked`:
      - Same patches as 4.2.1 but the tester's second call also returns `status="regression"` (fix did not resolve).
      - Assert return dict is `{"ticket_id": "tkt-1", "status": "blocked", "reason": "regression_unfixed", ...}` with `initial_failures` and `retest_failures` populated.
      - Assert `publish_event` was awaited with `("proj-1", "regression_escalation", <payload>)` where payload has keys `ticket_id`, `initial_failures`, `attempted_fix_summary`, `retest_failures`, `options == ["continue", "abandon"]`.
      - Assert `update_ticket_status` was awaited with `("proj-1", "tkt-1", "Agent Blocked")` — NOT `"Error"` (AC-5).
      - Assert `mark_ticket_done` was NOT called (`close_ticket_as_done` is not invoked on the escalation path).
    - [x] 4.2.3 `test_regression_fix_developer_error_escalates_without_retest`:
      - Tester's first call returns regression. `implement_pr_recommendations` returns `{"status": "error", "reason": "context7_grounding_failed", "message": "boom"}`.
      - Assert `tester.write_and_run_tests` was awaited exactly ONCE (no retest — AC-2.6 short-circuit).
      - Assert the return dict is a `status="blocked"` escalation with `attempted_fix_summary` containing `"boom"` (or `"context7_grounding_failed"` — whichever the code chose; assert on the shorter fallback string `"boom"` since the code prefers `.message` first).
      - Assert `update_ticket_status` was awaited with `("proj-1", "tkt-1", "Agent Blocked")`.
    - [x] 4.2.4 `test_regression_report_is_shallow_copied_not_mutated`:
      - Store the original `story_details["description"]` value the supervisor computed (patch the developer's `implement_feature` to capture the `story_details` arg it received and store it in a `list` for later assert).
      - Then, verify that when `implement_pr_recommendations` is later called, the ORIGINAL `story_details` object referenced by `_execute_ticket`'s locals has NOT been mutated — its description does NOT contain `"--- Regression report ---"`. The regression report appears ONLY in the `story_details` arg passed to `implement_pr_recommendations`.
      - This is a Story 5.3 regression guard — if `_execute_ticket` mutates its own `story_details["description"]`, the accumulated context builder for the next ticket will leak the regression report.
    - [x] 4.2.5 `test_close_ticket_as_done_refusal_falls_back_to_escalation`:
      - Tester returns regression then success. `implement_pr_recommendations` returns success. Patch `supervisor.close_ticket_as_done` with `AsyncMock(return_value={"ticket_id": "tkt-1", "status": "error", "reason": "test_artifact_missing"})` — simulating the AD-6 gate refusing the Done transition.
      - Assert the final return dict is a `status="blocked"` escalation (NOT `status="completed"`) — the supervisor MUST NOT report success when the gate refused.
      - Assert `regression_escalation` was published.
    - [x] 4.2.6 `test_first_pass_success_does_not_invoke_regression_handler`:
      - Tester returns success on the first (and only) call.
      - Assert `implement_pr_recommendations` was NEVER awaited.
      - Assert `update_ticket_status` was awaited with `"In Review"` (the Story 5.6 first-pass invariant is preserved).
      - Assert NO `regression_escalation` event was published.
  - [x] 4.3 Regression run: `python -m pytest tests/ -q` MUST show all previously-passing tests still passing. Any test that patches `tester.write_and_run_tests` with a mock returning `{"status": "success", ...}` must continue to pass unchanged — the regression handler only activates on `"regression"`.
  - [x] 4.4 Audit `tests/test_supervisor_agent.py` and `tests/test_supervisor_test_artifact_gate.py` for any test that relies on the Story 5.6 error branch shape (`{"status": "error", "reason": "testing_failed"}`). That branch is preserved verbatim for `status="error"`, so those tests should continue to pass. Document in Dev Notes that you verified this by reading each `write_and_run_tests` mock in those files.

- [x] 5. Documentation & schema notes
  - [x] 5.1 Do NOT create a new markdown doc for this story unless the user asks — per repo convention.
  - [x] 5.2 Do NOT modify `backend/store/migrations.py` — no new column is required. `"Agent Blocked"` is already covered by the state machine (Consistency Conventions in ARCHITECTURE-SPINE.md); no enum/CHECK constraint change is needed because `ticket.status` is a string inside JSONB.
  - [x] 5.3 Do NOT touch `.env.example`. `TESTER_MOCK_MODE` is a test-only knob with a safe default (`"success"`). Documenting it in `.env.example` would risk users setting it in real deployments.
  - [x] 5.4 Do NOT alter `backend/api/sse.py` or add a new endpoint. `publish_event` already accepts arbitrary event types (verified by inspection); the new `"regression_escalation"` event type is a data-only addition.

## Dev Notes

### What Stories 5.1–5.6 Built (Must Not Break)

- **Story 5.1** — `execution_lock.py` and FastAPI lifespan init. The regression handler runs INSIDE the existing sequential lock (it is invoked from `_execute_ticket`, which is already lock-scoped). No lock code changes. AD-2 remains intact.
- **Story 5.2** — `SupervisorAgent._execute_ticket` sets ticket status `"In Review"` after tests pass. Story 5.7 preserves that transition on the first-pass-success path. The `In Review` gate is only bypassed when an autonomous fix succeeded — in that case the ticket goes directly to `Done` via `close_ticket_as_done`, matching Epic wording ("the merge proceeds and the ticket transitions to Done").
- **Story 5.3** — `_build_accumulated_context` reads `ticket_history[].description` when building context for subsequent tickets. This story appends a regression report to `story_details["description"]` in a SHALLOW COPY (`dict(story_details)`) — the original dict passed into `_execute_ticket` is NOT mutated. This is the critical guard that keeps the accumulated-context builder clean for later tickets. If you mutate the caller's dict, the regression report will leak into every subsequent ticket's prompt.
- **Story 5.4** — `chat_history` and `agent_memory` JSONB round-tripping. Story 5.7 does not touch either. The new `Agent Blocked` state lives on the ticket record (existing JSONB field `ticket_history[].status`) — no new column, no round-trip change.
- **Story 5.5** — `context7_grounding.py` runs BEFORE code generation in both developer agents. `implement_pr_recommendations` calls `ground_with_context7` at its top (verified in `agents/developer_agent.py` line ~95 and `agents/local_developer_agent.py` line ~118). If grounding fails during the autonomous fix, the developer returns `{"status": "error", "reason": "context7_grounding_failed"}` — Task 2.6 catches this and escalates immediately without a retest. AD-8 is preserved.
- **Story 5.6** — `close_ticket_as_done` is the AD-6-gated Done transition. Story 5.6 explicitly deferred wiring it into `_execute_ticket` to a later story ("belongs to Story 5.7 (autonomous regression fix) or a later code-review-completion story"). This story wires it into the autonomous-fix-success path ONLY. The first-pass-success path remains at `In Review` (human/code-review still owns that gate).

### Architecture Compliance

- **AD-1 (agent hierarchy):** All fix delegation goes through `SupervisorAgent`. Sub-agents remain unaware of each other. `_handle_regression_and_maybe_fix` calls `self.local_developer` or `self.remote_developer` — the same routing pattern as `_delegate_to_developer`. No new peer visibility introduced.
- **AD-2 (sequential lock):** Retest and fix happen inside the same `_execute_ticket` call, which runs under the existing sequential lock. No parallel work.
- **AD-3 (MCPManager singleton):** Developer agents that get re-invoked reuse the singleton via their existing `load_dev_tools()` / `load_context7_mcp_tools()` context managers. No ad-hoc MCP instantiation.
- **AD-4 (LLM-as-last-resort):** The regression detection itself uses NO LLM. The mocked `TesterAgent` returns a hard-coded regression signal. Only the fix step (already-LLM-driven `implement_pr_recommendations`) invokes the LLM. The escalation path invokes NO LLM — it publishes structured SSE and updates the ticket status directly.
- **AD-5 (project isolation):** All operations are scoped by `project_id`. No cross-project reads.
- **AD-6 (test artifact gate):** The regression path STILL writes a test artifact (Task 1.5) — failed runs are also verifiable evidence. `close_ticket_as_done` on the success path enforces the gate via the fresh (successful) artifact. If the gate refuses (Task 4.2.5 scenario — an implementation bug elsewhere), the code falls through to escalation rather than pretending to succeed.
- **AD-7 (streaming over polling):** The regression escalation is a structured SSE event (`regression_escalation`), published as it happens. No batched delivery, no polling.
- **AD-8 (Context7 grounding):** Grounding runs inside `implement_pr_recommendations` (existing behaviour). No change.
- **AD-9 (async throughout):** Every new method (`_handle_regression_and_maybe_fix`, `_escalate_regression`) is `async def`. All calls use `await`. The tester method is already async (Story 5.6).
- **AD-13 (env vars only):** `TESTER_MOCK_MODE` reads via `os.environ.get("TESTER_MOCK_MODE", "success")` at method-invocation time (NOT at import time — see below). No hardcoded fallbacks.
- **project-context.md — env vars read at entry point:** `TESTER_MOCK_MODE` is read at method-invocation time (not once at module import) so tests using `monkeypatch.setenv` can change the value between calls. This is the SAME pattern used by `SupervisorAgent.__init__` for `AGENT_MODE` (except that one is per-instance; this one is per-invocation because tests need to flip it between the two calls inside a single `_execute_ticket` run for `regression_then_success`).
- **Ticket state machine (Consistency Conventions):** `Pending → In Progress → Done | Error | Agent Blocked`. The regression-escalation path uses `Agent Blocked` (not `Error`). `Error` is reserved for infrastructure/system failures (Story 5.6 semantics). This is the FIRST use of `Agent Blocked` in the codebase — confirmed by grepping for `"Agent Blocked"` and finding no prior occurrences.

### Files Being Modified — Current State and Change Scope

**`agents/tester_agent.py`** (current state: ~75 lines, async, mock scaffold, always returns `status="success"`; Story 5.6)
- Current: `write_and_run_tests` always returns `status="success"` with `test_files`, `coverage="100%"`, `message`, `test_artifact_ref`, `artifact_log_path`.
- Change: `__init__` now sets `self._invocation_count = 0`. `write_and_run_tests` reads `TESTER_MOCK_MODE` env var at invocation, increments a per-instance counter, and can return `status="regression"` with a `failures` list. Log artifact write and store write are unconditional (still happen on regression — AD-6 applies to failed runs).
- Must preserve: the exact success-path return dict shape (Story 5.6 tests assert on the keys). The scaffold-file generation. Both `print` statements (CLI visibility). Forward-slash normalisation of `artifact_ref`. The `project_id` truthy guard around `write_test_artifact` (CLI escape hatch, Story 5.6 AC-1).

**`agents/supervisor_agent.py`** (current state: ~340 lines including `close_ticket_as_done`; Stories 5.1–5.6)
- Current: `_execute_ticket` has a binary `test_result.status != "success"` branch that always sets `Error` and returns `reason="testing_failed"`. `close_ticket_as_done` exists but is not invoked from `_execute_ticket`.
- Change: replace the binary branch with a three-way branch (success / regression / error). Add `_handle_regression_and_maybe_fix` and `_escalate_regression` private methods. Invoke `close_ticket_as_done` on the autonomous-fix-success path only. Add ONE new SSE event type (`regression_escalation`) — data-only, no plumbing change.
- Must preserve: the entire `_execute_ticket` shape up to and including the tester call. The `In Review` transition on first-pass success. `close_ticket_as_done` itself (do NOT touch — Story 5.6 tests assert on it). The `_delegate_to_developer` routing. `_build_accumulated_context` (Story 5.3). The environment failure branch. The developer failure branch. The `error` fallback branch.

**`agents/main_agent.py`** — NOT modified. Verified in Task 3.1 that the CLI path does not use `SupervisorAgent._execute_ticket`.

**`agents/developer_agent.py` / `agents/local_developer_agent.py`** — NOT modified. `implement_pr_recommendations` already exists on both with the exact signature `(story_details, branch_name, workspace_path) -> dict` returning `{"status": ..., "branch": ..., "message": ...}`. Verified by inspection of both files.

**`backend/store/project_store.py`** — NOT modified. `update_ticket_status` accepts arbitrary status strings (it writes into a JSONB field with no CHECK constraint on the value). `mark_ticket_done` (Story 5.6) is invoked via `close_ticket_as_done` — untouched.

**`backend/api/sse.py`** — NOT modified. `publish_event(project_id, event_type, payload)` already accepts arbitrary event types.

**NEW files:**
- `tests/test_tester_regression_signal.py`
- `tests/test_supervisor_regression_fix.py`

**DO NOT modify:**
- `backend/store/errors.py`, `backend/store/database.py`, `backend/store/migrations.py`
- `backend/api/routes/execute.py`
- `backend/execution_lock.py`
- `agents/environment_agent.py`, `agents/context7_grounding.py`
- Story 5.5 grounding tests, Story 5.6 gate tests

### Windows / Path Notes

- No new path operations introduced. The tester log-write in Story 5.6 already handled `os.sep` normalisation; the regression path reuses the same code.
- All new file writes are inside existing `os.makedirs(exist_ok=True)`-scoped directories.

### Reference Implementation Sketch (non-normative)

Supervisor three-way branch:
```python
tester_status = test_result.get("status")
if tester_status == "success":
    await project_store.update_ticket_status(project_id, ticket_id, "In Review")
    await publish_event(project_id, "agent_log", {
        "message": f"[Supervisor] Ticket {ticket_id} complete — status set to 'In Review'.",
    })
    return {"ticket_id": ticket_id, "status": "completed", "development": dev_result, "testing": test_result}
elif tester_status == "regression":
    return await self._handle_regression_and_maybe_fix(
        project_id, ticket_id, story_details, dev_result, workspace_path, test_result,
    )
else:
    await publish_event(project_id, "agent_log", {
        "message": f"[Supervisor] Testing phase failed for ticket {ticket_id}.",
    })
    await project_store.update_ticket_status(project_id, ticket_id, "Error")
    return {"ticket_id": ticket_id, "status": "error", "reason": "testing_failed"}
```

Tester regression mock (skeleton):
```python
mock_mode = os.environ.get("TESTER_MOCK_MODE", "success")
self._invocation_count += 1
if mock_mode == "regression":
    effective_mode = "regression"
elif mock_mode == "regression_then_success" and self._invocation_count == 1:
    effective_mode = "regression"
else:
    effective_mode = "success"
# … scaffold + artifact write (unchanged; summary line adapts on regression) …
if effective_mode == "regression":
    return {
        "status": "regression",
        "test_files": test_files,
        "coverage": "0%",
        "message": "1 test failed.",
        "failures": [{"test": "tests/test_scaffold.py::test_perform_action",
                      "message": "AssertionError: mocked regression (TESTER_MOCK_MODE=regression)"}],
        "test_artifact_ref": artifact_ref,
        "artifact_log_path": log_path,
    }
return {
    "status": "success",
    "test_files": test_files,
    "coverage": "100%",
    "message": "All unit tests passed.",
    "test_artifact_ref": artifact_ref,
    "artifact_log_path": log_path,
}
```

### Project Structure Notes

- All new code lives in existing modules (`agents/tester_agent.py`, `agents/supervisor_agent.py`). No new package or subdirectory introduced. Aligned with the one-concept-per-file convention.
- New tests live under `tests/` with the `test_*.py` prefix (project-context.md testing rule). Names describe the behaviour under test (`test_tester_regression_signal.py`, `test_supervisor_regression_fix.py`) rather than the implementation file — consistent with `test_supervisor_test_artifact_gate.py` naming.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.7: Autonomous Pre-Merge Regression Fix]
- [Source: _bmad-output/planning-artifacts/epics.md#FR-18] — Autonomous Pre-Merge Regression Handling
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md#AD-1] — Strict agent hierarchy
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md#AD-2] — Global sequential execution lock
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md#AD-6] — Test artifact gate (no ghost validation)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md#AD-7] — Streaming over polling
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ai-consultant-2026-07-08/ARCHITECTURE-SPINE.md#Consistency Conventions] — Ticket state machine `Pending → In Progress → Done | Error | Agent Blocked`
- [Source: _bmad-output/project-context.md#Architecture Rules] — agent hierarchy, async rules, env-var rule
- [Source: _bmad-output/project-context.md#Testing Rules] — TesterAgent scaffold-only current state
- [Source: agents/supervisor_agent.py] — current `_execute_ticket` flow, existing `close_ticket_as_done`, existing `_delegate_to_developer` routing
- [Source: agents/tester_agent.py] — current async scaffold implementation with artifact write (Story 5.6)
- [Source: agents/developer_agent.py] — `RemoteDeveloperAgent.implement_pr_recommendations` (existing method, invoked on remote fix path)
- [Source: agents/local_developer_agent.py] — `LocalDeveloperAgent.implement_pr_recommendations` (existing method, invoked on local fix path)
- [Source: _bmad-output/implementation-artifacts/5-6-mandatory-test-artifact-gate.md] — Story 5.6 gate contract, `close_ticket_as_done`, "belongs to Story 5.7" wiring note
- [Source: _bmad-output/implementation-artifacts/5-3-cross-ticket-accumulated-context.md] — Story 5.3 accumulated-context builder (shallow-copy invariant this story preserves)
- [Source: _bmad-output/implementation-artifacts/5-2-supervisoragent-wired-to-backend-and-project-store.md] — Story 5.2 `In Review` transition (preserved on first-pass-success path)
- [Source: backend/store/project_store.py] — `update_ticket_status`, `mark_ticket_done`, `write_test_artifact` (all pre-existing)
- [Source: backend/api/sse.py] — `publish_event(project_id, event_type, payload)` signature

## Dev Agent Record

### Agent Model Used

GitHub Copilot (Claude Opus 4.7)

### Debug Log References

- `python -m pytest tests/test_tester_regression_signal.py tests/test_supervisor_regression_fix.py -q` → 12 passed
- `python -m pytest tests/ -q` → 92 passed (full regression, no failures)

### Completion Notes List

- Task 1 (TesterAgent regression mock): `__init__` now sets `self._invocation_count = 0`. `write_and_run_tests` reads `TESTER_MOCK_MODE` at invocation time (per project-context env-var rule), increments the counter, and computes `effective_mode` ∈ {`success`, `regression`}. Unknown values fail-open to `success` (AC-7). The log artifact is always written and `project_store.write_test_artifact` is always awaited when `project_id` is truthy — regression path included, per AD-6 ("failed run is still verifiable evidence"). Success-path return dict shape is byte-identical to Story 5.6 (Story 5.6 tests still pass). Regression-path adds `failures` list (new key) with the contract `[{"test": str, "message": str}, ...]`.
- Task 2 (SupervisorAgent regression handler): The old binary `test_result.status != "success"` branch was replaced with a three-way branch (`success` / `regression` / else). Two new async private methods added: `_handle_regression_and_maybe_fix` (build regression report on a shallow copy of `story_details`, delegate to same-mode developer via `implement_pr_recommendations`, short-circuit escalate on developer error, retest once, close as Done on success, escalate on any other retest outcome) and `_escalate_regression` (publishes structured `regression_escalation` SSE event + human-readable `agent_log`, flips ticket to `Agent Blocked`, returns `{"status": "blocked", "reason": "regression_unfixed", ...}`). `close_ticket_as_done` (Story 5.6) is unchanged; it is now invoked on the autonomous-fix-success path only. The `In Review` transition on first-pass success is preserved verbatim (Story 5.2 / 5.6 invariant). No new dependencies, no SSE plumbing changes, no migrations, no `.env.example` edits.
- Task 3 (main_agent.py out of scope): Confirmed by inspection — `agents/main_agent.py` defines its OWN `SupervisorAgent` class (legacy CLI orchestrator) at line 22 which does not inherit from or call `agents.supervisor_agent.SupervisorAgent._execute_ticket`. No code change. Grep for `_execute_ticket` in `agents/main_agent.py` returned zero hits.
- Task 4 (Tests): Added `tests/test_tester_regression_signal.py` (6 tests, all AC-7 branches covered including `regression_then_success` toggle, log-summary content check, AD-6 store-write guard). Added `tests/test_supervisor_regression_fix.py` (6 tests covering happy autonomous-fix-then-success, escalation on retest failure, developer-error short-circuit escalation without retest, shallow-copy invariant (Story 5.3 guard), `close_ticket_as_done` refusal falling back to escalation, and first-pass-success bypassing the regression handler). All 12 new tests pass. Full suite passes at 92/92 with no regressions.
- Task 4.4 (audit): Read the tester mocks in `tests/test_supervisor_agent.py` (line 47 `FAKE_TEST_RESULT = {"status": "success", ...}`) and `tests/test_supervisor_test_artifact_gate.py` (line 91–96 and line 127). Both return `status="success"` or `status="error"` — neither hits the new `"regression"` branch, so the pre-existing gate/happy-path assertions are unaffected. The `status="error"` branch in `_execute_ticket` is preserved verbatim, so `test_execute_ticket_marks_error_when_testing_failed` continues to pass.
- Task 5 (documentation & schema): No new markdown docs, no `migrations.py` change, no `.env.example` change, no `backend/api/sse.py` change. All confirmed by inspection of the acceptance criteria.
- **Architecture compliance:** AD-1 preserved (sub-agent routing via SupervisorAgent only). AD-2 preserved (retest + fix run inside the existing `_execute_ticket` sequential lock). AD-6 preserved (regression path still writes real log + calls `write_test_artifact`; success-path Done transition still goes through `close_ticket_as_done`). AD-7 preserved (structured `regression_escalation` SSE emitted as it happens). AD-9 preserved (both new methods `async def`, all sub-agent calls `await`ed). AD-13 preserved (`TESTER_MOCK_MODE` read from `os.environ.get` at invocation time). The `Agent Blocked` string is used for the first time in the codebase (grep confirmed zero prior occurrences) — this matches the architecture-spine state-machine table.
- **Windows notes:** No new path operations. All new file writes are inside directories already scoped by `os.makedirs(exist_ok=True)`.

### File List

- Modified: `agents/tester_agent.py`
- Modified: `agents/supervisor_agent.py`
- Modified: `_bmad-output/implementation-artifacts/sprint-status.yaml`
- Added: `tests/test_tester_regression_signal.py`
- Added: `tests/test_supervisor_regression_fix.py`

### Change Log

| Date       | Change                                                                                                                    |
| ---------- | ------------------------------------------------------------------------------------------------------------------------- |
| 2026-08-31 | `TesterAgent` gains `TESTER_MOCK_MODE` regression mock (`success` / `regression` / `regression_then_success`); default off. |
| 2026-08-31 | `SupervisorAgent._execute_ticket` grows a three-way tester-status branch; autonomous fix + retest + escalation added.      |
| 2026-08-31 | New SSE event type `regression_escalation` (data-only; no plumbing change).                                                |
| 2026-08-31 | Ticket state machine gains first use of `Agent Blocked` (for unfixed regressions; `Error` still reserved for infra).        |
| 2026-08-31 | Two new test modules cover AC-1 through AC-8; full suite passes at 92/92.                                                 |
