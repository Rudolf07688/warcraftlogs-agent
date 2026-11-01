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

Feature 045: the tenant scope is set once per tenant per transaction and a grant is rewritten
only when an hour older (PERF-005); each batch reports which items changed the stored payload
(:class:`BatchResult`, contract 5); and a fetch whose request was already under way when its
report went away is not written (sc-296, :data:`_tombstones`).

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
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import AsyncSession

from wcl_agent.cache.cache import evict_report
from wcl_agent.client import wcl_client
from wcl_agent.client.queries import REPORT_SUMMARY, report_summaries_query
from wcl_agent.client.wcl_client import (
    FetchedResponse,
    ReportGone,
    exact_report_codes,
    returned_report_code,
)

from ..db import session as db_session
from ..kb import indexer as kb_indexer
from ..repositories.raw_fetches import (
    GRANT_REFRESH,
    ReportStatus,
    delete_report,
    grant_codes,
    record_report_status,
    scope_tenant,
    stored_codes,
    upsert_raw_fetch,
)
from ..tenancy.context import current_identity

logger = logging.getLogger(__name__)

SHUTDOWN_GRACE_S = 5.0
_WRITE_TIMEOUT_S = 10.0  # per batch, then per item on retry; the queue absorbs the rest
_EVICT_TIMEOUT_S = 5.0  # Redis eviction of gone reports, outside the DB timeout
_LOG_EVERY_S = 60.0
_PARSE_OFF_LOOP_BYTES = 256_000  # like the WCL client: big bodies are parsed off the loop
BATCH_MAX = 20  # items per transaction (sc-177): one commit, bounded by the write timeout
BATCH_MAX_BYTES = 8 * 1024 * 1024  # and body bytes per transaction (041 fix 3)
# Gone or private reports this process saw (code -> when), so a fetch already under way then isn't
# written back afterwards (045 sc-296, 047 sc-322). Per process and lost on restart (045 FR-010).
# Kept well past the longest WCL query (75 s) plus queueing.
TOMBSTONE_TTL = timedelta(minutes=10)
TOMBSTONE_MAX = 1024
_tombstones: OrderedDict[str, datetime] = OrderedDict()


@dataclass(frozen=True)
class BatchResult:
    """One written batch: the gone reports (to evict from Redis) and the fetches whose stored
    payload changed (contract 5: 043's post-store hook)."""

    gone: list[str] = field(default_factory=list)
    changed: list[FetchedResponse] = field(default_factory=list)


@dataclass
class _Txn:
    """What one transaction already did: the tenant its scope is set to, and the grants it
    wrote (tenant, code) -> at, so neither is repeated per item (045 PERF-005)."""

    scoped: uuid.UUID | None = None
    granted: dict[tuple[uuid.UUID, str], datetime] = field(default_factory=dict)


def _bury(codes: Sequence[str], seen_at: datetime) -> None:
    for code in codes:
        if code not in _tombstones or seen_at > _tombstones[code]:
            _tombstones[code] = seen_at
            _tombstones.move_to_end(code)
    horizon = seen_at - TOMBSTONE_TTL
    while _tombstones and (len(_tombstones) > TOMBSTONE_MAX or next(iter(_tombstones.values())) < horizon):
        _tombstones.popitem(last=False)


def _stale(item: FetchedResponse) -> bool:
    """The fetch was requested before (or as) one of its reports was seen gone."""
    if item.requested_at is None or not _tombstones:
        return False
    codes = stored_codes(item.query, item.variables)
    return any((t := _tombstones.get(c)) is not None and item.requested_at <= t for c in codes)


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


async def _store_one(session: AsyncSession, pending: PendingWrite, txn: _Txn, result: BatchResult) -> None:
    """Write one item in the open transaction, adding to ``result``.

    Grants come from what WCL returned, never from the query text alone (041 fix 2, decision
    scope:041:grant-rule): our summary queries grant each code whose report object came back
    with that code; any other query grants its one code only when it is plain and its body
    holds the report (:func:`returned_report_code`). A fetch requested before one of its
    reports was seen gone or private writes nothing: not its row, its statuses or its grant (045
    sc-296, 047 sc-322).
    """
    item = pending.item
    if isinstance(item, ReportGone):
        _bury(item.codes, item.seen_at)
        for code in item.codes:
            await delete_report(session, code)
        result.gone.extend(item.codes)
        return
    if _stale(item):
        logger.info("fetch persistence: skipped a fetch requested before its report was gone")
        return
    if await upsert_raw_fetch(session, item):
        result.changed.append(item)
    codes = exact_report_codes(item.query, item.variables) or []
    gone: list[str] = []
    if codes and _is_summary(item, codes):
        statuses, gone = await _report_statuses(item, codes)
        _bury(gone, item.fetched_at)  # found private: a fetch already under way is stale too (sc-322)
        await record_report_status(session, statuses)
        for code in gone:
            await delete_report(session, code)
        result.gone.extend(gone)
        granted = [s.code for s in statuses]
    else:
        code = returned_report_code(item.query, item.variables, item.content)
        granted = [code] if code else []
    tenant = pending.tenant_id
    if tenant is None:
        return
    at = item.fetched_at
    fresh = [c for c in granted if (prev := txn.granted.get((tenant, c))) is None or at - prev >= GRANT_REFRESH]
    if not fresh:
        return
    if txn.scoped != tenant:
        # Grants are RLS'd per tenant; set_config(..., true) may be re-set inside a transaction.
        await scope_tenant(session, tenant)
        txn.scoped = tenant
    await grant_codes(session, tenant, fresh, at)
    txn.granted.update({(tenant, c): at for c in fresh})


async def store_batch(batch: Sequence[PendingWrite]) -> BatchResult:
    """Write queued items in one transaction. The gone reports' Redis keys are evicted by the
    writer after this timed DB part (041 fix 3). After the commit, each item whose stored payload
    changed goes to the knowledge base indexer (043; only enqueued, a no-op without one)."""
    result, txn = BatchResult(), _Txn()
    async with db_session.SessionLocal() as session:
        for pending in batch:
            await _store_one(session, pending, txn, result)
        await session.commit()
    for item in result.changed:
        kb_indexer.offer_fetch(item)
    return result


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


def _gone_of(result: BatchResult | list[str] | None) -> list[str]:
    """The gone codes of a store's result (an injected store may return just the codes)."""
    if isinstance(result, BatchResult):
        return list(result.gone)
    return list(result or [])


class FetchWriter:
    """Bounded queue + one consumer task writing fetched responses to the database."""

    def __init__(
        self,
        store: Callable[[Sequence[PendingWrite]], Awaitable[BatchResult | list[str] | None]] = store_batch,
        *,
        max_items: int,
        max_bytes: int,
    ):
        self._store = store
        self._max_bytes = max_bytes
        self._queue: asyncio.Queue[PendingWrite] = asyncio.Queue(maxsize=max(1, max_items))
        self._bytes = 0  # body bytes queued or being written
        self._busy = 0  # items being written
        self._carry: PendingWrite | None = None  # taken from the queue, too big for the last batch
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

    async def _next_batch(self) -> list[PendingWrite]:
        """Up to :data:`BATCH_MAX` items and :data:`BATCH_MAX_BYTES` (041 fix 3). The item that
        would overflow waits for the next batch; one oversize item still goes alone."""
        first, self._carry = self._carry, None
        batch = [first if first is not None else await self._queue.get()]
        size = batch[0].size
        while len(batch) < BATCH_MAX and not self._queue.empty():
            pending = self._queue.get_nowait()
            if size + pending.size > BATCH_MAX_BYTES:
                self._carry = pending
                break
            batch.append(pending)
            size += pending.size
        return batch

    async def _run(self) -> None:
        while True:
            batch = await self._next_batch()
            self._busy = len(batch)
            try:
                gone = await self._write(batch)
                if gone:
                    await self._evict(gone)
            finally:
                self._busy = 0
                for pending in batch:
                    self._bytes -= pending.size
                    self._queue.task_done()

    async def _write(self, batch: list[PendingWrite]) -> list[str]:
        """One transaction for the batch; on any error, a timeout included, each item alone, so
        one bad or slow item loses only itself and a ReportGone is never lost with the batch
        (041 fix 3). Order is kept. Returns the gone codes. Nothing ever reaches a caller."""
        try:
            async with asyncio.timeout(_WRITE_TIMEOUT_S):
                return _gone_of(await self._store(batch))
        except Exception as exc:  # noqa: BLE001 - TimeoutError too (FR-007)
            if len(batch) == 1:
                self._failures.hit(_describe(exc))
                return []
        gone: list[str] = []
        for pending in batch:
            try:
                async with asyncio.timeout(_WRITE_TIMEOUT_S):
                    gone += _gone_of(await self._store([pending]))
            except Exception as exc:  # noqa: BLE001
                self._failures.hit(_describe(exc))
        return gone

    async def _evict(self, codes: list[str]) -> None:
        """Gone reports leave the shared Redis cache, after (never inside) the timed DB write."""
        try:
            async with asyncio.timeout(_EVICT_TIMEOUT_S):
                for code in dict.fromkeys(codes):
                    await evict_report(code)
        except Exception as exc:  # noqa: BLE001 - eviction is best effort, like the cache
            logger.warning("fetch persistence: Redis eviction incomplete: %s", type(exc).__name__)

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
            left = self._queue.qsize() + self._busy + int(self._carry is not None)
            self.dropped += left
            logger.warning(
                "fetch persistence: stopped after %.1fs, dropped %d unwritten response(s)", grace_s, left
            )
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._drops.flush()
        self._failures.flush()
