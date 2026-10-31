"""Write-through persistence of every Warcraft Logs response (feature 020).

The WCL client offers each successful response to a process-wide sink
(:func:`wcl_agent.client.wcl_client.set_fetch_sink`). In the app that sink is
:meth:`FetchWriter.offer`, which only enqueues; one background task upserts the queued
responses into ``raw_fetches``. The queue is bounded in items and bytes: when full, new
responses are dropped from storage (never from the caller) and counted in a throttled
warning. Up to :data:`BATCH_MAX` queued items are written per transaction (feature 039). A
persistence error is logged (class and SQLSTATE only), never raised. See
specs/020-fetch-persistence/contracts/fetch-sink.md and 039 contracts/raw-store.md.

Feature 039: each queued item carries the tenant of the chat turn that fetched it, so a
successful fetch grants its report codes to that tenant, and summary bodies record each
report's visibility and end time. A :class:`ReportGone` (WCL answered ``report: null``) goes
through the same FIFO queue and deletes the report's stored rows, then evicts its Redis keys
(specs/039-local-first-data/contracts/raw-store.md W6/W7).

Only the app's lifespan starts a writer. The CLI, eval scripts and tests leave the sink
unset, so nothing is persisted there.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import AsyncSession

from wcl_agent.cache.cache import evict_report
from wcl_agent.client import wcl_client
from wcl_agent.client.queries import REPORT_SUMMARY, report_summaries_query
from wcl_agent.client.wcl_client import FetchedResponse, ReportGone, exact_report_codes

from ..db import session as db_session
from ..repositories.raw_fetches import (
    ReportStatus,
    delete_report,
    grant_codes,
    record_report_status,
    upsert_raw_fetch,
)
from ..tenancy.context import current_identity, set_scope

logger = logging.getLogger(__name__)

SHUTDOWN_GRACE_S = 5.0
_WRITE_TIMEOUT_S = 10.0  # a hung database costs one item this long; the queue absorbs the rest
_LOG_EVERY_S = 60.0
_PARSE_OFF_LOOP_BYTES = 256_000  # like the WCL client: big bodies are parsed off the loop
BATCH_MAX = 20  # items per transaction (sc-177): one commit, bounded by the write timeout


@dataclass(frozen=True)
class PendingWrite:
    """One queued item and the tenant whose chat turn fetched it (None outside a turn)."""

    item: FetchedResponse | ReportGone
    tenant_id: uuid.UUID | None = None

    @property
    def size(self) -> int:
        return len(self.item.content) if isinstance(self.item, FetchedResponse) else 0


def _is_summary(fetched: FetchedResponse, codes: list[str]) -> bool:
    """Only our own summary queries may state a report's visibility: a hand-written query
    could alias another field (``code: title``) to forge one (research R3)."""
    return fetched.query in (REPORT_SUMMARY, report_summaries_query(len(codes)))


async def _report_statuses(
    fetched: FetchedResponse, codes: list[str]
) -> tuple[list[ReportStatus], list[str]]:
    """(statuses, private codes) from a summary body's ``reportData`` report objects."""
    if len(fetched.content) > _PARSE_OFF_LOOP_BYTES:
        body = await asyncio.to_thread(json.loads, fetched.content)
    else:
        body = json.loads(fetched.content)
    reports = ((body.get("data") or {}).get("reportData")) or {}
    statuses: list[ReportStatus] = []
    private: list[str] = []
    for report in reports.values():
        code = report.get("code") if isinstance(report, dict) else None
        if not isinstance(code, str) or code not in codes:
            continue
        visibility, end = report.get("visibility"), report.get("endTime")
        if visibility == "private":
            private.append(code)
            continue
        statuses.append(
            ReportStatus(
                code,
                visibility if isinstance(visibility, str) else None,
                end if isinstance(end, int) else None,
                fetched.fetched_at,
            )
        )
    return statuses, private


async def _store_one(session: AsyncSession, pending: PendingWrite) -> list[str]:
    """Write one item in the open transaction; returns the codes whose Redis keys must go."""
    item = pending.item
    if isinstance(item, ReportGone):
        for code in item.codes:
            await delete_report(session, code)
        return list(item.codes)
    await upsert_raw_fetch(session, item)
    codes = exact_report_codes(item.query, item.variables) or []
    gone: list[str] = []
    if codes and _is_summary(item, codes) and b'"visibility"' in item.content:
        statuses, gone = await _report_statuses(item, codes)
        await record_report_status(session, statuses)
        for code in gone:
            await delete_report(session, code)
    granted = [c for c in codes if c not in gone]
    if pending.tenant_id is not None and granted:
        # Grants are RLS'd per tenant; set_config(..., true) may be re-set inside a transaction.
        await set_scope(session, tenant_id=pending.tenant_id)
        await grant_codes(session, pending.tenant_id, granted, item.fetched_at)
    return gone


async def store_batch(batch: Sequence[PendingWrite]) -> None:
    """Write queued items in one transaction, then evict the Redis keys of gone reports."""
    gone: list[str] = []
    async with db_session.SessionLocal() as session:
        for pending in batch:
            gone += await _store_one(session, pending)
        await session.commit()
    for code in dict.fromkeys(gone):
        await evict_report(code)


def _describe(exc: BaseException) -> str:
    """A failure, safe to log: a database error's text and repr carry the statement's bound
    parameters (query params, payload), so only its class and SQLSTATE are kept (sc-177)."""
    if isinstance(exc, StatementError):
        orig = exc.orig
        state = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
        inner = type(orig).__name__ if orig is not None else "-"
        return f"{type(exc).__name__}({inner}{f', sqlstate {state}' if state else ''})"
    return repr(exc)


class _Throttle:
    """Counts events; logs a warning at most once per interval with the count since the last."""

    def __init__(self, message: str):
        self._message = message  # first %d is the count
        self._pending = 0
        self._args: tuple[object, ...] = ()
        self._last = -math.inf

    def hit(self, *args: object) -> None:
        self._pending += 1
        self._args = args
        now = time.monotonic()
        if now - self._last >= _LOG_EVERY_S:
            logger.warning(self._message, self._pending, *args)
            self._pending = 0
            self._last = now

    def flush(self) -> None:
        """Log the count still waiting for its interval (on stop, so it is never lost)."""
        if self._pending:
            logger.warning(self._message, self._pending, *self._args)
            self._pending = 0


class FetchWriter:
    """Bounded queue + one consumer task writing fetched responses to the database."""

    def __init__(
        self,
        store: Callable[[Sequence[PendingWrite]], Awaitable[None]] = store_batch,
        *,
        max_items: int,
        max_bytes: int,
    ):
        self._store = store
        self._max_bytes = max_bytes
        self._queue: asyncio.Queue[PendingWrite] = asyncio.Queue(maxsize=max(1, max_items))
        self._bytes = 0  # body bytes queued or being written
        self._busy = 0  # items being written
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        self.dropped = 0
        self._drops = _Throttle("fetch persistence: queue full, dropped %d response(s)")
        self._failures = _Throttle("fetch persistence: %d write(s) failed, last error: %s")

    def start(self) -> None:
        """Start the consumer on the running loop and install :meth:`offer` as the client sink."""
        self._loop = asyncio.get_running_loop()
        self._task = self._loop.create_task(self._run(), name="fetch-persistence")
        wcl_client.set_fetch_sink(self.offer)

    def offer(self, item: FetchedResponse | ReportGone) -> None:
        """The client sink: O(1), never awaits. Fetches on another thread hop to our loop.

        The tenant is read here, in the fetching task's context (the chat turn's identity).
        """
        loop = self._loop
        if loop is None:
            return
        identity = current_identity.get()
        pending = PendingWrite(item, identity.tenant_id if identity is not None else None)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._enqueue(pending)
        else:
            loop.call_soon_threadsafe(self._enqueue, pending)

    def _enqueue(self, pending: PendingWrite) -> None:
        size = pending.size
        if self._queue.full() or self._bytes + size > self._max_bytes:
            self.dropped += 1
            self._drops.hit()
            return
        self._bytes += size
        self._queue.put_nowait(pending)

    async def _run(self) -> None:
        while True:
            batch = [await self._queue.get()]
            while len(batch) < BATCH_MAX and not self._queue.empty():
                batch.append(self._queue.get_nowait())
            self._busy = len(batch)
            try:
                await self._write(batch)
            finally:
                self._busy = 0
                for pending in batch:
                    self._bytes -= pending.size
                    self._queue.task_done()

    async def _write(self, batch: list[PendingWrite]) -> None:
        """One transaction for the batch; on an error (not a hung database) each item alone,
        so one bad item loses only itself. Nothing ever reaches a caller (FR-007)."""
        try:
            async with asyncio.timeout(_WRITE_TIMEOUT_S):
                await self._store(batch)
            return
        except TimeoutError as exc:
            for _ in batch:
                self._failures.hit(_describe(exc))
            return
        except Exception as exc:  # noqa: BLE001
            if len(batch) == 1:
                self._failures.hit(_describe(exc))
                return
        for pending in batch:
            try:
                async with asyncio.timeout(_WRITE_TIMEOUT_S):
                    await self._store([pending])
            except Exception as exc:  # noqa: BLE001
                self._failures.hit(_describe(exc))

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
            left = self._queue.qsize() + self._busy
            self.dropped += left
            logger.warning(
                "fetch persistence: stopped after %.1fs, dropped %d unwritten response(s)", grace_s, left
            )
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._drops.flush()
        self._failures.flush()
