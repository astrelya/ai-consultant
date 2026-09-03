"""
Filesystem watcher publishing ``file_tree_update`` SSE events (Story 6.3).

Uses ``watchdog`` (cross-platform Observer) to catch every filesystem
mutation inside a project's workspace regardless of which code path made
it — direct ``write_file``, MCP tool, ``git checkout``, etc. Watchdog
callbacks run on a background thread, so we submit ``publish_event`` to
the captured FastAPI event loop via ``asyncio.run_coroutine_threadsafe``
(fire-and-forget, same tolerance as ``token_tracker``).

State is module-level and keyed by ``project_id``. Access exclusively
through :func:`start_watcher` and :func:`stop_watcher`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Dict

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from backend.api.sse import publish_event

logger = logging.getLogger(__name__)

_IGNORED_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "node_modules"}
_COALESCE_WINDOW_SEC = 0.1

_active_watchers: Dict[str, Observer] = {}


def _is_ignored(rel_path: str) -> bool:
    """Return True if any path segment should be filtered out."""
    if not rel_path or rel_path == ".":
        return False
    parts = rel_path.replace("\\", "/").split("/")
    for seg in parts:
        if not seg:
            continue
        if seg in _IGNORED_DIRS:
            return True
        if seg.startswith("."):
            return True
    return False


class _WorkspaceEventHandler(FileSystemEventHandler):
    """Watchdog handler translating FS events into ``file_tree_update`` SSE events."""

    def __init__(self, project_id: str, root: str, loop: asyncio.AbstractEventLoop):
        self.project_id = project_id
        self.root = root
        self.loop = loop
        self._recent: Dict[tuple[str, str], float] = {}

    def _dispatch(self, src_path: str, operation: str, is_directory: bool) -> None:
        if is_directory:
            return
        try:
            rel = os.path.relpath(src_path, self.root).replace(os.sep, "/")
        except ValueError:
            return
        if _is_ignored(rel):
            return

        key = (rel, operation)
        now = time.monotonic()
        last = self._recent.get(key, 0.0)
        if now - last < _COALESCE_WINDOW_SEC:
            return
        self._recent[key] = now

        try:
            asyncio.run_coroutine_threadsafe(
                publish_event(
                    self.project_id,
                    "file_tree_update",
                    {"path": rel, "operation": operation},
                ),
                self.loop,
            )
        except Exception:
            logger.warning(
                "workspace_watcher: dropped %s event for %s (loop unavailable)",
                operation, rel,
            )

    def on_created(self, event) -> None:  # pragma: no cover - trivial dispatch
        self._dispatch(event.src_path, "created", event.is_directory)

    def on_modified(self, event) -> None:  # pragma: no cover - trivial dispatch
        self._dispatch(event.src_path, "modified", event.is_directory)

    def on_deleted(self, event) -> None:  # pragma: no cover - trivial dispatch
        self._dispatch(event.src_path, "deleted", event.is_directory)


def start_watcher(
    project_id: str,
    workspace_path: str,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Start an Observer for ``project_id`` if one is not already running."""
    if project_id in _active_watchers:
        return
    if not workspace_path or not os.path.isdir(workspace_path):
        return
    handler = _WorkspaceEventHandler(project_id, workspace_path, loop)
    observer = Observer()
    observer.schedule(handler, workspace_path, recursive=True)
    observer.start()
    _active_watchers[project_id] = observer


def stop_watcher(project_id: str) -> None:
    """Stop and drop the Observer for ``project_id`` (no-op if absent)."""
    observer = _active_watchers.pop(project_id, None)
    if observer is None:
        return
    try:
        observer.stop()
        observer.join(timeout=1.0)
    except Exception:
        pass
