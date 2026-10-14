"""Thread helpers for the sync Warcraft Logs tools (QA PERF-001, PERF-002).

``off_loop`` wraps a sync tool as an async function that runs in a worker thread. ADK 2.x
calls sync tools inline on the event loop in SSE mode: its thread pool is live-mode only.
Without the wrapper, "parallel" tool calls would run one after another and block every
other request while waiting on WCL.

Tool calls run on a dedicated pool (``WCL_TOOL_THREADS``, default 32), not asyncio's shared
default executor: a slow WCL call must not hold a worker that short jobs on the chat path
(scratch writes, PDF rendering, DNS lookups) are waiting for (PERF-101). Other WCL calls
made from async code use ``run_in_tool_pool`` for the same reason.

``gather_threads`` runs independent WCL requests inside one tool concurrently. Total HTTP
concurrency is capped separately by the client (``WCL_MAX_CONCURRENCY``).

Both carry the caller's contextvars into the worker thread, because the per-tenant WCL cache
scope lives in one (``cache._scope_prefix``).
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import threading
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from .cache import _env_int

T = TypeVar("T")

# Comfortably above WCL_MAX_CONCURRENCY: workers waiting on the HTTP cap or on another
# thread's identical query (single-flight) must not starve each other.
DEFAULT_TOOL_THREADS = 32
_tool_pool: ThreadPoolExecutor | None = None
_tool_pool_lock = threading.Lock()


def _get_tool_pool() -> ThreadPoolExecutor:
    global _tool_pool
    if _tool_pool is None:
        with _tool_pool_lock:
            if _tool_pool is None:
                _tool_pool = ThreadPoolExecutor(
                    max_workers=max(1, _env_int("WCL_TOOL_THREADS", DEFAULT_TOOL_THREADS)),
                    thread_name_prefix="wcl-tool",
                )
    return _tool_pool


async def run_in_tool_pool(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run ``fn`` on the dedicated WCL thread pool with the caller's contextvars."""
    loop = asyncio.get_running_loop()
    call = functools.partial(fn, *args, **kwargs)
    return await loop.run_in_executor(_get_tool_pool(), contextvars.copy_context().run, call)


def off_loop(fn: Callable[..., T]) -> Callable[..., Awaitable[T]]:
    """Return an async wrapper that runs ``fn`` in a worker thread.

    ``functools.wraps`` keeps ``__name__``, ``__doc__``, annotations and ``__wrapped__``, so
    ADK builds the same tool declaration (and finds ``ToolContext``) as for ``fn`` itself.
    The call runs on the dedicated tool pool with the current contextvars copied in.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        return await run_in_tool_pool(fn, *args, **kwargs)

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
