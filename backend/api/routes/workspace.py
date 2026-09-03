"""
Workspace tree and file-content endpoints for the Dev View (Story 6.3).

Both endpoints are read-only, filesystem-only — no LLM call, no DB write.
They resolve the workspace root from ``project.agent_memory["workspace_path"]``
(persisted by :class:`SupervisorAgent._execute_ticket` per AC-6) and expose
just enough to render a live file tree + a read-only viewer.

Security — every returned/consumed path is validated against the workspace
root via ``os.path.commonpath`` (AC-3, AC-7 / OWASP A01).
"""
from __future__ import annotations

import asyncio
import os
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.api.workspace_watcher import _IGNORED_DIRS
from backend.store import project_store

router = APIRouter()

_MAX_FILE_BYTES = 1024 * 1024  # 1 MB (AC-7)


class WorkspaceEntry(BaseModel):
    path: str
    type: Literal["file", "dir"]


class WorkspaceTree(BaseModel):
    root: Optional[str]
    entries: List[WorkspaceEntry]


class WorkspaceFile(BaseModel):
    path: str
    content: str
    truncated: bool


def _list_workspace(root: str) -> List[WorkspaceEntry]:
    dirs_out: List[WorkspaceEntry] = []
    files_out: List[WorkspaceEntry] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in _IGNORED_DIRS and not d.startswith(".")
        ]
        for name in dirnames:
            abs_path = os.path.join(dirpath, name)
            rel = os.path.relpath(abs_path, root).replace(os.sep, "/")
            dirs_out.append(WorkspaceEntry(path=rel, type="dir"))
        for name in filenames:
            if name.startswith("."):
                continue
            abs_path = os.path.join(dirpath, name)
            rel = os.path.relpath(abs_path, root).replace(os.sep, "/")
            files_out.append(WorkspaceEntry(path=rel, type="file"))
    dirs_out.sort(key=lambda e: e.path.lower())
    files_out.sort(key=lambda e: e.path.lower())
    return dirs_out + files_out


@router.get("/projects/{project_id}/workspace/tree", response_model=WorkspaceTree)
async def get_workspace_tree(project_id: str) -> WorkspaceTree:
    project = await project_store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    agent_memory = project.get("agent_memory") or {}
    workspace_path = (
        agent_memory.get("workspace_path") if isinstance(agent_memory, dict) else None
    )
    if not workspace_path or not os.path.isdir(workspace_path):
        return WorkspaceTree(root=None, entries=[])
    entries = await asyncio.to_thread(_list_workspace, workspace_path)
    return WorkspaceTree(root=workspace_path, entries=entries)


def _read_file_utf8(target: str) -> tuple[str, bool]:
    try:
        with open(target, "r", encoding="utf-8") as fh:
            return fh.read(), False
    except UnicodeDecodeError:
        return "<binary file>", True


@router.get("/projects/{project_id}/workspace/file", response_model=WorkspaceFile)
async def get_workspace_file(
    project_id: str,
    path: str = Query(..., description="Workspace-relative file path"),
) -> WorkspaceFile:
    project = await project_store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    agent_memory = project.get("agent_memory") or {}
    workspace_path = (
        agent_memory.get("workspace_path") if isinstance(agent_memory, dict) else None
    )
    if not workspace_path or not os.path.isdir(workspace_path):
        raise HTTPException(status_code=404, detail="No workspace")

    root = os.path.abspath(workspace_path)
    target = os.path.abspath(os.path.join(root, path))
    try:
        if os.path.commonpath([root, target]) != root:
            raise HTTPException(status_code=400, detail="Invalid path")
    except ValueError:
        # Different drives on Windows → definitely outside root
        raise HTTPException(status_code=400, detail="Invalid path")

    if not os.path.exists(target):
        raise HTTPException(status_code=404, detail="File not found")
    if os.path.isdir(target):
        raise HTTPException(status_code=400, detail="Path is a directory")
    if os.path.getsize(target) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="File too large")

    content, truncated = await asyncio.to_thread(_read_file_utf8, target)
    return WorkspaceFile(path=path, content=content, truncated=truncated)
