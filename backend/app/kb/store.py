"""Writes to the knowledge base chunk tables (feature 043): the one chunk writer, shared by the
background indexer and the backfill.

Nothing here serves chunks to a user (044's search does, through the visibility rule); the
reads are the writer's own bookkeeping: a source's existing keys and hashes, the fight context
for a table chunk, and the rows still waiting for a vector. Chat rows are written and read
inside the caller's tenant-scoped transaction (RLS), with an explicit tenant predicate too.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import KbChatChunk, KbChunk
from .chunks import ChatChunkDraft, ChunkDraft, PlayerRef
from .wcl_chunker import FightContext

ChunkModel = type[KbChunk] | type[KbChatChunk]


@dataclass(frozen=True)
class PendingRow:
    """A chunk waiting for its vector: what to embed and the hash it must still have."""

    id: uuid.UUID
    text: str
    content_hash: str


async def replace_source_chunks(
    session: AsyncSession,
    drafts: Sequence[ChunkDraft],
    *,
    raw_fetch_id: str | None = None,
    guide_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    """Make one source's chunks exactly ``drafts``: new keys inserted, changed text rewritten
    with its vector cleared, keys no longer produced deleted, unchanged rows (and their vectors)
    kept. Returns the ids of the source's rows that still need a vector. An FK error (the fetch
    or guide is gone) surfaces at flush/commit for the caller to drop."""
    if (raw_fetch_id is None) == (guide_id is None):
        raise ValueError("exactly one of raw_fetch_id / guide_id")
    kind, source = ("wcl", KbChunk.raw_fetch_id == raw_fetch_id) if raw_fetch_id else ("guide", KbChunk.guide_id == guide_id)
    existing = {
        row.chunk_key: row
        for row in (
            await session.execute(
                select(KbChunk.id, KbChunk.chunk_key, KbChunk.content_hash, KbChunk.embedding.is_(None)).where(source)
            )
        ).all()
    }
    wanted = {d.chunk_key: d for d in drafts}  # a repeated key keeps the last draft
    pending: list[uuid.UUID] = []
    for key, draft in wanted.items():
        row = existing.get(key)
        if row is None:
            chunk = KbChunk(kind=kind, raw_fetch_id=raw_fetch_id, guide_id=guide_id, **draft.columns())
            session.add(chunk)
            await session.flush()
            pending.append(chunk.id)
        elif row.content_hash != draft.content_hash:
            await session.execute(
                update(KbChunk)
                .where(KbChunk.id == row.id)
                .values(**draft.columns(), embedding=None, embed_model=None, embedded_at=None)
            )
            pending.append(row.id)
        elif row[3]:  # unchanged but never embedded
            pending.append(row.id)
    stale = [row.id for key, row in existing.items() if key not in wanted]
    if stale:
        await session.execute(delete(KbChunk).where(KbChunk.id.in_(stale)))
    return pending


async def upsert_chat_chunk(session: AsyncSession, draft: ChatChunkDraft) -> uuid.UUID | None:
    """Write one exchange's chunk in the caller's tenant-scoped transaction; returns its id when
    it needs a vector (new, changed, or never embedded), else None."""
    row = (
        await session.execute(
            select(KbChatChunk.id, KbChatChunk.content_hash, KbChatChunk.embedding.is_(None)).where(
                KbChatChunk.tenant_id == draft.tenant_id,
                KbChatChunk.conversation_id == draft.conversation_id,
                KbChatChunk.message_seq == draft.message_seq,
            )
        )
    ).first()
    if row is None:
        chunk = KbChatChunk(**draft.columns())
        session.add(chunk)
        await session.flush()
        return chunk.id
    if row.content_hash != draft.content_hash:
        await session.execute(
            update(KbChatChunk)
            .where(KbChatChunk.id == row.id)
            .values(**draft.columns(), embedding=None, embed_model=None, embedded_at=None)
        )
        return row.id
    return row.id if row[2] else None


def _players(raw: object) -> tuple[PlayerRef, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(
        PlayerRef(p["name"], p.get("key", ""), p.get("class"), p.get("spec"), p.get("id"))
        for p in raw
        if isinstance(p, dict) and isinstance(p.get("name"), str)
    )


async def fight_contexts(session: AsyncSession, report_code: str, fight_ids: Iterable[int]) -> dict[int, FightContext]:
    """What the report's fight-summary chunks say about these fights (for table chunks)."""
    ids = list(fight_ids)
    if not ids:
        return {}
    rows = await session.execute(
        select(
            KbChunk.fight_id, KbChunk.encounter_id, KbChunk.difficulty, KbChunk.kill, KbChunk.start_time,
            KbChunk.zone_id, KbChunk.guild, KbChunk.players, KbChunk.extra,
        ).where(
            KbChunk.kind == "wcl",
            KbChunk.report_code == report_code,
            KbChunk.fight_id.in_(ids),
            KbChunk.chunk_key.startswith(f"fight:{report_code}:"),
        )
    )
    contexts: dict[int, FightContext] = {}
    for row in rows:
        start = row.start_time
        contexts[row.fight_id] = FightContext(
            name=(row.extra or {}).get("fight_name"),
            encounter_id=row.encounter_id,
            difficulty=row.difficulty,
            kill=row.kill,
            start_time=start if start is None or start.tzinfo else start.replace(tzinfo=UTC),
            zone_id=row.zone_id,
            guild=row.guild,
            players=_players(row.players),
        )
    return contexts


async def pending_rows(
    session: AsyncSession, model: ChunkModel, *, ids: Sequence[uuid.UUID] | None = None,
    tenant_id: uuid.UUID | None = None, limit: int = 100,
) -> list[PendingRow]:
    """Rows of ``model`` without a vector: among ``ids`` when given, else any (chat rows of
    ``tenant_id`` only, which the caller's scope must match)."""
    stmt = select(model.id, model.text, model.content_hash).where(model.embedding.is_(None))
    if ids is not None:
        stmt = stmt.where(model.id.in_(list(ids)))
    if model is KbChatChunk:
        stmt = stmt.where(KbChatChunk.tenant_id == tenant_id)
    rows = await session.execute(stmt.order_by(model.id).limit(limit))
    return [PendingRow(r.id, r.text, r.content_hash) for r in rows]


async def store_vectors(
    session: AsyncSession, model: ChunkModel, rows: Sequence[PendingRow], vectors: Sequence[Sequence[float]],
    embed_model: str,
) -> int:
    """Store each row's vector, only where its text is still the one embedded (a re-chunk in
    between leaves the row pending for the next pass). Returns the rows updated."""
    now = datetime.now(UTC)
    stored = 0
    for row, vector in zip(rows, vectors, strict=True):
        result = await session.execute(
            update(model)
            .where(model.id == row.id, model.content_hash == row.content_hash)
            .values(embedding=list(vector), embed_model=embed_model, embedded_at=now)
        )
        stored += result.rowcount or 0
    return stored


async def indexed_fetch_ids(session: AsyncSession, raw_fetch_ids: Sequence[str]) -> set[str]:
    """Which of these fetches already have chunks (the backfill skips them)."""
    if not raw_fetch_ids:
        return set()
    rows = await session.scalars(
        select(KbChunk.raw_fetch_id).where(KbChunk.raw_fetch_id.in_(list(raw_fetch_ids))).distinct()
    )
    return set(rows)


async def indexed_guide_ids(session: AsyncSession) -> set[uuid.UUID]:
    """Guides that already have chunks (the backfill skips them)."""
    return set(await session.scalars(select(KbChunk.guide_id).where(KbChunk.guide_id.is_not(None)).distinct()))


async def indexed_exchanges(session: AsyncSession, tenant_id: uuid.UUID) -> set[tuple[uuid.UUID, int]]:
    """(conversation, answer seq) pairs of this workspace that already have a chunk."""
    rows = await session.execute(
        select(KbChatChunk.conversation_id, KbChatChunk.message_seq).where(KbChatChunk.tenant_id == tenant_id)
    )
    return {(r[0], r[1]) for r in rows}


async def pending_totals(
    session: AsyncSession, model: ChunkModel, *, tenant_id: uuid.UUID | None = None
) -> tuple[int, int]:
    """(rows, characters) still waiting for a vector (chat: this workspace's)."""
    stmt = select(func.count(), func.coalesce(func.sum(func.length(model.text)), 0)).where(model.embedding.is_(None))
    if model is KbChatChunk:
        stmt = stmt.where(KbChatChunk.tenant_id == tenant_id)
    count, chars = (await session.execute(stmt)).one()
    return int(count), int(chars)
