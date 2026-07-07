"""
Tester Agent Module
Responsible for generating and EXECUTING unit tests for code created by the Developer Agent.
Supports local execution (subprocess) and remote CI (GitHub Actions).
"""
import asyncio
import base64
import io
import os
import re
import subprocess
import time
import zipfile

import requests
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from tools.file_ops import read_file, write_file

# ---------------------------------------------------------------------------
# GitHub Actions workflow template — pushed automatically to target repos
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

# ---------------------------------------------------------------------------
# Per-language system prompts for test generation
# ---------------------------------------------------------------------------
_TEST_SYSTEM_PROMPTS = {
    "python": (
        "You are an expert Python tester. Write meaningful pytest unit tests for the provided code. "
        "Cover main functionality and edge cases. Use unittest.mock for external dependencies. "
        "Output ONLY the Python test code, no markdown, no explanations."
    ),
    "javascript": (
        "You are an expert JavaScript tester. Write Jest unit tests for the provided code. "
        "Cover main functionality and edge cases. Mock external dependencies with jest.mock(). "
        "Output ONLY the JavaScript test code, no markdown, no explanations."
    ),
    "typescript": (
        "You are an expert TypeScript tester. Write Jest unit tests for the provided TypeScript code. "
        "Cover main functionality and edge cases. Mock external dependencies with jest.mock(). "
        "Output ONLY the TypeScript test code, no markdown, no explanations."
    ),
    "go": (
        "You are an expert Go tester. Write Go unit tests using the standard testing package. "
        "Cover main functionality and edge cases. "
        "Output ONLY the Go test code, no markdown, no explanations."
    ),
}

_FIX_SYSTEM_PROMPT = (
    "You are an expert developer. The following source code has failing tests. "
    "Analyze the test errors and return a corrected version of the SOURCE code (not the tests). "
    "Output ONLY the corrected source code, no markdown, no explanations."
)


class TesterAgent:
    def __init__(self):
        model_name = os.environ.get("TICKET_MODEL", "gemini-2.5-flash")
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)
        self.timeout = int(os.environ.get("TEST_TIMEOUT_SECONDS", "120"))
        self.github_token = os.environ.get(
            "GITHUB_PERSONAL_ACCESS_TOKEN", os.environ.get("GITHUB_TOKEN", "")
        )
        self.github_api = "https://api.github.com"

    # -----------------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------------

    async def write_and_run_tests(
        self,
        story_details: dict,
        code_files: list,
        workspace_path: str,
        mode: str = "local",
        pr_url: str = None,
    ) -> dict:
        print(f"  [TesterAgent] Mode={mode} | Analyzing {len(code_files)} file(s)...")
        if mode == "local":
            return self._run_local_tests(story_details, code_files, workspace_path, pr_url)
        else:
            return await self._run_remote_tests(story_details, code_files, workspace_path, pr_url)

    # -----------------------------------------------------------------------
    # MODE LOCAL — subprocess execution + 1 auto-fix attempt
    # -----------------------------------------------------------------------

    def _run_local_tests(self, story_details, code_files, workspace_path, pr_url):
        test_files = []
        all_passed = True
        final_output = []

        for file_path in code_files:
            file_name = os.path.basename(file_path)
            lang = self._detect_language(file_path)
            if lang == "unsupported":
                print(f"  [TesterAgent] Skipping {file_name}: unsupported language.")
                continue

            test_file_path = os.path.join(workspace_path, "tests", f"test_{file_name}")
            os.makedirs(os.path.dirname(test_file_path), exist_ok=True)

            code_content = read_file(file_path)
            test_code = self._generate_test_code(file_name, code_content, lang)

            with open(test_file_path, "w", encoding="utf-8") as f:
                f.write(test_code)
            test_files.append(test_file_path)
            print(f"  [TesterAgent] Test file written: {test_file_path}")

            cmd = self._build_test_command(lang, test_file_path)
            passed, stdout, stderr = self._execute_tests(cmd, workspace_path)

            if not passed:
                print(f"  [TesterAgent] Tests failed — attempting 1 auto-fix for {file_name}...")
                fixed_code = self._request_fix(file_name, code_content, stderr or stdout)
                if fixed_code:
                    write_file(file_path, fixed_code)
                    passed, stdout, stderr = self._execute_tests(cmd, workspace_path)

            output_log = stdout + ("\n" + stderr if stderr else "")
            final_output.append(output_log)

            if passed:
                print(f"  [TesterAgent] Tests passed for {file_name}")
            else:
                all_passed = False
                error_body = (
                    f"🔴 **Tests failed after auto-fix attempt** for `{file_name}`\n\n"
                    f"```\n{output_log[:3000]}\n```"
                )
                print(f"  [TesterAgent] Tests still failing for {file_name}.")
                print(f"  [TesterAgent] Error log:\n{output_log[:1000]}")
                if pr_url:
                    self._post_pr_comment(pr_url, error_body)

        return {
            "status": "success" if all_passed else "failure",
            "test_files": test_files,
            "test_output": "\n---\n".join(final_output),
            "message": (
                "All tests passed."
                if all_passed
                else "Tests failed after auto-fix. See PR comments for details."
            ),
        }

    # -----------------------------------------------------------------------
    # MODE REMOTE — push test files + poll GitHub Actions CI
    # -----------------------------------------------------------------------

    async def _run_remote_tests(self, story_details, code_files, workspace_path, pr_url):
        if not pr_url:
            print("  [TesterAgent] No PR URL provided; skipping remote CI tests.")
            return {"status": "skipped", "message": "No PR URL available for CI."}

        owner, repo, pr_number, branch = self._parse_pr_info(pr_url, story_details)
        if not owner:
            return {"status": "skipped", "message": "Could not parse PR info."}

        test_files_pushed = []
        for file_path in code_files:
            file_name = os.path.basename(file_path)
            lang = self._detect_language(file_path)
            if lang == "unsupported":
                continue
            code_content = read_file(file_path)
            test_code = self._generate_test_code(file_name, code_content, lang)
            remote_path = f"tests/test_{file_name}"
            ok = self._push_file_to_branch(
                owner, repo, branch, remote_path, test_code,
                f"test: add auto-generated tests for {file_name}",
            )
            if ok:
                test_files_pushed.append(remote_path)
                print(f"  [TesterAgent] Pushed test file to branch: {remote_path}")

        if not test_files_pushed:
            return {"status": "skipped", "message": "No test files could be pushed."}

        print(f"  [TesterAgent] Waiting for GitHub Actions CI on branch '{branch}'...")
        run_id, conclusion = await self._poll_workflow_run(owner, repo, branch)

        if conclusion == "success":
            print(f"  [TesterAgent] CI passed (run_id={run_id})")
            return {"status": "success", "message": "CI passed.", "run_id": run_id}

        print(f"  [TesterAgent] CI failed (run_id={run_id}, conclusion={conclusion})")
        logs = self._fetch_workflow_logs(owner, repo, run_id)
        analysis = self._analyze_failure_with_llm(logs)
        comment = (
            f"🔴 **CI failed** — GitHub Actions run "
            f"[{run_id}](https://github.com/{owner}/{repo}/actions/runs/{run_id})\n\n"
            f"**Analysis:**\n{analysis}\n\n"
            f"<details><summary>Raw logs (truncated)</summary>\n\n"
            f"```\n{logs[:3000]}\n```\n</details>"
        )
        self._post_pr_comment(pr_url, comment)
        return {"status": "failure", "message": "CI failed. See PR for analysis.", "run_id": run_id}

    # -----------------------------------------------------------------------
    # Language / runner helpers
    # -----------------------------------------------------------------------

    def _detect_language(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        return {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".go": "go",
        }.get(ext, "unsupported")

    def _build_test_command(self, lang: str, test_file_path: str) -> list:
        return {
            "python":     ["pytest", test_file_path, "-v", "--tb=short"],
            "javascript": ["npx", "jest", test_file_path, "--no-coverage"],
            "typescript": ["npx", "jest", test_file_path, "--no-coverage"],
            "go":         ["go", "test", "./..."],
        }.get(lang, ["pytest", test_file_path, "-v", "--tb=short"])

    def _execute_tests(self, cmd: list, cwd: str):
        from tools.rtk_wrapper import run_command_with_rtk
        return run_command_with_rtk(cmd, cwd=cwd, timeout=self.timeout)

    # -----------------------------------------------------------------------
    # LLM helpers
    # -----------------------------------------------------------------------

    def _generate_test_code(self, file_name: str, code_content: str, lang: str) -> str:
        system_prompt = _TEST_SYSTEM_PROMPTS.get(lang, _TEST_SYSTEM_PROMPTS["python"])
        user_prompt = (
            f"Here is the code for `{file_name}`:\n\n```\n{code_content}\n```\n\nWrite tests."
        )
        response = self.llm.invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )
        return self._strip_code_block(response.content)

    def _request_fix(self, file_name: str, original_code: str, error_output: str) -> str:
        user_prompt = (
            f"Source file: `{file_name}`\n\n"
            f"Source code:\n```\n{original_code}\n```\n\n"
            f"Test errors:\n```\n{error_output[:2000]}\n```\n\n"
            "Return only the corrected source code."
        )
        try:
            response = self.llm.invoke(
                [SystemMessage(content=_FIX_SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
            )
            return self._strip_code_block(response.content)
        except Exception as e:
            print(f"  [TesterAgent] LLM fix request failed: {e}")
            return ""

    def _analyze_failure_with_llm(self, logs: str) -> str:
        from tools.caveman_prompt import wrap_with_caveman
        prompt = wrap_with_caveman(
            f"The following are CI test failure logs. "
            f"Briefly explain what is failing and why:\n\n```\n{logs[:3000]}\n```"
        )
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return self._strip_code_block(response.content)
        except Exception:
            return "Could not analyze logs."

    @staticmethod
    def _strip_code_block(content) -> str:
        if isinstance(content, list):
            text = "".join(
                b.get("text", "") if isinstance(b, dict) else str(b) for b in content
            )
        else:
            text = content
        text = text.strip()
        if text.startswith("```python"):
            text = text[9:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    # -----------------------------------------------------------------------
    # GitHub REST API helpers
    # -----------------------------------------------------------------------

    def _github_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _parse_pr_info(self, pr_url: str, story_details: dict):
        """Returns (owner, repo, pr_number, branch) from a PR URL."""
        m = re.search(r"github\.com/([\w\-]+)/([\w\-]+)/pull/(\d+)", pr_url or "")
        if m:
            owner, repo, pr_number = m.group(1), m.group(2), int(m.group(3))
        else:
            owner = os.environ.get("GITHUB_OWNER", "")
            repo_full = story_details.get("repo_full_name", "/")
            repo = repo_full.split("/")[-1]
            pr_number = None
        ticket_id = story_details.get("id", "unknown").replace("/", "-").replace("#", "-")
        branch = f"feature/{ticket_id}"
        return owner, repo, pr_number, branch

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

    def _push_file_to_branch(
        self, owner: str, repo: str, branch: str, path: str, content: str, message: str
    ) -> bool:
        url = f"{self.github_api}/repos/{owner}/{repo}/contents/{path}"
        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        payload = {"message": message, "content": encoded, "branch": branch}
        try:
            get_resp = requests.get(
                url, headers=self._github_headers(), params={"ref": branch}, timeout=10
            )
            if get_resp.status_code == 200:
                payload["sha"] = get_resp.json().get("sha", "")
            resp = requests.put(url, headers=self._github_headers(), json=payload, timeout=15)
            return resp.status_code in (200, 201)
        except Exception as e:
            print(f"  [TesterAgent] Error pushing file {path}: {e}")
            return False

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
