"""
VerifyAgent Test (Phase 4)
Verifies the real verification machinery WITHOUT any external service
(no LLM, Jira, GitHub or Docker). `run_pytest` is a pure function, so it can be
exercised against temporary workspaces:

1. Passing tests in a temp workspace -> returncode 0, counts parsed.
2. Failing tests -> non-zero returncode, failure count parsed.
3. No tests at all -> pytest exit code 5 ("no tests ran").
4. Hanging test suite -> timeout reported (returncode None).
5. The compiled SDD graph wires `verify` as a conditional node (finish or END).

Run directly:  python test_verify_agent.py
Or via pytest: pytest test_verify_agent.py
"""
import os
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agents.verify_agent import run_pytest, _find_test_files  # noqa: E402


def _make_workspace(test_code: str = None, module_code: str = "def add(a, b):\n    return a + b\n") -> str:
    root = tempfile.mkdtemp(prefix="verify-agent-test-")
    (Path(root) / "calc.py").write_text(module_code)
    if test_code is not None:
        tests_dir = Path(root) / "tests"
        tests_dir.mkdir()
        (tests_dir / "__init__.py").write_text("")
        (tests_dir / "test_calc.py").write_text(test_code)
    return root


def scenario_pytest_pass():
    root = _make_workspace("from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    try:
        result = run_pytest(root)
        assert result["ran"] is True
        assert result["returncode"] == 0, f"expected rc=0, got {result['returncode']}: {result['output_tail'][-500:]}"
        assert result["passed"] >= 1, f"expected at least 1 passed, got {result['passed']}"
        assert "passed" in result["summary"], f"unexpected summary: {result['summary']}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def scenario_pytest_fail():
    root = _make_workspace("from calc import add\n\n\ndef test_add_wrong():\n    assert add(1, 2) == 4\n")
    try:
        result = run_pytest(root)
        assert result["returncode"] != 0, f"expected non-zero rc, got {result['returncode']}"
        assert result["failed"] >= 1, f"expected at least 1 failed, got {result['failed']}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def scenario_no_tests():
    root = _make_workspace(test_code=None)
    try:
        result = run_pytest(root)
        assert result["returncode"] == 5, f"expected pytest exit code 5 (no tests), got {result['returncode']}"
        assert result["summary"] == "no tests ran", f"unexpected summary: {result['summary']}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def scenario_timeout():
    root = _make_workspace("import time\n\n\ndef test_slow():\n    time.sleep(10)\n")
    try:
        result = run_pytest(root, timeout=2)
        assert result["returncode"] is None, f"expected timed-out run (rc=None), got {result['returncode']}"
        assert "timed out" in result["summary"], f"unexpected summary: {result['summary']}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def scenario_test_file_discovery():
    root = _make_workspace("from calc import add\n")
    try:
        # A test file outside tests/ must also be discovered; .git is skipped.
        (Path(root) / "test_root_level.py").write_text("def test_x():\n    assert True\n")
        git_dir = Path(root) / ".git"
        git_dir.mkdir(exist_ok=True)
        (git_dir / "test_hidden.py").write_text("def test_y():\n    assert True\n")

        files = _find_test_files(root)
        assert "tests/test_calc.py" in files, f"missing tests/test_calc.py in {files}"
        assert "test_root_level.py" in files, f"missing root-level test in {files}"
        assert not any(".git" in f for f in files), f".git contents leaked: {files}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def scenario_graph_wiring():
    """The compiled SDD graph must keep `verify` as a conditional node:
    the real route_after_verify closure (compiled into the node's writers)
    must send failures to END and successes to finish. Requires GEMINI_API_KEY
    because building the real graph instantiates all agents."""
    from langgraph.graph import END
    from langgraph._internal._runnable import RunnableCallable
    from core.graph import build_sdd_graph
    from core.state import STATUS_FAILED, STATUS_VERIFYING

    graph = build_sdd_graph()
    nodes = graph.nodes
    assert {"verify", "finish"} <= set(nodes.keys()), f"missing verify/finish nodes: {sorted(nodes)}"

    def branch_route(node):
        # A conditional edge compiles into an extra RunnableCallable writer. Its
        # .func is BranchSpec._route; the actual routing closure lives at
        # BranchSpec.path.func (ChannelWrite writers are not branches).
        for writer in node.writers:
            if type(writer) is RunnableCallable:
                spec = getattr(writer.func, "__self__", None)
                path_func = getattr(getattr(spec, "path", None), "func", None)
                if callable(path_func):
                    return path_func
        raise AssertionError("verify node has no conditional branch writer — routing to finish/END is lost")

    route_after_verify = branch_route(nodes["verify"])
    assert route_after_verify({"status": STATUS_FAILED}) == END, "failed verification must stop the pipeline"
    assert route_after_verify({"status": STATUS_VERIFYING}) == "finish", "passed verification must open the PR"


def test_pytest_pass():
    scenario_pytest_pass()


def test_pytest_fail():
    scenario_pytest_fail()


def test_no_tests():
    scenario_no_tests()


def test_timeout():
    scenario_timeout()


def test_test_file_discovery():
    scenario_test_file_discovery()


def test_graph_wiring():
    scenario_graph_wiring()


def main():
    print("Running VerifyAgent tests (no external services)...\n")
    scenario_pytest_pass()
    print("[PASS] passing suite -> rc=0, counts parsed")
    scenario_pytest_fail()
    print("[PASS] failing suite -> non-zero rc, failure count parsed")
    scenario_no_tests()
    print("[PASS] empty workspace -> 'no tests ran' (exit code 5)")
    scenario_timeout()
    print("[PASS] hanging suite -> timeout reported")
    scenario_test_file_discovery()
    print("[PASS] test file discovery (tests/, root level, .git skipped)")
    scenario_graph_wiring()
    print("[PASS] SDD graph: verify is a conditional node (finish | END)")
    print("\n[SUCCESS] All VerifyAgent tests passed.")


if __name__ == "__main__":
    main()
