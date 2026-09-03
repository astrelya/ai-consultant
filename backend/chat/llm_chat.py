"""Tool-calling streaming chat over Gemini.

Design decision (2026-09-03): the rigid keyword pipeline
(`brainstorm`/`spec_review`/`generate_tickets`/`execute` route branches) was
replaced with a single LLM agent that decides on its own when to invoke actions
via bound tools. The user just talks naturally; the LLM calls `save_spec` /
`generate_tickets` / `execute_pending_tickets` when appropriate.

Streaming loop:
    astream → collect text chunks → when the merged chunk carries tool_calls,
    execute them → append ToolMessages → re-stream → repeat until no tool_calls.

Env-var shim: langchain_google_genai reads GOOGLE_API_KEY; if only
GEMINI_API_KEY is set, mirror it once so calls don't silently fail.
"""
from __future__ import annotations

import logging
import os
from typing import Awaitable, Callable

from langchain_core.messages import (
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from agents import token_tracker
from backend.api.sse import publish_event
from backend.chat.tools import build_tools

logger = logging.getLogger(__name__)


if os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]


DEFAULT_TICKET_MODEL = "gemini-2.5-flash"
DEFAULT_CODING_MODEL = "gemini-2.5-pro"

AVAILABLE_MODELS: list[str] = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-3.1-pro-preview",
]

MAX_TOOL_ITERATIONS = 6

SYSTEM_PROMPT = (
    "You are the AI Consultant — a project-manager-style assistant helping the "
    "user build software end-to-end. You have TOOLS you can and should invoke "
    "to actually do things. Never claim you did something without calling the "
    "corresponding tool.\n\n"
    "Available tools:\n"
    "  • get_project_state() — check what's saved (spec, tickets) before deciding.\n"
    "  • save_spec(spec_text) — persist a spec. Pass the FULL markdown text.\n"
    "  • generate_tickets() — break the saved spec into implementation tickets.\n"
    "  • execute_pending_tickets() — run the SupervisorAgent on all Pending tickets.\n\n"
    "Workflow the user expects:\n"
    "  1. Discussion / brainstorming to sharpen an idea.\n"
    "  2. When the idea is sharp, YOU draft a spec and call save_spec — do NOT "
    "     ask the user to paste it back at you.\n"
    "  3. Propose to generate tickets. If the user agrees, call generate_tickets.\n"
    "  4. Propose to start development. If the user agrees, call "
    "     execute_pending_tickets.\n\n"
    "Rules:\n"
    "  • Respond in the user's language.\n"
    "  • Be concise. No walls of text. No fake process-narration.\n"
    "  • Prefer calling a tool over asking the user to run something themselves.\n"
    "  • If a tool returns ERROR, tell the user what went wrong and what to do next.\n"
    "  • Use the Prior Session Context (if present) instead of re-asking for info."
)


def get_current_model(role: str = "ticket") -> str:
    if role == "coding":
        return os.environ.get("CODING_MODEL", DEFAULT_CODING_MODEL)
    return os.environ.get("TICKET_MODEL", DEFAULT_TICKET_MODEL)


def set_model(role: str, model: str) -> str:
    env_var = "CODING_MODEL" if role == "coding" else "TICKET_MODEL"
    os.environ[env_var] = model
    return model


def _build_llm(role: str):
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=get_current_model(role),
        temperature=0.3,
        streaming=True,
    )


def _extract_text(content: object) -> str:
    """Normalize a Gemini chunk's content into plain text (list-shape guard)."""
    if isinstance(content, list):
        return "".join(
            (item.get("text", "") if isinstance(item, dict) else str(item))
            for item in content
        )
    return str(content or "")


async def _stream_one_turn(
    llm_with_tools,
    messages: list[BaseMessage],
    project_id: str,
    parts: list[str],
) -> AIMessageChunk | None:
    """Stream one LLM turn, publishing text chunks. Returns the merged aggregate
    chunk (which carries any tool_calls the model produced)."""
    aggregate: AIMessageChunk | None = None
    async for chunk in llm_with_tools.astream(messages):
        text = _extract_text(getattr(chunk, "content", ""))
        if text:
            parts.append(text)
            await publish_event(project_id, "chat_chunk", {"delta": text})
        aggregate = chunk if aggregate is None else (aggregate + chunk)
    return aggregate


async def stream_chat_reply(
    project_id: str,
    preamble: str,
    user_message: str,
    project_getter: Callable[[], Awaitable[dict | None]],
) -> str:
    """Stream a tool-calling Gemini reply to the project's SSE channel.

    Returns the assembled assistant text so the caller can persist it.
    Emits: chat_start, chat_chunk*, chat_done | chat_error.
    """
    messages: list[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]
    if preamble:
        messages.append(SystemMessage(content=preamble))
    messages.append(HumanMessage(content=user_message))

    model_name = get_current_model("ticket")
    await publish_event(project_id, "chat_start", {"mode": "agent", "model": model_name})

    token_tracker.CURRENT_PROJECT_ID.set(project_id)
    token_tracker.CURRENT_SESSION_ID.set(f"chat-{project_id}")

    tools = build_tools(project_id, project_getter)
    tools_by_name = {t.name: t for t in tools}
    llm = _build_llm("ticket")
    llm_with_tools = llm.bind_tools(tools)

    parts: list[str] = []
    try:
        for iteration in range(MAX_TOOL_ITERATIONS):
            aggregate = await _stream_one_turn(llm_with_tools, messages, project_id, parts)
            if aggregate is None:
                break

            if aggregate is not None:
                try:
                    await token_tracker.record_llm_call(
                        aggregate, project_id=project_id, session_id=f"chat-{project_id}"
                    )
                except Exception as exc:
                    logger.warning("token_tracker.record_llm_call failed: %s", exc)

            tool_calls = getattr(aggregate, "tool_calls", None) or []
            if not tool_calls:
                break

            # Append the assistant's tool-call message before ToolMessages (LLM contract).
            messages.append(aggregate)

            for call in tool_calls:
                name = call.get("name")
                args = call.get("args") or {}
                call_id = call.get("id")
                await publish_event(
                    project_id,
                    "tool_call",
                    {"name": name, "args_preview": _preview_args(args)},
                )
                tool = tools_by_name.get(name)
                if tool is None:
                    result = f"ERROR: unknown tool '{name}'."
                else:
                    try:
                        result = await tool.ainvoke(args)
                    except Exception as exc:
                        logger.exception("tool %s failed", name)
                        result = f"ERROR: {exc}"
                await publish_event(
                    project_id,
                    "tool_result",
                    {"name": name, "result": str(result)[:400]},
                )
                messages.append(ToolMessage(content=str(result), tool_call_id=call_id))
        else:
            logger.warning("MAX_TOOL_ITERATIONS reached for %s", project_id)
    except Exception as exc:
        logger.exception("stream_chat_reply failed for project %s", project_id)
        err = f"LLM call failed: {exc}"
        await publish_event(project_id, "chat_error", {"error": err})
        return err

    full = "".join(parts).strip()
    await publish_event(project_id, "chat_done", {"content": full, "mode": "agent"})
    return full


def _preview_args(args: dict) -> dict:
    """Truncate long arg values so the SSE payload stays small."""
    out: dict = {}
    for k, v in args.items():
        s = str(v)
        out[k] = s if len(s) <= 120 else s[:120] + "…"
    return out
