"""Hybrid knowledge search (feature 044, sc-114): specs/044-kb-search/contracts/search-knowledge.md.

Each query is one hybrid search: the top :data:`LEG_LIMIT` chunks by cosine distance to its
``RETRIEVAL_QUERY`` embedding and the top :data:`LEG_LIMIT` by keyword rank, fused by
reciprocal rank fusion (``1/(RRF_K + rank)``). The queries of one call run concurrently, each
in its own session, and are fused again across queries, then deduplicated by source. Soft
filters relax in :data:`RELAX_ORDER` while fewer than ``k`` hits come back, and the result is
capped at :data:`OUTPUT_CAP` characters, because it goes straight into the model's context.

Visibility lives in the SQL of every leg (the query runner): WCL chunks only through the 039
rule's one definition, chat chunks only under the workspace's row-level security, guides
globally. Nothing here post-filters, so no filter can widen what a workspace sees.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, Integer, String, Text, and_, cast, func, literal, null, or_, select, text, union_all
from sqlalchemy.dialects.postgresql import JSONB, REGCONFIG, TSQUERY
from sqlalchemy.sql.elements import ColumnElement

from ..config import settings
from ..db import session as db_session
from ..db.models import KB_DIMENSIONS, KbChatChunk, KbChunk
from ..repositories.raw_fetches import fetch_visible_clause
from ..services.name_resolver import ClassSpec, spec_pairs
from ..tenancy.context import set_scope
from .embedder import Embedder

logger = logging.getLogger(__name__)

Kind = Literal["wcl", "guide", "chat"]
Leg = Literal["vector", "keyword"]
Mode = Literal["hybrid", "vector", "keyword"]
SoftFilter = Literal["spec", "class_name", "encounter", "dates"]

KINDS: tuple[Kind, ...] = ("wcl", "guide", "chat")
RELAX_ORDER: tuple[SoftFilter, ...] = ("spec", "class_name", "encounter", "dates")
LEG_LIMIT = 40  # candidates per leg and query
RRF_K = 60
DEFAULT_K = 8
MAX_K = 15
MAX_QUERIES = 5
MAX_QUERY_CHARS = 300
HIT_TEXT_CHARS = 400
OUTPUT_CAP = 6000  # characters of the serialised tool result
EMBED_TIMEOUT_S = 3.0
SEARCH_TIMEOUT_S = 8.0

KEYWORD_ONLY_NOTE = "Semantic search is unavailable right now; these are keyword matches only."
NO_HITS_NOTE = "No stored knowledge matched. Use the Warcraft Logs tools for this question."


@dataclass(frozen=True)
class SearchFilters:
    """Resolved filter values (never raw agent text). ``until`` is an exclusive bound."""

    kind: Kind | None = None
    report_code: str | None = None
    class_name: str | None = None
    spec: str | None = None
    encounter_id: int | None = None
    difficulty: int | None = None
    character_key: str | None = None
    since: datetime | None = None
    until: datetime | None = None

    def soft_present(self) -> list[SoftFilter]:
        present = {
            "spec": self.spec is not None,
            "class_name": self.class_name is not None,
            "encounter": self.encounter_id is not None,
            "dates": self.since is not None or self.until is not None,
        }
        return [name for name in RELAX_ORDER if present[name]]

    def without(self, name: SoftFilter) -> SearchFilters:
        if name == "dates":
            return replace(self, since=None, until=None)
        if name == "encounter":
            return replace(self, encounter_id=None)
        return replace(self, **{name: None})

    def pairs(self) -> tuple[ClassSpec, ...]:
        """The (class, spec) pairs a spec filter matches; empty without a spec."""
        return spec_pairs(self.spec, self.class_name) if self.spec else ()


@dataclass(frozen=True)
class SearchRequest:
    queries: tuple[str, ...]
    filters: SearchFilters
    hard: frozenset[SoftFilter]  # soft filters the user stated, so never relaxed
    k: int
    tenant_id: uuid.UUID


@dataclass(frozen=True)
class Candidate:
    """One row of one leg. ``source_key`` identifies the source for deduplication; ``source``
    is the pointer the agent sees."""

    chunk_id: str
    kind: Kind
    text: str
    source_key: tuple
    source: dict[str, Any] = field(hash=False)
    leg: Leg = "keyword"
    rank: int = 1


@dataclass(frozen=True)
class Hit:
    kind: Kind
    source: dict[str, Any]
    text: str
    score: float
    relaxed: bool = False


@dataclass(frozen=True)
class SearchResult:
    hits: list[Hit]
    mode: Literal["hybrid", "keyword_only", "vector", "keyword"]
    relaxed: list[SoftFilter]
    capped: bool = False
    note: str | None = None


# (query, its vector or None, filters, tenant, legs) -> the candidates of those legs
QueryRunner = Callable[
    [str, list[float] | None, SearchFilters, uuid.UUID, frozenset[Leg]], Awaitable[list[Candidate]]
]


class SearchUnavailable(RuntimeError):
    """The database can't run knowledge search (not Postgres)."""


# --- The SQL legs -----------------------------------------------------------------------
#
# One statement per query: a UNION ALL of branches, one per (kind, leg), each with its own
# ORDER BY ... LIMIT so the HNSW and GIN indexes serve it. Every branch carries its kind's
# visibility predicate; filters are ANDed onto it, so no filter can widen the scope.


def _tsquery(config: str, query: str) -> ColumnElement:
    """The query's lexemes OR-ed: natural questions rarely contain every word of a chunk.
    ``plainto_tsquery`` sanitises the text (a bound parameter); ``config`` is a constant."""
    plain = func.plainto_tsquery(cast(literal(config), REGCONFIG), query)
    return cast(func.replace(cast(plain, Text), " & ", " | "), TSQUERY)


def _contains(column, value: list[dict[str, str]]) -> ColumnElement[bool]:
    return column.op("@>")(literal(value, JSONB))


def _class_spec(filters: SearchFilters, class_col, spec_col, players=None) -> list[ColumnElement]:
    """The class/spec filter for one table; ``players`` also matches any player in a WCL chunk."""
    if filters.spec:
        options = []
        for pair in filters.pairs():
            options.append(and_(class_col == pair.class_name, spec_col == pair.spec))
            if players is not None:
                options.append(_contains(players, [{"class": pair.class_name, "spec": pair.spec}]))
        return [or_(*options)]
    if filters.class_name:
        options = [class_col == filters.class_name]
        if players is not None:
            options.append(_contains(players, [{"class": filters.class_name}]))
        return [or_(*options)]
    return []


def _dates(filters: SearchFilters, column) -> list[ColumnElement]:
    out = []
    if filters.since is not None:
        out.append(column >= filters.since)
    if filters.until is not None:
        out.append(column < filters.until)
    return out


def _chunk_where(kind: Kind, filters: SearchFilters, tenant_id: uuid.UUID, since: datetime) -> list:
    """Visibility first, then the filters that apply to ``kind`` (spec: filter applicability)."""
    if kind == "guide":
        return [KbChunk.kind == "guide", *_class_spec(filters, KbChunk.class_name, KbChunk.spec)]
    where = [
        KbChunk.kind == "wcl",
        fetch_visible_clause(KbChunk.raw_fetch_id, tenant_id=tenant_id, since=since),
        *_class_spec(filters, KbChunk.class_name, KbChunk.spec, KbChunk.players),
        *_dates(filters, KbChunk.start_time),
    ]
    if filters.report_code is not None:
        where.append(KbChunk.report_code == filters.report_code)
    if filters.encounter_id is not None:
        where.append(KbChunk.encounter_id == filters.encounter_id)
    if filters.difficulty is not None:
        where.append(KbChunk.difficulty == filters.difficulty)
    if filters.character_key is not None:
        where.append(_contains(KbChunk.players, [{"key": filters.character_key}]))
    return where


def _chat_where(filters: SearchFilters, tenant_id: uuid.UUID) -> list:
    # RLS scopes the session; the explicit predicate is defence in depth.
    where = [KbChatChunk.tenant_id == tenant_id, *_dates(filters, KbChatChunk.created_at)]
    if filters.character_key is not None:
        where.append(_contains(KbChatChunk.characters, [{"key": filters.character_key}]))
    return where


def _chunk_columns(kind: Kind) -> list:
    return [
        cast(KbChunk.id, String).label("id"), literal(kind).label("kind"), KbChunk.text,
        KbChunk.label, KbChunk.report_code, KbChunk.fight_id, cast(KbChunk.guide_id, String).label("guide_id"),
        KbChunk.class_name, KbChunk.spec, KbChunk.content_type, KbChunk.section,
        cast(null(), String).label("conversation_id"), cast(null(), Integer).label("message_seq"),
    ]


def _chat_columns() -> list:
    return [
        cast(KbChatChunk.id, String).label("id"), literal("chat").label("kind"), KbChatChunk.text,
        KbChatChunk.label, cast(null(), String).label("report_code"), cast(null(), Integer).label("fight_id"),
        cast(null(), String).label("guide_id"), cast(null(), String).label("class_name"),
        cast(null(), String).label("spec"), cast(null(), String).label("content_type"),
        cast(null(), String).label("section"), cast(KbChatChunk.conversation_id, String).label("conversation_id"),
        KbChatChunk.message_seq,
    ]


def _branches(
    query: str,
    vector: list[float] | None,
    filters: SearchFilters,
    tenant_id: uuid.UUID,
    legs: frozenset[Leg],
    since: datetime,
) -> list:
    kinds = [filters.kind] if filters.kind else list(KINDS)
    out = []
    for kind in kinds:
        if kind == "chat":
            model, columns, where, config = KbChatChunk, _chat_columns(), _chat_where(filters, tenant_id), "english"
        else:
            model, columns = KbChunk, _chunk_columns(kind)
            where, config = _chunk_where(kind, filters, tenant_id, since), "simple" if kind == "wcl" else "english"
        if "vector" in legs and vector is not None:
            distance = model.embedding.op("<=>", return_type=Float)(literal(vector, Vector(KB_DIMENSIONS)))
            out.append(
                select(*columns, literal("vector").label("leg"), distance.label("score"))
                .where(model.embedding.isnot(None), *where)
                .order_by(distance)
                .limit(LEG_LIMIT)
            )
        if "keyword" in legs:
            tsq = _tsquery(config, query)
            rank = func.ts_rank_cd(model.tsv, tsq)
            out.append(
                select(*columns, literal("keyword").label("leg"), rank.label("score"))
                .where(model.tsv.op("@@")(tsq), *where)
                .order_by(rank.desc())
                .limit(LEG_LIMIT)
            )
    return out


def _candidate(row) -> Candidate:
    if row.kind == "chat":
        source: dict[str, Any] = {"conversation_id": row.conversation_id, "message_seq": row.message_seq}
        key: tuple = ("chat", row.conversation_id, row.message_seq)
    elif row.kind == "guide":
        source = {
            "class_name": row.class_name, "spec": row.spec, "content_type": row.content_type,
            "section": row.section or row.label,
        }
        key = ("guide", row.guide_id, row.section or row.label)
    else:
        source = {"report_code": row.report_code, "fight_id": row.fight_id, "label": row.label}
        key = ("wcl", row.report_code, row.fight_id, row.label)
    return Candidate(row.id, row.kind, row.text, key, source)


async def run_query(
    query: str,
    vector: list[float] | None,
    filters: SearchFilters,
    tenant_id: uuid.UUID,
    legs: frozenset[Leg],
) -> list[Candidate]:
    """One query's legs in one statement, in a session scoped to ``tenant_id`` (RLS)."""
    since = datetime.now(UTC) - timedelta(days=settings.raw_store_reverify_days)
    branches = _branches(query, vector, filters, tenant_id, legs, since)
    if not branches:
        return []
    async with db_session.SessionLocal() as session:
        if session.get_bind().dialect.name != "postgresql":
            raise SearchUnavailable("knowledge search needs Postgres")
        await set_scope(session, tenant_id=tenant_id)
        # pgvector >= 0.8: keep scanning the HNSW index until the WHERE clause is satisfied.
        await session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        rows = (await session.execute(union_all(*branches))).all()
    out: list[Candidate] = []
    for leg in ("vector", "keyword"):
        mine = sorted(
            (r for r in rows if r.leg == leg),
            key=lambda r: (r.score if leg == "vector" else -r.score, r.id),
        )[:LEG_LIMIT]
        out += [replace(_candidate(r), leg=leg, rank=i) for i, r in enumerate(mine, start=1)]
    return out


@dataclass(frozen=True)
class _Scored:
    candidate: Candidate
    score: float


def _rrf(ranked: Sequence[Sequence[str]]) -> dict[str, float]:
    """Reciprocal rank fusion of several ranked id lists (rank 1 = best)."""
    scores: dict[str, float] = {}
    for ids in ranked:
        for rank, chunk_id in enumerate(ids, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
    return scores


def _order(scores: dict[str, float]) -> list[str]:
    return sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))


def fuse(per_query: Sequence[Sequence[Candidate]]) -> list[_Scored]:
    """RRF of each query's legs, RRF again across the queries' fused ranks, then one hit per
    source (the best-scoring chunk). Ties break on chunk id, so the order is deterministic."""
    by_id: dict[str, Candidate] = {}
    fused_lists: list[list[str]] = []
    for candidates in per_query:
        legs: dict[Leg, list[Candidate]] = {}
        for c in candidates:
            by_id.setdefault(c.chunk_id, c)
            legs.setdefault(c.leg, []).append(c)
        ranked = [[c.chunk_id for c in sorted(leg, key=lambda c: c.rank)] for leg in legs.values()]
        fused_lists.append(_order(_rrf(ranked)))
    total = _rrf(fused_lists)
    seen: set[tuple] = set()
    out: list[_Scored] = []
    for chunk_id in _order(total):
        candidate = by_id[chunk_id]
        if candidate.source_key in seen:
            continue
        seen.add(candidate.source_key)
        out.append(_Scored(candidate, total[chunk_id]))
    return out


def truncate(text: str, limit: int = HIT_TEXT_CHARS) -> str:
    """``text`` cut to ``limit`` characters at a word boundary, with an ellipsis."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + "…"


def payload(result: SearchResult) -> dict[str, Any]:
    """The tool result the agent sees (contracts/search-knowledge.md)."""
    hits = []
    for hit in result.hits:
        item: dict[str, Any] = {
            "kind": hit.kind, "source": hit.source, "text": hit.text, "score": round(hit.score, 4)
        }
        if hit.relaxed:
            item["relaxed"] = True
        hits.append(item)
    return {
        "status": "success",
        "mode": result.mode,
        "relaxed": list(result.relaxed),
        "capped": result.capped,
        "note": result.note,
        "hits": hits,
    }


def _size(result: SearchResult) -> int:
    return len(json.dumps(payload(result), ensure_ascii=False))


def cap(result: SearchResult, limit: int = OUTPUT_CAP) -> SearchResult:
    """Drop the lowest-ranked hits until the serialised result fits in ``limit`` characters."""
    if _size(result) <= limit:
        return result
    hits = list(result.hits)
    while hits and _size(replace(result, hits=hits, capped=True)) > limit:
        hits.pop()
    return replace(result, hits=hits, capped=True)


async def _embed(queries: Sequence[str], embedder: Embedder | None) -> list[list[float]] | None:
    """One embedding call for every query; None when unavailable or failed (keyword only)."""
    if embedder is None:
        return None
    try:
        async with asyncio.timeout(EMBED_TIMEOUT_S):
            vectors = await embedder.embed(list(queries), task="RETRIEVAL_QUERY")
    except Exception as exc:  # noqa: BLE001 - search still runs on keywords
        logger.warning("query embedding failed, keyword search only: %s", type(exc).__name__)
        return None
    return vectors if len(vectors) == len(queries) else None


async def _run_pass(
    request: SearchRequest,
    filters: SearchFilters,
    vectors: list[list[float]] | None,
    legs: frozenset[Leg],
    runner: QueryRunner,
) -> list[_Scored]:
    per_query = await asyncio.gather(
        *(
            runner(query, vectors[i] if vectors else None, filters, request.tenant_id, legs)
            for i, query in enumerate(request.queries)
        )
    )
    return fuse(per_query)


async def search(
    request: SearchRequest,
    *,
    embedder: Embedder | None,
    runner: QueryRunner | None = None,
    mode: Mode = "hybrid",
) -> SearchResult:
    """Run every query concurrently, relax soft filters while short of ``k`` hits, cap the
    result. ``runner`` defaults to the SQL legs; ``mode`` other than hybrid is for the eval."""
    runner = runner or run_query
    started = time.monotonic()
    async with asyncio.timeout(SEARCH_TIMEOUT_S):
        vectors = None if mode == "keyword" else await _embed(request.queries, embedder)
        wanted: dict[Mode, frozenset[Leg]] = {
            "hybrid": frozenset({"vector", "keyword"}),
            "vector": frozenset({"vector"}),
            "keyword": frozenset({"keyword"}),
        }
        legs = wanted[mode] if vectors is not None else wanted[mode] - {"vector"}
        result_mode = "keyword_only" if mode == "hybrid" and vectors is None else mode

        filters = request.filters
        droppable = [f for f in filters.soft_present() if f not in request.hard]
        dropped: list[SoftFilter] = []
        hits: list[Hit] = []
        passes: list[int] = []  # the relaxation pass each hit came from
        seen: set[tuple] = set()
        while True:
            scored = await _run_pass(request, filters, vectors, legs, runner) if legs else []
            for s in scored:
                if s.candidate.source_key in seen:
                    continue
                seen.add(s.candidate.source_key)
                c = s.candidate
                hits.append(Hit(c.kind, c.source, truncate(c.text), s.score, relaxed=bool(dropped)))
                passes.append(len(dropped))
            if len(hits) >= request.k or not droppable:
                break
            name = droppable.pop(0)
            filters = filters.without(name)
            dropped.append(name)
    hits, passes = hits[: request.k], passes[: request.k]
    relaxed = dropped[: max(passes, default=0)]
    note = KEYWORD_ONLY_NOTE if result_mode == "keyword_only" else None
    if not hits:
        note = f"{note} {NO_HITS_NOTE}" if note else NO_HITS_NOTE
    result = cap(SearchResult(hits, result_mode, relaxed, note=note))
    logger.info(
        "kb search queries=%d mode=%s hits=%d relaxed=%s capped=%s ms=%d",
        len(request.queries), result.mode, len(result.hits), ",".join(relaxed) or "-",
        result.capped, int((time.monotonic() - started) * 1000),
    )
    return result
