"""Context7 grounding helper (Story 5.5 / AD-8).

Every code-generation entry point in a developer agent must call
``ground_with_context7`` before the ReAct agent's ``ainvoke``. If grounding
cannot be completed, ``Context7GroundingError`` is raised — the developer
agent must convert that into a normal error dict so ``SupervisorAgent``
treats the ticket as failed (never proceed to code-gen ungrounded).
"""
from __future__ import annotations

import os
import re
from typing import Iterable, List, Optional, Tuple

from langchain_google_genai import ChatGoogleGenerativeAI

from agents.token_tracker import tracked_ainvoke
from backend.api.sse import publish_event
from tools.mcp_loader import MCPManager


class Context7GroundingError(RuntimeError):
    """Raised when Context7 grounding cannot be completed. AD-8: hard violation."""


_DEFAULT_WHITELIST = "fastapi,langgraph,langchain,pytest,asyncpg,react,next.js,tailwindcss"


def _whitelist() -> List[str]:
    raw = os.environ.get("CONTEXT7_LIBRARY_WHITELIST", _DEFAULT_WHITELIST)
    return [s.strip().lower() for s in raw.split(",") if s.strip()]


def _infer_target_libraries_heuristic(text: str) -> List[str]:
    text_lower = text.lower()
    hits: List[str] = []
    for lib in _whitelist():
        if lib in text_lower and lib not in hits:
            hits.append(lib)
    return hits


async def _infer_target_libraries_llm(text: str) -> List[str]:
    # AD-4: LLM is the last resort when the pure-Python heuristic yields nothing.
    llm = ChatGoogleGenerativeAI(
        model=os.environ.get("TICKET_MODEL", "gemini-2.5-flash"), temperature=0
    )
    prompt = (
        "List up to 3 open-source libraries or frameworks that the following "
        "ticket description is most likely to touch. Return ONLY a comma-separated "
        "list of lowercase names, no prose.\n\n"
        f"{text}"
    )
    result = await tracked_ainvoke(llm, prompt)
    content = result.content
    # langchain-google-genai may return content as a list of dicts.
    if isinstance(content, list):
        content = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return [s.strip().lower() for s in str(content).split(",") if s.strip()]


async def _infer_target_libraries(story_details: dict) -> List[str]:
    text = " ".join(
        str(story_details.get(k, ""))
        for k in ("title", "description", "accumulated_context")
    )
    hits = _infer_target_libraries_heuristic(text)
    if not hits:
        hits = await _infer_target_libraries_llm(text)
        # Deduplicate LLM output preserving order.
        seen: List[str] = []
        for lib in hits:
            if lib and lib not in seen:
                seen.append(lib)
        hits = seen
    max_libs = int(os.environ.get("CONTEXT7_MAX_LIBRARIES", "3"))
    return hits[:max_libs]


def _find_tool(tools: Iterable, name: str):
    for t in tools:
        if getattr(t, "name", None) == name:
            return t
    return None


async def ground_with_context7(
    story_details: dict, project_id: Optional[str]
) -> str:
    """Query Context7 for every target library and return the grounding preamble.

    Raises ``Context7GroundingError`` if grounding cannot be completed. The
    caller MUST NOT proceed with code generation in that case (AD-8).
    """
    manager = await MCPManager.get_instance()
    doc_tools = getattr(manager, "doc_tools", []) or []
    if not doc_tools:
        raise Context7GroundingError(
            "Context7 MCP unavailable — CONTEXT7_API_KEY missing or MCP subprocess failed to start"
        )

    resolve_tool = _find_tool(doc_tools, "resolve-library-id")
    docs_tool = _find_tool(doc_tools, "get-library-docs")
    if resolve_tool is None or docs_tool is None:
        missing = "resolve-library-id" if resolve_tool is None else "get-library-docs"
        raise Context7GroundingError(
            f"Context7 MCP missing required tool: {missing}"
        )

    libraries = await _infer_target_libraries(story_details)
    if not libraries:
        raise Context7GroundingError(
            "Could not identify any target library for grounding"
        )

    max_chars = int(os.environ.get("CONTEXT7_MAX_CHARS_PER_LIB", "4000"))
    tokens = int(os.environ.get("CONTEXT7_TOKENS_PER_LIB", "2000"))

    pid = str(project_id) if project_id else None

    successes: List[Tuple[str, str, str]] = []
    failures: List[Tuple[str, str]] = []

    for lib in libraries:
        if pid:
            await publish_event(
                pid, "agent_log", {"message": f"Querying Context7 for {lib}…"}
            )
        try:
            resolved_raw = await resolve_tool.ainvoke({"libraryName": lib})
            match = re.search(
                r"[a-zA-Z0-9._-]+/[a-zA-Z0-9._/-]+", str(resolved_raw)
            )
            if not match:
                raise ValueError(
                    f"could not parse resolved id from: {str(resolved_raw)[:200]!r}"
                )
            resolved_id = match.group(0)
            docs_raw = await docs_tool.ainvoke(
                {"context7CompatibleLibraryID": resolved_id, "tokens": tokens}
            )
            docs = str(docs_raw)[:max_chars]
            successes.append((lib, resolved_id, docs))
        except Exception as exc:  # noqa: BLE001
            failures.append((lib, str(exc)))
            if pid:
                await publish_event(
                    pid,
                    "agent_log",
                    {"message": f"Context7 grounding failed for {lib}: {exc}"},
                )

    if not successes:
        raise Context7GroundingError(
            f"All Context7 grounding queries failed: {failures}"
        )

    blocks = [f"[{lib}] (id: {rid})\n{docs}" for lib, rid, docs in successes]
    return (
        "--- Context7 Grounding ---\n"
        + "\n\n".join(blocks)
        + "\n--------------------------\n"
    )
