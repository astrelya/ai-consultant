"""
Tester Agent Module
Pure test-execution responsibility: runs the project's real test suite (local)
or polls GitHub Actions CI (remote) and reports pass/fail + raw output.
Does NOT attempt to fix code — that is the Developer Agent's job, invoked by
the Supervisor's fix loop whenever a test run comes back as a failure.
"""
import asyncio
import io
import json
import os
import re
import subprocess
import time
import zipfile

import requests
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

# ---------------------------------------------------------------------------
# GitHub Actions workflow template — pushed automatically to target repos by
# EnvironmentAgent. Kept here since environment_agent.py imports it from
# this module.
# ---------------------------------------------------------------------------
_CI_WORKFLOW_TEMPLATE = """\
name: AI Agent Tests
on:
  push:
    branches:
      - "feature/**"
      - "feature-local/**"
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
          pip install pytest
      - name: Run tests
        run: pytest tests/ -v --tb=short
"""


class TesterAgent:
    def __init__(self):
        model_name = os.environ.get("TICKET_MODEL", "gemini-2.5-flash")
        # Only used to write a short human-readable summary of a CI failure
        # for the PR comment — never used to generate or fix code.
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)
        self.timeout = int(os.environ.get("TEST_TIMEOUT_SECONDS", "120"))
        self.github_token = os.environ.get(
            "GITHUB_PERSONAL_ACCESS_TOKEN", os.environ.get("GITHUB_TOKEN", "")
        )
        self.github_api = "https://api.github.com"

    # -----------------------------------------------------------------------
    # LOCAL — run the project's real test command. No code fixing here.
    # -----------------------------------------------------------------------

    def run_local_tests(self, workspace_path: str) -> dict:
        cmd = self._detect_project_test_command(workspace_path)
        if cmd is None:
            return {
                "status": "skipped",
                "command": None,
                "output": "",
                "message": (
                    "No recognizable project test suite found (checked package.json "
                    "'test' script, test/run-tests.js, tests/*.py)."
                ),
            }

        cmd_desc = " ".join(cmd)
        print(f"  [TesterAgent] Running project test suite: `{cmd_desc}`...")
        passed, stdout, stderr = self._execute_tests(cmd, workspace_path)
        output = (stdout + ("\n" + stderr if stderr else "")).strip()

        return {
            "status": "success" if passed else "failure",
            "command": cmd_desc,
            "output": output,
            "message": "All tests passed." if passed else "Tests failed.",
        }

    def _detect_project_test_command(self, workspace_path: str):
        """
        Looks for a real, existing test entry point, in priority order:
          1. package.json "scripts"."test"          -> ["npm", "test", "--silent"]
          2. test/run-tests.js or tests/run-tests.js -> ["node", "<path>"]
          3. A tests/ directory containing .py files -> ["pytest", "tests/", "-v", "--tb=short"]
        Returns None if nothing recognizable is found.
        """
        package_json_path = os.path.join(workspace_path, "package.json")
        if os.path.isfile(package_json_path):
            try:
                with open(package_json_path, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                test_script = pkg.get("scripts", {}).get("test")
                if test_script and "no test specified" not in test_script.lower():
                    return ["npm", "test", "--silent"]
            except Exception as e:
                print(f"  [TesterAgent] Could not parse package.json: {e}")

        for candidate in ("test/run-tests.js", "tests/run-tests.js"):
            candidate_path = os.path.join(workspace_path, candidate)
            if os.path.isfile(candidate_path):
                return ["node", candidate]

        tests_dir = os.path.join(workspace_path, "tests")
        if os.path.isdir(tests_dir):
            has_py_tests = any(
                fname.endswith(".py") and (fname.startswith("test_") or fname.endswith("_test.py"))
                for fname in os.listdir(tests_dir)
            )
            if has_py_tests:
                return ["pytest", "tests/", "-v", "--tb=short"]

        return None

    def _execute_tests(self, cmd: list, cwd: str):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=self.timeout,
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", f"Test execution timed out after {self.timeout}s."
        except FileNotFoundError as e:
            return False, "", f"Test runner not found: {e}"

    # -----------------------------------------------------------------------
    # REMOTE — poll the GitHub Actions run already triggered by the
    # developer agent's push. Nothing is pushed here; the repo's own CI
    # workflow is the source of truth.
    # -----------------------------------------------------------------------

    async def run_remote_tests(self, owner: str, repo: str, branch: str, pr_url: str = None) -> dict:
        print(f"  [TesterAgent] Waiting for GitHub Actions CI on branch '{branch}'...")
        run_id, conclusion = await self._poll_workflow_run(owner, repo, branch)

        if conclusion == "success":
            print(f"  [TesterAgent] CI passed (run_id={run_id})")
            return {
                "status": "success",
                "command": "GitHub Actions CI",
                "output": "",
                "message": "CI passed.",
                "run_id": run_id,
            }

        print(f"  [TesterAgent] CI failed (run_id={run_id}, conclusion={conclusion})")
        logs = self._fetch_workflow_logs(owner, repo, run_id) if run_id else "No workflow run found for this branch."

        if pr_url:
            analysis = self._analyze_failure_with_llm(logs)
            comment = (
                f"🔴 **CI failed** — GitHub Actions run "
                f"[{run_id}](https://github.com/{owner}/{repo}/actions/runs/{run_id})\n\n"
                f"**Analysis:**\n{analysis}\n\n"
                f"<details><summary>Raw logs (truncated)</summary>\n\n"
                f"```\n{logs[:3000]}\n```\n</details>"
            )
            self._post_pr_comment(pr_url, comment)

        return {
            "status": "failure",
            "command": "GitHub Actions CI",
            "output": logs,
            "message": f"CI failed (conclusion={conclusion}).",
            "run_id": run_id,
        }

    def _analyze_failure_with_llm(self, logs: str) -> str:
        from tools.caveman_prompt import wrap_with_caveman
        prompt = wrap_with_caveman(
            f"The following are CI test failure logs. "
            f"Briefly explain what is failing and why:\n\n```\n{logs[:3000]}\n```"
        )
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = response.content
            if isinstance(content, list):
                return "".join(
                    b.get("text", "") if isinstance(b, dict) else str(b) for b in content
                ).strip()
            return str(content).strip()
        except Exception:
            return "Could not analyze logs."

    # -----------------------------------------------------------------------
    # GitHub REST API helpers (remote mode only)
    # -----------------------------------------------------------------------

    def _github_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _post_pr_comment(self, pr_url: str, body: str):
        m = re.search(r"github\.com/([\w\-]+)/([\w\-]+)/pull/(\d+)", pr_url or "")
        if not m:
            print(f"  [TesterAgent] Could not parse PR URL for comment: {pr_url}")
            return
        owner, repo, pr_number = m.group(1), m.group(2), m.group(3)
        url = f"{self.github_api}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        try:
            resp = requests.post(
                url, headers=self._github_headers(), json={"body": body}, timeout=15
            )
            if resp.status_code == 201:
                print(f"  [TesterAgent] Comment posted on PR #{pr_number}")
            else:
                print(f"  [TesterAgent] Failed to post comment: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            print(f"  [TesterAgent] Error posting PR comment: {e}")

    async def _poll_workflow_run(self, owner: str, repo: str, branch: str):
        url = f"{self.github_api}/repos/{owner}/{repo}/actions/runs"
        deadline = time.time() + self.timeout * 3
        run_id = None
        while time.time() < deadline:
            await asyncio.sleep(10)
            try:
                resp = requests.get(
                    url,
                    headers=self._github_headers(),
                    params={"branch": branch, "event": "push", "per_page": 5},
                    timeout=10,
                )
                if resp.status_code != 200:
                    continue
                runs = resp.json().get("workflow_runs", [])
                if not runs:
                    continue
                latest = runs[0]
                run_id = latest["id"]
                status = latest["status"]
                conclusion = latest.get("conclusion")
                print(f"  [TesterAgent] CI run {run_id}: status={status}, conclusion={conclusion}")
                if status == "completed":
                    return run_id, conclusion or "failure"
            except Exception as e:
                print(f"  [TesterAgent] Polling error: {e}")
        return run_id, "timeout"

    def _fetch_workflow_logs(self, owner: str, repo: str, run_id: int) -> str:
        url = f"{self.github_api}/repos/{owner}/{repo}/actions/runs/{run_id}/logs"
        try:
            resp = requests.get(
                url, headers=self._github_headers(), timeout=20, allow_redirects=True
            )
            if resp.status_code != 200:
                return f"Could not fetch logs (HTTP {resp.status_code})"
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
            logs = []
            for name in zf.namelist():
                with zf.open(name) as f:
                    logs.append(f.read().decode("utf-8", errors="replace"))
            return "\n".join(logs)
        except Exception as e:
            return f"Error fetching logs: {e}"