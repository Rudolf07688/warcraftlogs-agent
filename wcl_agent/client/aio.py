"""Async concurrency helpers for the Warcraft Logs tools (feature 013, PERF-201).

``gather_settled`` runs independent WCL requests inside one tool concurrently on the event
loop, replacing the thread-based ``gather_threads``. Total HTTP concurrency is capped by the
client's lane limiter, not here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")


async def gather_settled(*aws: Awaitable[T]) -> list[T | BaseException]:
    """Await ``aws`` concurrently and return their results in input order.

    An exception raised by one awaitable is returned in its slot instead of being raised, so
    each caller keeps its own per-step error handling. Cancelling the caller cancels every
    child (``asyncio.gather`` semantics).
    """
    if not aws:
        return []
    return await asyncio.gather(*aws, return_exceptions=True)


def unwrap(result: T | BaseException) -> T:
    """Re-raise a result captured by ``gather_settled``, or return it unchanged."""
    if isinstance(result, BaseException):
        raise result
    return result
