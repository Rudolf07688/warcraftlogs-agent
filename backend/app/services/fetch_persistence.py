"""Write-through persistence of every Warcraft Logs response (feature 020).

The WCL client offers each successful response to a process-wide sink
(:func:`wcl_agent.client.wcl_client.set_fetch_sink`). In the app that sink is
:meth:`FetchWriter.offer`, which only enqueues; one background task upserts the queued
responses into ``raw_fetches``. The queue is bounded in items and bytes: when full, new
responses are dropped from storage (never from the caller) and counted in a throttled
warning. A persistence error is logged, never raised. See contracts/fetch-sink.md.

Only the app's lifespan starts a writer. The CLI, eval scripts and tests leave the sink
unset, so nothing is persisted there.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
from collections.abc import Awaitable, Callable

from wcl_agent.client import wcl_client
from wcl_agent.client.wcl_client import FetchedResponse

from ..db import session as db_session
from ..repositories.raw_fetches import upsert_raw_fetch

logger = logging.getLogger(__name__)

SHUTDOWN_GRACE_S = 5.0
_WRITE_TIMEOUT_S = 10.0  # a hung database costs one item this long; the queue absorbs the rest
_LOG_EVERY_S = 60.0


async def store_fetch(fetched: FetchedResponse) -> None:
    """Upsert one response in its own transaction."""
    async with db_session.SessionLocal() as session:
        await upsert_raw_fetch(session, fetched)
        await session.commit()


class _Throttle:
    """Counts events; logs a warning at most once per interval with the count since the last."""

    def __init__(self, message: str):
        self._message = message  # first %d is the count
        self._pending = 0
        self._last = -math.inf

    def hit(self, *args: object) -> None:
        self._pending += 1
        now = time.monotonic()
        if now - self._last >= _LOG_EVERY_S:
            logger.warning(self._message, self._pending, *args)
            self._pending = 0
            self._last = now


class FetchWriter:
    """Bounded queue + one consumer task writing fetched responses to the database."""

    def __init__(
        self,
        store: Callable[[FetchedResponse], Awaitable[None]] = store_fetch,
        *,
        max_items: int,
        max_bytes: int,
    ):
        self._store = store
        self._max_bytes = max_bytes
        self._queue: asyncio.Queue[FetchedResponse] = asyncio.Queue(maxsize=max(1, max_items))
        self._bytes = 0  # body bytes queued or being written
        self._busy = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        self.dropped = 0
        self._drops = _Throttle("fetch persistence: queue full, dropped %d response(s)")
        self._failures = _Throttle("fetch persistence: %d write(s) failed, last error: %r")

    def start(self) -> None:
        """Start the consumer on the running loop and install :meth:`offer` as the client sink."""
        self._loop = asyncio.get_running_loop()
        self._task = self._loop.create_task(self._run(), name="fetch-persistence")
        wcl_client.set_fetch_sink(self.offer)

    def offer(self, fetched: FetchedResponse) -> None:
        """The client sink: O(1), never awaits. Fetches on another thread hop to our loop."""
        loop = self._loop
        if loop is None:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._enqueue(fetched)
        else:
            loop.call_soon_threadsafe(self._enqueue, fetched)

    def _enqueue(self, fetched: FetchedResponse) -> None:
        size = len(fetched.content)
        if self._queue.full() or self._bytes + size > self._max_bytes:
            self.dropped += 1
            self._drops.hit()
            return
        self._bytes += size
        self._queue.put_nowait(fetched)

    async def _run(self) -> None:
        while True:
            fetched = await self._queue.get()
            self._busy = True
            try:
                async with asyncio.timeout(_WRITE_TIMEOUT_S):
                    await self._store(fetched)
            except Exception as exc:  # noqa: BLE001 - never reaches a caller (FR-007)
                self._failures.hit(exc)
            finally:
                self._busy = False
                self._bytes -= len(fetched.content)
                self._queue.task_done()

    async def stop(self, grace_s: float = SHUTDOWN_GRACE_S) -> None:
        """Stop accepting, give queued writes ``grace_s`` to finish, then drop the rest."""
        if wcl_client._fetch_sink == self.offer:
            wcl_client.set_fetch_sink(None)
        self._loop = None
        task, self._task = self._task, None
        if task is None:
            return
        try:
            await asyncio.wait_for(self._queue.join(), grace_s)
        except TimeoutError:
            left = self._queue.qsize() + int(self._busy)
            self.dropped += left
            logger.warning(
                "fetch persistence: stopped after %.1fs, dropped %d unwritten response(s)", grace_s, left
            )
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
