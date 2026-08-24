"""
Global execution lock (AD-2).

Provides a process-level asyncio.Lock that ensures no two ticket executions
run simultaneously — across any project in the same process.

Rules:
- Use asyncio.Lock (never threading.Lock) to avoid blocking the event loop (AD-9).
- get_execution_lock() is the single access point; returns the same instance every call.
- is_execution_running() is a convenience predicate for status checks and 409 guards.
"""
import asyncio

# Module-level singleton lock.  Re-assignable to `None` in tests to force re-creation.
_lock: asyncio.Lock | None = None


def get_execution_lock() -> asyncio.Lock:
    """Return the global execution asyncio.Lock, creating it on first call."""
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def is_execution_running() -> bool:
    """Return True if the global execution lock is currently held."""
    lock = get_execution_lock()
    return lock.locked()
