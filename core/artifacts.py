"""
SDD Artifact Storage Module
Stores pipeline artifacts (spec.md, plan.md, tasks.md, report.md) outside the
cloned repository so they are never accidentally committed to feature branches.

Layout: <WORKSPACE_DIR>/.sdd/<repo>/<ticket-id>/*.md
"""
import os
from typing import Optional


def artifact_root() -> str:
    workspace_dir = os.path.abspath(os.getenv("WORKSPACE_DIR", "./workspaces"))
    return os.path.join(workspace_dir, ".sdd")


def _safe_ticket_id(ticket_id: str) -> str:
    return ticket_id.replace("/", "-").replace("#", "-")


def artifact_dir(repo_name: str, ticket_id: str) -> str:
    path = os.path.join(artifact_root(), repo_name, _safe_ticket_id(ticket_id))
    os.makedirs(path, exist_ok=True)
    return path


def write_artifact(repo_name: str, ticket_id: str, name: str, content: str) -> str:
    """Writes an artifact markdown file and returns its absolute path."""
    path = os.path.join(artifact_dir(repo_name, ticket_id), name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  [Artifacts] Saved {name} -> {path}")
    return path


def read_artifact(repo_name: str, ticket_id: str, name: str) -> Optional[str]:
    path = os.path.join(artifact_dir(repo_name, ticket_id), name)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
