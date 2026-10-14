"""Thread helpers for the sync Warcraft Logs tools (QA PERF-001, PERF-002).

``off_loop`` wraps a sync tool as an async function that runs in a worker thread. ADK 2.x
calls sync tools inline on the event loop in SSE mode: its thread pool is live-mode only.
Without the wrapper, "parallel" tool calls would run one after another and block every
other request while waiting on WCL.

``gather_threads`` runs independent WCL requests inside one tool concurrently. Total HTTP
concurrency is capped separately by the client (``WCL_MAX_CONCURRENCY``).

Both carry the caller's contextvars into the worker thread, because the per-tenant WCL cache
scope lives in one (``cache._scope_prefix``).
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")


def off_loop(fn: Callable[..., T]) -> Callable[..., Awaitable[T]]:
    """Return an async wrapper that runs ``fn`` in a worker thread.

    ``functools.wraps`` keeps ``__name__``, ``__doc__``, annotations and ``__wrapped__``, so
    ADK builds the same tool declaration (and finds ``ToolContext``) as for ``fn`` itself.
    ``asyncio.to_thread`` copies the current contextvars into the thread.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        return await asyncio.to_thread(fn, *args, **kwargs)

    return wrapper


def gather_threads(
    calls: list[Callable[[], T]], max_workers: int = 4
) -> list[T | BaseException]:
    """Run ``calls`` concurrently and return their results in input order.

    An exception raised by a call is returned in its slot instead of being raised, so each
    caller keeps its own per-step error handling. Each call runs in its own copy of the
    caller's contextvars (pool workers don't inherit them).
    """
    if not calls:
        return []
    if len(calls) == 1:
        return [_capture(calls[0])]
    with ThreadPoolExecutor(max_workers=min(max_workers, len(calls))) as pool:
        futures = [pool.submit(contextvars.copy_context().run, _capture, c) for c in calls]
        return [f.result() for f in futures]


def unwrap(result: T | BaseException) -> T:
    """Re-raise a result captured by ``gather_threads``, or return it unchanged."""
    if isinstance(result, BaseException):
        raise result
    return result


def _capture(call: Callable[[], T]) -> T | BaseException:
    try:
        return call()
    except Exception as exc:  # noqa: BLE001 - handed back to the caller in its slot
        return exc
