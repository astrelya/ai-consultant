"""
Implementation agent — wraps the existing CLI SupervisorAgent so the FastAPI
worker can trigger a full implementation run for a Jira issue key.

The SupervisorAgent already handles: fetching ticket details, preparing the
workspace, delegating to the developer agent (local or remote), running the
tester agent, and (in remote mode) opening a PR via the GitHub MCP tools.
"""
import os
import sys
from pathlib import Path
from typing import Any


# Make the repo root importable so we can reuse the existing `agents/` package.
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


async def run_implementation(
    jira_issue_key: str,
    coding_model: str,
    repo_pat: str | None = None,
    repo_owner: str | None = None,
    repo_name: str | None = None,
    mode: str = "remote",
) -> dict[str, Any]:
    """Invoke the existing SupervisorAgent to implement a ticket."""
    # Push per-run configuration through env — this is how the existing agents read config.
    if coding_model:
        os.environ["GEMINI_MODEL"] = coding_model
    if repo_pat:
        os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"] = repo_pat
    if repo_owner:
        os.environ["GITHUB_OWNER"] = repo_owner
    if repo_name:
        os.environ["GITHUB_REPO"] = repo_name
    os.environ["AGENT_MODE"] = mode

    from agents.main_agent import SupervisorAgent  # imported lazily so env vars apply

    supervisor = SupervisorAgent()
    supervisor.mode = mode
    result = await supervisor.run(jira_issue_key)
    if isinstance(result, str):
        return {"status": "failed", "error": result}
    return result
