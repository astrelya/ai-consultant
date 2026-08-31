"""
Verify Agent Module (Phase 4)
Replaces the old TesterAgent stub with real verification:

1. Syncs the workspace clone to the feature branch (fetch + checkout + pull),
   so verification always runs against the code the developer agents pushed.
2. Generates real, executable pytest tests from the approved spec's
   acceptance criteria (ReAct agent with local file tools + Context7 docs).
3. Commits and pushes the generated tests to the feature branch.
4. Executes pytest inside the isolated workspace.
5. Produces a spec-compliance report (markdown) comparing the results against
   the acceptance criteria.

`run_pytest` is a plain function (no LLM) so it can be unit-tested without any
external service.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from git import Repo

from agents.local_developer_agent import local_read_file, local_write_file, local_list_files
from tools.context7_mcp import load_context7_mcp_tools


def _sync_to_branch(workspace_path: str, branch_name: str) -> None:
    """Fetches origin and checks out the feature branch (creating a tracking
    branch if needed), then pulls the latest commits."""
    repo = Repo(workspace_path)
    origin = repo.remote(name="origin")
    origin.fetch()
    try:
        repo.git.checkout(branch_name)
    except Exception:
        if not repo.git.branch("--list", f"origin/{branch_name}").strip():
            raise RuntimeError(f"Branch '{branch_name}' not found on origin — cannot verify.")
        repo.git.checkout("-b", branch_name, f"origin/{branch_name}")
    try:
        repo.git.pull("origin", branch_name)
    except Exception as e:
        print(f"  [VerifyAgent] Pull of '{branch_name}' failed (continuing with local state): {e}")


def _commit_and_push_tests(workspace_path: str, branch_name: str, message: str) -> bool:
    """Commits and pushes generated test files to the feature branch.
    Returns False when there is nothing to commit."""
    repo = Repo(workspace_path)
    if not repo.is_dirty(include_untracked=True):
        return False
    repo.git.add(A=True)
    repo.index.commit(message)
    repo.remote(name="origin").push(branch_name)
    return True


def _find_test_files(workspace_path: str) -> list:
    """Lists test_*.py files in the workspace (relative paths, forward slashes), skipping VCS dirs."""
    root = Path(workspace_path)
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("test_*.py")
        if ".git" not in p.parts and "node_modules" not in p.parts and "__pycache__" not in p.parts
    )


def run_pytest(workspace_path: str, timeout: int = 600) -> dict:
    """Runs pytest inside the workspace (no LLM involved).

    Returns {"ran": bool, "returncode": int|None, "summary": str,
             "passed": int, "failed": int, "errors": int, "output_tail": str}
    `returncode` is None when the run timed out.
    """
    cmd = [sys.executable, "-m", "pytest", "--tb=short", "-q"]
    try:
        proc = subprocess.run(
            cmd, cwd=workspace_path, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return {
            "ran": True,
            "returncode": None,
            "summary": f"pytest timed out after {timeout}s",
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "output_tail": "",
        }

    output = proc.stdout or ""
    if proc.stderr:
        output += "\n[stderr]\n" + proc.stderr

    passed = failed = errors = 0
    summary = ""
    for line in output.splitlines():
        # The final pytest summary line contains a duration, e.g. "3 passed, 1 failed in 0.42s"
        if re.search(r"in\s+[\d.]+s", line) and re.search(r"\d+\s+(passed|failed|error)", line):
            pm = re.search(r"(\d+)\s+passed", line)
            fm = re.search(r"(\d+)\s+failed", line)
            em = re.search(r"(\d+)\s+error", line)
            passed = int(pm.group(1)) if pm else 0
            failed = int(fm.group(1)) if fm else 0
            errors = int(em.group(1)) if em else 0
            summary = line.strip()
            break
    if not summary and proc.returncode == 5:
        summary = "no tests ran"

    return {
        "ran": True,
        "returncode": proc.returncode,
        "summary": summary,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "output_tail": output[-8000:],
    }


def _clean_markdown(content: str) -> str:
    content = content.strip()
    if content.startswith("```markdown"):
        content = content[11:-3].strip()
    elif content.startswith("```"):
        content = content[3:-3].strip()
    return content


def _acceptance_criteria_block(tasks: list) -> str:
    lines = []
    for t in tasks or []:
        for ac in t.get("acceptance_criteria", []):
            lines.append(f"- [{t.get('id')}] {ac}")
    return "\n".join(lines)


class VerifyAgent:
    def __init__(self):
        model_name = os.environ.get("CODING_MODEL", "gemini-3.1-pro-preview")
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    async def verify(
        self,
        story_details: dict,
        spec: str,
        plan: str,
        tasks: list,
        workspace_path: str,
        branch_name: str,
    ) -> dict:
        """Full SDD verification: sync branch → generate tests → commit/push → run pytest → compliance report."""
        ticket_id = story_details.get("id", "ticket")
        print(f"  [VerifyAgent] Verifying {ticket_id} in {workspace_path} (branch '{branch_name}')...")

        _sync_to_branch(workspace_path, branch_name)

        test_files = await self._generate_tests(story_details, spec, plan, tasks, workspace_path)
        print(f"  [VerifyAgent] Test files present: {test_files or 'none'}")

        committed = False
        if test_files:
            safe_id = ticket_id.replace("/", "-").replace("#", "-")
            committed = _commit_and_push_tests(
                workspace_path, branch_name,
                f"test({safe_id}): generated tests for {story_details.get('title', ticket_id)}",
            )

        pytest_result = run_pytest(workspace_path)
        print(f"  [VerifyAgent] pytest: rc={pytest_result['returncode']} — {pytest_result['summary'] or 'no summary'}")

        report = await self._write_report(story_details, spec, tasks, test_files, pytest_result)

        if not test_files:
            status, message = "failed", "No test files were generated."
        elif pytest_result["returncode"] == 0:
            status, message = "passed", f"All tests passed ({pytest_result['summary'] or 'see report'})."
        else:
            status, message = "failed", f"Tests failed ({pytest_result['summary'] or 'see report'}). See the verification report."

        return {
            "status": status,
            "test_files": test_files,
            "tests_committed": committed,
            "pytest": pytest_result,
            "report": report,
            "message": message,
        }

    async def write_and_run_tests(self, story_details: dict, code_files: list, workspace_path: str) -> dict:
        """Backward-compatible entry point for the legacy PR-recommendations flow
        (no approved spec/plan): generates tests from the story + changed files only."""
        print(f"  [VerifyAgent] Generating tests for {story_details.get('id')} (legacy flow, no spec)...")

        test_files = await self._generate_tests(
            story_details, "", "", [], workspace_path, code_files=code_files
        )
        pytest_result = run_pytest(workspace_path)

        if test_files:
            try:
                repo = Repo(workspace_path)
                branch_name = repo.active_branch.name
                _commit_and_push_tests(
                    workspace_path, branch_name,
                    f"test({story_details.get('id', 'pr')}): generated tests",
                )
            except Exception as e:
                print(f"  [VerifyAgent] Could not commit/push tests (non-fatal): {e}")

        passed, failed = pytest_result["passed"], pytest_result["failed"]
        coverage = f"{passed} passed / {failed} failed"
        status = "success" if pytest_result["returncode"] == 0 else "failed"
        return {
            "status": status,
            "test_files": test_files,
            "coverage": coverage,
            "pytest": pytest_result,
            "message": f"pytest rc={pytest_result['returncode']}: {pytest_result['summary'] or 'no summary'}",
        }

    async def _generate_tests(
        self,
        story_details: dict,
        spec: str,
        plan: str,
        tasks: list,
        workspace_path: str,
        code_files: list = None,
    ) -> list:
        """Runs the ReAct test engineer and returns the test files actually on disk."""
        ac_block = _acceptance_criteria_block(tasks) or "- (use the acceptance criteria from the specification)"
        scope_section = f"""APPROVED SPECIFICATION:
{spec}

IMPLEMENTATION PLAN:
{plan}

ACCEPTANCE CRITERIA TO COVER:
{ac_block}"""
        if not spec and code_files:
            files_block = "\n".join(f"- {f}" for f in code_files) or "- (unknown)"
            scope_section = f"""USER STORY:
- ID: {story_details.get('id', 'unknown')}
- Title: {story_details.get('title', 'Untitled')}
- Description: {story_details.get('description', '')}

CHANGED FILES TO TEST:
{files_block}"""

        system_prompt = f"""You are a Test Engineer generating real, executable pytest tests for newly implemented code.
Your workspace is located at: {workspace_path}

{scope_section}

Your task:
1. List the project structure and read the relevant implemented files to understand their REAL API (signatures, imports, behavior).
2. Check requirements.txt / pyproject.toml for available test dependencies; only import libraries that are actually available in this project.
3. Write focused, deterministic pytest tests in '{workspace_path}/tests/' (create the directory and an __init__.py if missing). Name files test_<module>.py.
4. Every acceptance criterion above must be covered by at least one test. Tests must call the real code — never placeholder asserts like `assert True`.
5. Keep tests fast and independent; do NOT modify production code and do NOT add new dependencies.

When finished, reply with a short list of the test files you created."""

        async with load_context7_mcp_tools() as doc_tools:
            combined_tools = [local_read_file, local_write_file, local_list_files] + doc_tools
            agent_executor = create_react_agent(self.llm, combined_tools)
            result = await agent_executor.ainvoke({"messages": [("user", system_prompt)]})

        content_raw = result["messages"][-1].content
        if isinstance(content_raw, list):
            content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content_raw])
        else:
            content = str(content_raw)
        print(f"  [VerifyAgent] Test engineer finished: {content[:200]}")

        return _find_test_files(workspace_path)

    async def _write_report(self, story_details: dict, spec: str, tasks: list, test_files: list, pytest_result: dict) -> str:
        """LLM-driven spec-compliance report; falls back to a minimal generated
        report so the pipeline never dies on report generation."""
        ac_block = _acceptance_criteria_block(tasks) or "- (see specification)"
        files_block = "\n".join(f"- {f}" for f in test_files) or "- none"

        prompt = f"""You are a QA reviewer writing a spec-compliance report.

TICKET: {story_details.get('id', 'unknown')} — {story_details.get('title', '')}

SPECIFICATION (excerpt):
{spec[:6000]}

ACCEPTANCE CRITERIA:
{ac_block}

GENERATED TEST FILES:
{files_block}

PYTEST EXECUTION RESULT (exit code {pytest_result['returncode']}):
{pytest_result['output_tail'][-6000:] or '(no output)'}

Write a markdown report with EXACTLY these sections:
# Verification Report
## Verdict
One line: PASS or FAIL, and why.
## Test Execution
Summarize the pytest result (counts, notable failures). Distinguish failures in the newly generated tests from pre-existing failures unrelated to this feature.
## Acceptance Criteria Coverage
A markdown table with columns: Criterion | Covered by test? | Result (pass/fail/not tested)
## Recommendations
Bulleted list of concrete next steps (empty list if everything passed).

Output raw markdown only — no code fence around the whole document."""

        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content
            if isinstance(content, list):
                content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content])
            return _clean_markdown(str(content))
        except Exception as e:
            print(f"  [VerifyAgent] Report generation failed ({e}); using fallback report.")
            return self._fallback_report(story_details, test_files, pytest_result)

    def _fallback_report(self, story_details: dict, test_files: list, pytest_result: dict) -> str:
        verdict = "PASS" if pytest_result["returncode"] == 0 else "FAIL"
        lines = [
            "# Verification Report",
            "## Verdict",
            f"{verdict} — pytest exit code {pytest_result['returncode']} ({pytest_result['summary'] or 'no summary'}).",
            "## Test Execution",
            f"- Passed: {pytest_result['passed']}, Failed: {pytest_result['failed']}, Errors: {pytest_result['errors']}",
            "## Acceptance Criteria Coverage",
            "(Report generation unavailable — see pytest output.)",
            "## Recommendations",
            "- Re-run the pipeline to regenerate the compliance report.",
        ]
        return "\n".join(lines)
