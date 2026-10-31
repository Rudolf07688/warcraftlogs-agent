"""Fire-and-forget background tasks for the request path (guides, recent raids).

``spawn`` keeps a reference to each task so it isn't garbage-collected mid-run, and skips a
key that is already running in this process so a rapid repeat doesn't start two tasks for
one entry. Cross-instance coordination, where needed, is the caller's job (e.g. the recent
raids refresh claim in the database).

Each task runs in a fresh, empty context (sc-222): it never inherits the caller's context
variables, such as the chat turn's acting identity (``tenancy.context.current_identity``).
"""

from __future__ import annotations

import asyncio
import contextvars
from collections.abc import Coroutine, Hashable
from typing import Any

_bg_tasks: set[asyncio.Task] = set()
_inflight: set[Hashable] = set()


def spawn(coro: Coroutine[Any, Any, Any], key: Hashable) -> None:
    """Fire-and-forget a background task with GC-safe referencing + idempotency.

    No-op when there's no running loop (e.g. a sync unit test that isn't exercising
    the lifecycle) so scheduling never raises into the request path.
    """
    if key in _inflight:
        coro.close()  # discard the duplicate coroutine so it isn't left un-awaited
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        coro.close()
        return
    _inflight.add(key)
    task = loop.create_task(coro, context=contextvars.Context())
    _bg_tasks.add(task)

    def _done(t: asyncio.Task) -> None:
        _bg_tasks.discard(t)
        _inflight.discard(key)

    task.add_done_callback(_done)
