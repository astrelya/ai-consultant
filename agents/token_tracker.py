"""Token consumption recorder for LLM `.ainvoke` call sites (Story 6.1 / FR-25).

Wiring contract:
- ``CURRENT_PROJECT_ID`` / ``CURRENT_SESSION_ID`` are ``contextvars.ContextVar``s
  set once at the top of ``SupervisorAgent.run_tickets`` and once per chat turn
  in ``main_agent.SupervisorAgent.process_chat``. Every ``await`` chain launched
  from those methods inherits the same ``Context`` (PEP 567), so downstream
  sub-agents never need to receive ``project_id`` explicitly to record cost.
- ``tracked_ainvoke`` is the single wrapper imported by every LLM call site. It
  is a thin adapter over ``await executor.ainvoke(payload)`` and never mutates
  the return value.

Pricing note:
- ``COST_PER_1K_TOKENS`` env var overrides the default $0.00015/1K tokens
  (Gemini 2.5 Flash published input price as of 2026-Q3). This is a single
  blended rate; a v2 story can split input vs output pricing. A malformed env
  value falls back to the default and logs a warning — it never raises.

AC-9 (no circular imports): this module MUST only depend on
``backend.store.project_store`` and ``backend.api.sse``. It MUST NOT import
from ``agents.*``.
"""
from __future__ import annotations

import contextvars
import logging
import os
from typing import Any

from backend.api.sse import publish_event
from backend.store import project_store

logger = logging.getLogger(__name__)

_DEFAULT_COST_PER_1K = 0.00015

CURRENT_PROJECT_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "CURRENT_PROJECT_ID", default=None
)
CURRENT_SESSION_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "CURRENT_SESSION_ID", default=None
)

# Process-local in-memory session counter. Persistence lives in `cost_ledger`;
# this map only backs the SSE `token_update` payload's `session_*` fields.
_SESSION_TOTALS: dict[str, dict] = {}


def compute_cost_usd(total_tokens: int) -> float:
    """Return the USD cost for *total_tokens* at the configured per-1K rate.

    Reads ``COST_PER_1K_TOKENS`` from the environment. Malformed values fall
    back to the hard-coded default and log a warning — this function NEVER
    raises. Rounded to 6 decimal places to match ledger precision.
    """
    raw = os.environ.get("COST_PER_1K_TOKENS", str(_DEFAULT_COST_PER_1K))
    try:
        price = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "COST_PER_1K_TOKENS=%r is not a valid float — falling back to %s",
            raw,
            _DEFAULT_COST_PER_1K,
        )
        price = _DEFAULT_COST_PER_1K
    return round(total_tokens / 1000.0 * price, 6)


def _extract_tokens_from_result(result: Any) -> tuple[int, int]:
    """Sum ``input_tokens`` / ``output_tokens`` across every AI message.

    Handles two shapes:
    - ReAct return: ``{"messages": [AIMessage, ...]}`` — iterate all messages.
    - Direct LLM return: single ``AIMessage`` with ``.usage_metadata``.

    NEVER raises. Unknown shapes return ``(0, 0)``.
    """
    prompt = 0
    completion = 0
    try:
        if isinstance(result, dict) and "messages" in result:
            for msg in result.get("messages") or []:
                usage = getattr(msg, "usage_metadata", None)
                if not usage:
                    continue
                prompt += int(usage.get("input_tokens", 0) or 0)
                completion += int(usage.get("output_tokens", 0) or 0)
            return prompt, completion
        usage = getattr(result, "usage_metadata", None)
        if usage:
            prompt = int(usage.get("input_tokens", 0) or 0)
            completion = int(usage.get("output_tokens", 0) or 0)
    except Exception as exc:  # noqa: BLE001 — defensive: extraction must never break the call.
        logger.warning("token extraction failed: %s", exc)
        return 0, 0
    return prompt, completion


async def record_llm_call(
    result: Any,
    *,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Record token usage for a single LLM invocation to the project's cost ledger.

    Returns a summary dict, or ``{"skipped": True, "reason": "no_project_id"}``
    when no project context is available (e.g. an LLM call fired outside any
    supervised run). This function NEVER raises — SSE plumbing and DB failures
    are swallowed so the caller's own result path is preserved.
    """
    pid = project_id if project_id is not None else CURRENT_PROJECT_ID.get()
    if pid is None:
        return {"skipped": True, "reason": "no_project_id"}

    sid = session_id if session_id is not None else CURRENT_SESSION_ID.get()
    if sid is None:
        sid = "__no_session__"

    prompt_tokens, completion_tokens = _extract_tokens_from_result(result)
    total_tokens = prompt_tokens + completion_tokens
    cost_usd = compute_cost_usd(total_tokens)

    totals = _SESSION_TOTALS.setdefault(sid, {"tokens": 0, "cost_usd": 0.0})
    totals["tokens"] += total_tokens
    totals["cost_usd"] = round(totals["cost_usd"] + cost_usd, 6)

    try:
        ledger = await project_store.add_cost_ledger_entry(
            pid, prompt_tokens, completion_tokens, cost_usd
        )
    except Exception as exc:  # noqa: BLE001 — never break the LLM call path.
        logger.warning("add_cost_ledger_entry failed for project %s: %s", pid, exc)
        ledger = {}

    ledger_total_tokens = int(ledger.get("total_tokens", 0) or 0) if ledger else 0
    ledger_total_cost = float(ledger.get("total_cost_usd", 0.0) or 0.0) if ledger else 0.0

    payload = {
        "session_tokens": totals["tokens"],
        "session_cost_usd": totals["cost_usd"],
        "total_tokens": ledger_total_tokens,
        "total_cost_usd": ledger_total_cost,
    }
    try:
        await publish_event(pid, "token_update", payload)
    except Exception as exc:  # noqa: BLE001 — SSE must never break the LLM path.
        logger.warning("publish_event(token_update) failed for project %s: %s", pid, exc)

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
        "session_tokens": totals["tokens"],
        "session_cost_usd": totals["cost_usd"],
        "total_tokens_project": ledger_total_tokens,
        "total_cost_usd_project": ledger_total_cost,
    }


async def tracked_ainvoke(
    executor: Any,
    payload: Any,
    *,
    project_id: str | None = None,
    session_id: str | None = None,
) -> Any:
    """Await ``executor.ainvoke(payload)`` and record its token usage.

    This is the ONLY new callable that LLM call sites import. The raw
    ``result`` is returned untouched.
    """
    result = await executor.ainvoke(payload)
    await record_llm_call(result, project_id=project_id, session_id=session_id)
    return result


def reset_session(session_id: str) -> None:
    """Reset the in-memory counter for *session_id*. NEVER touches ``cost_ledger``."""
    _SESSION_TOTALS[session_id] = {"tokens": 0, "cost_usd": 0.0}
