"""
Session-context preamble builder — Story 5.4.

Pure Python (no LLM, no I/O). Formats a compact preamble containing the project's
spec, ticket_history summary, agent_memory keys, and last N chat messages so
subprocess-driven modes (brainstorm / spec_review) never re-ask for context that
already lives in the project store (AC-3, AD-4).

The ticket-summary format mirrors the one produced by
``SupervisorAgent._build_accumulated_context`` (Story 5.3) at
``agents/supervisor_agent.py``. It is re-implemented inline rather than imported
to keep this helper free of the sub-agent import graph — if the two ever drift,
unify them or add an explicit shared formatter.

TODO: unify with SupervisorAgent._build_accumulated_context if a shared formatter
lands.
"""
from __future__ import annotations

from typing import Any

_SPEC_EXCERPT_CHARS = 500
_MEMORY_VALUE_CHARS = 200
_CHAT_MESSAGE_CHARS = 500
_CHAT_HISTORY_LIMIT = 10


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _spec_section(spec: Any) -> str:
    if not spec:
        return "## Spec\n(no spec)"
    excerpt = _truncate(str(spec), _SPEC_EXCERPT_CHARS)
    return f"## Spec\n{excerpt}"


def _ticket_section(ticket_history: Any) -> str:
    if not isinstance(ticket_history, list) or not ticket_history:
        return "## Ticket History\n(no tickets)"
    lines: list[str] = ["## Ticket History"]
    for ticket in ticket_history:
        if not isinstance(ticket, dict):
            continue
        tid = ticket.get("id", "?")
        title = (ticket.get("title") or "").strip()
        file_list = ticket.get("file_list") or []
        notes = (ticket.get("completion_notes") or "").strip()
        lines.append(f"[{tid}] {title}".rstrip())
        if file_list:
            files_str = ", ".join(str(p) for p in file_list)
            lines.append(f"  Files: {files_str}")
        lines.append(f"  Notes: {notes if notes else '(none)'}")
    return "\n".join(lines)


def _memory_section(agent_memory: Any) -> str:
    if not isinstance(agent_memory, dict) or not agent_memory:
        return "## Agent Memory\n(empty)"
    lines: list[str] = ["## Agent Memory"]
    for key, value in agent_memory.items():
        rendered = _truncate(str(value), _MEMORY_VALUE_CHARS)
        lines.append(f"- {key}: {rendered}")
    return "\n".join(lines)


def _chat_section(chat_history: Any) -> str:
    if not isinstance(chat_history, list) or not chat_history:
        return "## Recent Conversation\n(no prior messages)"
    tail = chat_history[-_CHAT_HISTORY_LIMIT:]
    lines: list[str] = ["## Recent Conversation"]
    for entry in tail:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role", "user")
        content = _truncate(str(entry.get("content", "")), _CHAT_MESSAGE_CHARS)
        lines.append(f"[{role}] {content}")
    return "\n".join(lines)


def build_session_context_preamble(project: dict) -> str:
    """Return a compact multi-section preamble for the given project.

    Returns ``""`` when the project has no spec, no tickets, no memory, and no
    chat history — nothing worth prepending.
    """
    spec = project.get("spec")
    tickets = project.get("ticket_history")
    memory = project.get("agent_memory")
    chat = project.get("chat_history")

    has_content = bool(spec) or bool(tickets) or bool(memory) or bool(chat)
    if not has_content:
        return ""

    sections = [
        "# Prior Session Context",
        _spec_section(spec),
        _ticket_section(tickets),
        _memory_section(memory),
        _chat_section(chat),
    ]
    return "\n\n".join(sections)
