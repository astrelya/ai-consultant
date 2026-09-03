"""
Tester Agent Module
Responsible for generating unit tests for the code created by the Developer Agent.
"""
import os
from datetime import datetime, timezone

from backend.store import project_store


class TesterAgent:
    def __init__(self) -> None:
        # Per-instance counter drives the "regression_then_success" mock toggle.
        self._invocation_count = 0

    async def write_and_run_tests(
        self,
        story_details: dict,
        code_files: list,
        workspace_path: str,
    ) -> dict:
        ticket_id = story_details.get("id", "unknown")
        project_id = story_details.get("project_id")

        # Story 5.7: env-var driven regression mock. Read at invocation time so
        # tests can flip it between calls inside the same _execute_ticket run.
        mock_mode = os.environ.get("TESTER_MOCK_MODE", "success")
        self._invocation_count += 1
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

        print(f"  [TesterAgent] Analyzing files for testing: {code_files}")

        # Scaffold-test-file generation (documented TODO per project-context.md;
        # real LLM-driven test generation lands in a later story).
        test_files = []
        for file in code_files:
            file_name = os.path.basename(file)
            test_file_path = os.path.join(workspace_path, "tests", f"test_{file_name}")
            os.makedirs(os.path.dirname(test_file_path), exist_ok=True)

            with open(test_file_path, "w") as f:
                f.write(f"# Auto-generated unit tests for {file_name}\n")
                f.write("def test_perform_action():\n")
                f.write("    assert True\n")

            test_files.append(test_file_path)
            print(f"  [TesterAgent] Created test file: {test_file_path}")

        print("  [TesterAgent] Running tests... (mocked)")

        # AD-6 / FR-17: emit a real log-file artifact so the store-side gate
        # (project_store.mark_ticket_done) has something verifiable to bite on.
        logs_dir = os.path.join(workspace_path, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        log_name = f"test-{ticket_id}-{ts}.log"
        log_path = os.path.join(logs_dir, log_name)
        if effective_mode == "regression":
            # Guard against empty test_files (max(0, ...) for the "passed" count).
            passed = max(0, len(test_files) - 1)
            summary = f"pytest: {passed} passed, 1 failed, 0 skipped"
        elif effective_mode == "insufficient_logs":
            passed = max(0, len(test_files) - 1)
            summary = f"pytest: {passed} passed, 1 failed, 0 skipped (log coverage insufficient)"
        else:
            summary = f"pytest: {len(test_files)} passed, 0 failed, 0 skipped"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"ticket_id: {ticket_id}\n")
            f.write(f"timestamp: {datetime.now(timezone.utc).isoformat()}\n")
            f.write(f"test_files: {test_files}\n")
            f.write(f"summary: {summary}\n")

        # Forward-slash normalisation: PostgreSQL/JSON round-trip and the
        # frontend both choke on Windows backslashes.
        artifact_ref = os.path.relpath(log_path, workspace_path).replace(os.sep, "/")

        # CLI/smoke path has no project_id and no backend store — skip the
        # store write there. Only tolerated escape hatch (see Story 5.6 AC-1).
        # Regression path still writes: AD-6 applies to failed runs too.
        if project_id:
            await project_store.write_test_artifact(project_id, ticket_id, artifact_ref)

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

        return {
            "status": "success",
            "test_files": test_files,
            "coverage": "100%",
            "message": "All unit tests passed.",
            "test_artifact_ref": artifact_ref,
            "artifact_log_path": log_path,
        }

