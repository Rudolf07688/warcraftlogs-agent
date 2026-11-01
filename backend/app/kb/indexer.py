"""The knowledge base indexer: chunks new sources and embeds them in the background (feature 043).

Shaped like the 039 fetch writer: the ``offer_*`` hooks only enqueue (O(1), never await, never
raise) and one consumer task does the work, so no WCL fetch, guide run or chat turn ever waits
for it. Each job (a stored fetch whose body changed, a published guide, a finished exchange) is
chunked and written in its own short transaction, then the rows it left without a vector are
embedded (``RETRIEVAL_DOCUMENT``) in batches; the embedding call runs outside any transaction.

The chunk tables are the backlog: a NULL vector means "not embedded yet" (still keyword-
searchable). After an embedding failure the consumer stops embedding until the next sweep;
every ``kb_embed_sweep_s`` the sweep embeds whatever is still NULL: global rows directly, chat
rows workspace by workspace under that workspace's scope. A full queue drops the job (counted
in a throttled warning; the backfill recovers it). Only the app lifespan starts an indexer; the
CLI, evals and tests leave it unset, so the hooks do nothing there.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from wcl_agent.client.wcl_client import FetchedResponse, exact_report_codes

from ..db import session as db_session
from ..db.models import KbChatChunk, KbChunk, Tenant
from ..repositories.raw_fetches import load_fetch_for_index
from ..services import fetch_persistence  # module, not names: it imports this module too
from ..tenancy.context import tenant_scope
from . import store
from .chat_chunker import ExchangeJob, chunk_exchange
from .embedder import get_embedder
from .guide_chunker import GuideJob, chunk_guide
from .names import mentioned_characters
from .wcl_chunker import chunk_fetch, chunkable_query, needed_fights, source_from_query

logger = logging.getLogger(__name__)

SHUTDOWN_GRACE_S = 5.0
SWEEP_MAX_ROWS = 2_000  # per table and sweep, so a sweep never starves the queue for long
_PARSE_OFF_LOOP_BYTES = 256_000  # like the writer: big bodies are parsed off the loop



@dataclass(frozen=True)
class FetchJob:
    """A stored fetch to (re)chunk. Only the key and the query travel through the queue; the
    consumer reads the body from the store, so a queued job never holds a multi-MB response
    (P7 SEC-001)."""

    query_key: str
    query: str
    variables: dict
    report_codes: tuple[str, ...]


Job = FetchJob | GuideJob | ExchangeJob


@dataclass
class IndexerStats:
    dropped: int = 0
    failed: int = 0
    embedded: int = 0


class KbIndexer:
    """Bounded job queue + one consumer task that chunks, writes and embeds."""

    def __init__(self, *, max_items: int, batch: int, sweep_s: float):
        self._queue: asyncio.Queue[Job] = asyncio.Queue(maxsize=max(1, max_items))
        self._batch = max(1, batch)
        self._sweep_s = max(1.0, sweep_s)
        self._next_sweep = 0.0
        self._paused = False  # embedding failed: wait for the next sweep
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        self.stats = IndexerStats()
        self._drops = fetch_persistence._Throttle("knowledge base: queue full, dropped %d job(s)")
        self._failures = fetch_persistence._Throttle("knowledge base: %d job(s) failed, last error: %s")

    # --- lifecycle -----------------------------------------------------------------------

    def start(self) -> None:
        global _indexer
        self._loop = asyncio.get_running_loop()
        self._next_sweep = time.monotonic() + self._sweep_s
        self._task = self._loop.create_task(self._run(), name="kb-indexer")
        _indexer = self

    async def stop(self, grace_s: float = SHUTDOWN_GRACE_S) -> None:
        """Stop accepting, give queued jobs ``grace_s`` to finish, then drop the rest."""
        global _indexer
        if _indexer is self:
            _indexer = None
        self._loop = None
        task, self._task = self._task, None
        if task is None:
            return
        try:
            await asyncio.wait_for(self._queue.join(), grace_s)
        except TimeoutError:
            logger.warning("knowledge base: stopped with %d job(s) unindexed", self._queue.qsize())
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._drops.flush()
        self._failures.flush()

    def offer(self, job: Job) -> None:
        """O(1), never awaits; a job from another thread hops to our loop."""
        loop = self._loop
        if loop is None:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._enqueue(job)
        else:
            loop.call_soon_threadsafe(self._enqueue, job)

    def _enqueue(self, job: Job) -> None:
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            self.stats.dropped += 1
            self._drops.hit()

    # --- the consumer ----------------------------------------------------------------------

    async def _run(self) -> None:
        while True:
            wait = self._next_sweep - time.monotonic()
            try:
                job = await asyncio.wait_for(self._queue.get(), max(wait, 0.0)) if wait > 0 else None
            except TimeoutError:
                job = None
            if job is None:
                await self._safely(self.sweep())
                self._next_sweep = time.monotonic() + self._sweep_s
                continue
            try:
                await self._safely(self.handle(job))
            finally:
                self._queue.task_done()

    async def _safely(self, work) -> None:
        try:
            await work
        except Exception as exc:  # noqa: BLE001 - nothing ever reaches a caller (like the writer)
            self.stats.failed += 1
            self._failures.hit(fetch_persistence._describe(exc))

    async def handle(self, job: Job) -> None:
        """Chunk, write and embed one job (also called directly by tests)."""
        if isinstance(job, FetchJob):
            await self._index_fetch(job)
        elif isinstance(job, GuideJob):
            await self._index_guide(job)
        else:
            await self._index_exchange(job)

    async def _index_fetch(self, job: FetchJob) -> None:
        async with db_session.SessionLocal() as session:
            row = await load_fetch_for_index(session, job.query_key)
            if row is None:
                return  # gone (report gone or private): its chunks went with it (cascade)
            # The newest stored body for this key: a newer fetch since the offer only means its
            # own job finds nothing left to change.
            if len(row.body) > _PARSE_OFF_LOOP_BYTES:
                body = await asyncio.to_thread(json.loads, row.body)
            else:
                body = json.loads(row.body)
            source = source_from_query(job.query_key, job.query, job.variables, job.report_codes, body)
            code, fights = needed_fights(source)
            contexts = await store.fight_contexts(session, code, fights) if code else {}
            # Even no chunks is written: a body that now yields none must drop the old ones
            # (P7 SEC-002a).
            drafts = chunk_fetch(source, contexts)
            try:
                ids = await store.replace_source_chunks(session, drafts, raw_fetch_id=job.query_key)
                await session.commit()
            except IntegrityError:
                # The fetch row went (report gone or private) before we got here: nothing to keep.
                await session.rollback()
                return
        await self.embed(KbChunk, ids)

    async def _index_guide(self, job: GuideJob) -> None:
        drafts = chunk_guide(job)
        async with db_session.SessionLocal() as session:
            try:
                ids = await store.replace_source_chunks(session, drafts, guide_id=job.guide_id)
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return
        await self.embed(KbChunk, ids)

    async def _index_exchange(self, job: ExchangeJob) -> None:
        try:
            async with tenant_scope(job.tenant_id) as session:
                characters = await mentioned_characters(session, job.tenant_id, f"{job.question}\n{job.answer}")
                chunk_id = await store.upsert_chat_chunk(session, chunk_exchange(job, characters))
        except IntegrityError:
            return  # the conversation was deleted meanwhile
        if chunk_id is not None:
            await self.embed(KbChatChunk, [chunk_id], tenant_id=job.tenant_id)

    # --- embedding ---------------------------------------------------------------------------

    def _session(self, tenant_id: uuid.UUID | None):
        return tenant_scope(tenant_id) if tenant_id is not None else _committing(db_session.SessionLocal)

    async def embed(
        self, model: type[KbChunk] | type[KbChatChunk], ids: Sequence[uuid.UUID] | None = None,
        *, tenant_id: uuid.UUID | None = None, max_rows: int = SWEEP_MAX_ROWS,
    ) -> bool:
        """Embed rows of ``model`` without a vector (among ``ids``, else any, up to ``max_rows``).
        Returns False when embedding is unavailable or failed (the rows stay pending)."""
        if self._paused or (ids is not None and not ids):
            return not self._paused
        embedder = get_embedder()
        if embedder is None:
            return False
        done = 0
        remaining = list(ids) if ids is not None else None
        while done < max_rows:
            batch_ids = None
            if remaining is not None:
                batch_ids, remaining = remaining[: self._batch], remaining[self._batch :]
                if not batch_ids:
                    break
            async with self._session(tenant_id) as session:
                rows = await store.pending_rows(session, model, ids=batch_ids, tenant_id=tenant_id, limit=self._batch)
            if not rows:
                if remaining is None:
                    break
                continue
            try:
                vectors = await embedder.embed([r.text for r in rows], task="RETRIEVAL_DOCUMENT")
            except Exception as exc:  # noqa: BLE001 - rows stay NULL, keyword-searchable
                self._paused = True
                logger.warning("knowledge base: embedding failed (%s); retrying at the next sweep", type(exc).__name__)
                return False
            async with self._session(tenant_id) as session:
                self.stats.embedded += await store.store_vectors(session, model, rows, vectors, embedder.model)
            done += len(rows)
        return True

    async def sweep(self) -> None:
        """Embed what is still pending: global rows, then each workspace's chat rows."""
        self._paused = False
        if get_embedder() is None:
            return
        if not await self.embed(KbChunk):
            return
        async with db_session.SessionLocal() as session:
            tenants = list(await session.scalars(select(Tenant.id)))
        for tenant_id in tenants:
            if not await self.embed(KbChatChunk, tenant_id=tenant_id):
                return


@contextlib.asynccontextmanager
async def _committing(factory):
    async with factory() as session:
        yield session
        await session.commit()


_indexer: KbIndexer | None = None


def offer_fetch(fetched: FetchedResponse) -> None:
    """The writer's post-commit hook for a stored fetch whose body changed (contract 5).

    Only a fetch that can ever have chunks is queued: it names an exact report code (039 never
    serves the rest) and its query is one the chunker reads. The job carries no body."""
    if _indexer is None or not chunkable_query(fetched.query):
        return
    codes = exact_report_codes(fetched.query, fetched.variables)
    if codes:
        _indexer.offer(FetchJob(fetched.query_key, fetched.query, dict(fetched.variables), tuple(codes)))


def offer_guide(job: GuideJob) -> None:
    """The guide pipeline's hook after a publish commit."""
    if _indexer is not None:
        _indexer.offer(job)


def offer_exchange(job: ExchangeJob) -> None:
    """The chat socket's hook after a turn's final answer is saved."""
    if _indexer is not None:
        _indexer.offer(job)


__all__ = ["ExchangeJob", "FetchJob", "GuideJob", "KbIndexer", "offer_exchange", "offer_fetch", "offer_guide"]
