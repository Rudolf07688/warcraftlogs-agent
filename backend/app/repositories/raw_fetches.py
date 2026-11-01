"""Raw Warcraft Logs responses (features 020, 039): the global ``raw_fetches`` store.

The response body is bound as text and decoded by the database, which also drops the
client's injected ``data._cost`` field. No Python JSON work on a multi-MB body ever runs on
the event loop (020 research R3).

Feature 039: this is the ONLY module that reads ``raw_fetches`` (a guard test enforces it).
:func:`fetch_visible_clause` is the one definition of the visibility rule — a row is served to a
tenant only when every report it names is public or granted to that tenant, both confirmed
recently — and every read goes through it (:func:`probe_visible_fetch`, 044's search join), so
DB-first reads and search can't bypass it (specs/039-local-first-data/data-model.md, 045
contracts/visibility-clause.md).
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import (
    Boolean,
    LargeBinary,
    Text,
    and_,
    case,
    cast,
    delete,
    exists,
    func,
    literal,
    literal_column,
    not_,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from wcl_agent.client.queries import REPORT_SUMMARY, report_summaries_query
from wcl_agent.client.wcl_client import (
    _COST_RE,
    _REPORT_TOKEN_RE,
    FetchedResponse,
    _flight_key,
    exact_report_codes,
    operation_name,
    report_codes,
)

from ..db.models import RawFetch, RawFetchGrant, RawReport
from ..db.repository import _insert

_UPDATED = ("operation_name", "params", "report_code", "report_codes", "fetched_at", "payload", "payload_hash")
MAX_CODE = 32  # raw_reports.code / raw_fetch_grants.report_code; longer codes are never visible
MAX_OPERATION = 120  # raw_fetches.operation_name
_OFF_LOOP_BYTES = 256_000  # hashing / scanning bigger bodies runs in a thread
GRANT_REFRESH = timedelta(hours=1)  # a grant younger than this isn't rewritten (045 PERF-005)
# A JSON escape sequence: an escaped backslash (kept) or \u0000, which JSONB rejects (dropped).
_ESCAPE_RE = re.compile(rb"\\(\\|u0000)")


@dataclass(frozen=True)
class ReportStatus:
    """What WCL last showed us about one report (a ``raw_reports`` row)."""

    code: str
    visibility: str | None
    end_time_ms: int | None
    checked_at: datetime


# fresh(fetched_at, the status of each code the row names, None where WCL showed us none)
Freshness = Callable[[datetime, list[ReportStatus | None]], bool]


def _aware(at: datetime) -> datetime:
    """SQLite returns naive datetimes; everything here is UTC."""
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def _payload(dialect: str, body: str) -> ColumnElement:
    """The response body as JSON without ``data._cost``, decoded in the database."""
    raw = literal(body, Text)
    if dialect == "postgresql":
        return raw.cast(JSONB).op("#-", return_type=JSONB)(literal(["data", "_cost"], ARRAY(Text)))
    return func.json_remove(raw, "$.data._cost")


_STRING_RE = re.compile(r'"([^"\\]*)"')


def stored_codes(query: str, variables: dict) -> list[str]:
    """The codes a row is filed under, so delete-on-gone finds it (041 BUG-007).

    Exact when the strict parser resolves the query. When it can't but the query names a
    report, every string literal and string variable is listed too: an over-approximation that
    can only make a gone report delete more. Such rows are never served (reads need exact
    codes).
    """
    exact = exact_report_codes(query, variables)
    if exact is not None or not _REPORT_TOKEN_RE.search(query):
        return exact if exact is not None else report_codes(query, variables)
    loose = report_codes(query, variables) + _STRING_RE.findall(query)
    loose += [v for v in variables.values() if isinstance(v, str)]
    return list(dict.fromkeys(c.strip() for c in loose if c.strip()))


def _prepare(content: bytes) -> tuple[str, bytes]:
    """(hash, storable body). The hash ignores ``data._cost``, which changes every request;
    the body loses ``\\u0000`` escapes (Postgres JSONB rejects them, sc-177)."""
    digest = hashlib.sha256(_COST_RE.sub(b"", content, count=1)).hexdigest()
    if b"\\u0000" in content:
        content = _ESCAPE_RE.sub(lambda m: m.group(0) if m.group(1) == b"\\" else b"", content)
    return digest, content


async def upsert_raw_fetch(session: AsyncSession, fetched: FetchedResponse) -> bool:
    """Store one fetch; a row with the same ``query_key`` is replaced only by a newer fetch.

    An unchanged body (same hash) only moves ``fetched_at`` forward: the payload is neither
    sent nor rewritten (sc-177). Overlong labels never fail the insert: the operation name is
    truncated, and a code over :data:`MAX_CODE` leaves ``report_code`` empty (it stays in
    ``report_codes``, so deletion still finds it). Returns whether the stored payload changed
    (inserted or replaced; contract 5, 043's post-store hook).
    """
    if len(fetched.content) > _OFF_LOOP_BYTES:
        digest, body = await asyncio.to_thread(_prepare, fetched.content)
    else:
        digest, body = _prepare(fetched.content)
    stored = await session.scalar(
        select(RawFetch.payload_hash).where(RawFetch.query_key == fetched.query_key)
    )
    if stored == digest:
        await session.execute(
            update(RawFetch)
            .where(RawFetch.query_key == fetched.query_key, RawFetch.fetched_at < fetched.fetched_at)
            .values(fetched_at=fetched.fetched_at)
        )
        return False
    codes = stored_codes(fetched.query, fetched.variables)
    exact = exact_report_codes(fetched.query, fetched.variables)
    single = codes[0] if exact and len(codes) == 1 and len(codes[0]) <= MAX_CODE else None
    op = operation_name(fetched.query)
    stmt = _insert(session, RawFetch).values(
        query_key=fetched.query_key,
        operation_name=op[:MAX_OPERATION] if op else None,
        params=fetched.variables,
        report_code=single,
        report_codes=codes,
        fetched_at=fetched.fetched_at,
        payload=_payload(session.bind.dialect.name, body.decode()),
        payload_hash=digest,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["query_key"],
        set_={col: stmt.excluded[col] for col in _UPDATED},
        where=RawFetch.fetched_at < stmt.excluded.fetched_at,
    ).returning(RawFetch.query_key)
    return (await session.execute(stmt)).first() is not None


# --- Visibility (feature 039) -------------------------------------------------------


async def grant_codes(
    session: AsyncSession, tenant_id: uuid.UUID, codes: Sequence[str], at: datetime
) -> None:
    """Record that ``tenant_id`` fetched these codes from WCL itself at ``at``.

    ``raw_fetch_grants`` is under RLS: the caller sets the transaction's tenant scope first.
    A stored grant less than :data:`GRANT_REFRESH` older than ``at`` is left alone, so a
    report fetched again and again doesn't rewrite its grant row each time (045 PERF-005).
    """
    rows = [
        {"tenant_id": tenant_id, "report_code": code, "granted_at": at}
        for code in dict.fromkeys(codes)
        if len(code) <= MAX_CODE
    ]
    if not rows:
        return
    stmt = _insert(session, RawFetchGrant).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["tenant_id", "report_code"],
        set_={"granted_at": stmt.excluded.granted_at},
        where=RawFetchGrant.granted_at < literal(at - GRANT_REFRESH, RawFetchGrant.granted_at.type),
    )
    await session.execute(stmt)


async def record_report_status(session: AsyncSession, statuses: Sequence[ReportStatus]) -> None:
    """Upsert what WCL showed about each report; an older observation never wins."""
    rows = {
        s.code: {
            "code": s.code,
            "visibility": (s.visibility or None) and s.visibility[:16],
            "end_time_ms": s.end_time_ms,
            "checked_at": s.checked_at,
        }
        for s in statuses
        if 0 < len(s.code) <= MAX_CODE
    }
    if not rows:
        return
    stmt = _insert(session, RawReport).values(list(rows.values()))
    stmt = stmt.on_conflict_do_update(
        index_elements=["code"],
        set_={c: stmt.excluded[c] for c in ("visibility", "end_time_ms", "checked_at")},
        where=RawReport.checked_at < stmt.excluded.checked_at,
    )
    await session.execute(stmt)


def _names_report(session: AsyncSession, code: str) -> ColumnElement[bool]:
    if session.bind.dialect.name == "postgresql":
        return RawFetch.report_codes.op("?")(code)  # the GIN index (0013)
    return text(
        "EXISTS (SELECT 1 FROM json_each(raw_fetches.report_codes) WHERE json_each.value = :code)"
    ).bindparams(code=code)


async def delete_report(session: AsyncSession, code: str) -> int:
    """WCL no longer serves this report: drop every row naming it and its status.

    Grants stay: the rows they would unlock are gone, and rows only come back through a
    successful WCL fetch of the code (research R7). Returns the number of rows deleted.
    """
    result = await session.execute(delete(RawFetch).where(_names_report(session, code)))
    await session.execute(delete(RawReport).where(RawReport.code == code))
    return result.rowcount or 0


async def scope_tenant(session: AsyncSession, tenant_id: uuid.UUID | None) -> None:
    """Set the transaction's ``app.tenant_id`` for the grants' RLS in one statement (Postgres
    only). ``app.user_id`` stays unset: no raw-store policy reads it (0018)."""
    if session.bind.dialect.name == "postgresql":
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id) if tenant_id else ""}
        )


class _CodesVisible(ColumnElement[bool]):
    """Every element of a ``report_codes`` array is a visible code (see :func:`fetch_visible_clause`).

    Compiled per dialect, because walking a JSON array differs: ``jsonb_array_elements`` on
    Postgres, ``json_each`` on SQLite.
    """

    type = Boolean()
    inherit_cache = False

    def __init__(self, codes: ColumnElement, tenant_id: uuid.UUID | None, since: datetime):
        self.codes, self.tenant_id, self.since = codes, tenant_id, since


def _codes_visible(element: _CodesVisible, postgres: bool) -> ColumnElement[bool]:
    if postgres:
        each = func.jsonb_array_elements(element.codes).table_valued("value").alias("vis_code")
        is_string = func.jsonb_typeof(each.c.value) == "string"
        code = each.c.value.op("#>>", return_type=Text)(literal_column("'{}'"))
    else:
        each = func.json_each(element.codes).table_valued("value", "type").alias("vis_code")
        is_string = each.c.type == "text"
        code = each.c.value
    since = literal(element.since, RawReport.checked_at.type)
    allowed = exists().where(
        RawReport.code == code, RawReport.visibility == "public", RawReport.checked_at >= since
    )
    if element.tenant_id is not None:
        allowed = or_(
            allowed,
            exists().where(
                RawFetchGrant.tenant_id == element.tenant_id,
                RawFetchGrant.report_code == code,
                RawFetchGrant.granted_at >= since,
            ),
        )
    ok = and_(is_string, func.length(code) >= 1, func.length(code) <= MAX_CODE, allowed)
    return not_(exists(select(literal(1)).select_from(each).where(not_(ok))))


@compiles(_CodesVisible, "postgresql")
def _compile_pg(element, compiler, **kw):
    return compiler.process(_codes_visible(element, postgres=True), **kw)


@compiles(_CodesVisible)
def _compile_default(element, compiler, **kw):
    return compiler.process(_codes_visible(element, postgres=False), **kw)


class _NonEmpty(ColumnElement[bool]):
    """A JSON array with at least one element (per dialect, like :class:`_CodesVisible`)."""

    type = Boolean()
    inherit_cache = False

    def __init__(self, codes: ColumnElement):
        self.codes = codes


@compiles(_NonEmpty, "postgresql")
def _compile_non_empty_pg(element, compiler, **kw):
    return compiler.process(func.jsonb_array_length(element.codes) > 0, **kw)


@compiles(_NonEmpty)
def _compile_non_empty(element, compiler, **kw):
    return compiler.process(func.json_array_length(element.codes) > 0, **kw)


def fetch_visible_clause(
    raw_fetch_id: ColumnElement[str] | str, *, tenant_id: uuid.UUID | None, since: datetime
) -> ColumnElement[bool]:
    """The 039 visibility rule in SQL: the ONE definition (045 contract 3).

    True when the ``raw_fetches`` row with ``query_key = raw_fetch_id`` exists, names at least
    one report, every code is at most :data:`MAX_CODE` long, and every code is public (checked
    at or after ``since``) or granted to ``tenant_id`` at or after ``since``. ``tenant_id``
    None sees public reports only. Freshness is the caller's rule. On Postgres the caller's
    transaction carries the tenant scope (:func:`scope_tenant`; grants are RLS'd).
    """
    row = aliased(RawFetch, name="vis_fetch")
    return exists().where(
        row.query_key == raw_fetch_id,
        _NonEmpty(row.report_codes),
        _CodesVisible(row.report_codes, tenant_id, since),
    )


def fetch_names_code(
    raw_fetch_id: ColumnElement[str], code: ColumnElement[str]
) -> ColumnElement[bool]:
    """True when the ``raw_fetches`` row ``raw_fetch_id`` lists ``code`` among its report codes
    (feature 044, P7 SEC-001): a row derived from a fetch may only carry a code that fetch names,
    so :func:`fetch_visible_clause` covers it. NULL ``code`` is false. Postgres only (JSONB
    ``?``, the GIN index): knowledge search runs only there."""
    row = aliased(RawFetch, name="code_fetch")
    return exists().where(row.query_key == raw_fetch_id, row.report_codes.op("?")(code))


ProbeOutcome = Literal["hit", "miss", "not_visible"]


@dataclass(frozen=True)
class Probe:
    """What one store read found. ``body`` (JSON bytes) only on a hit; ``shared`` when every
    code is public, so the body may go to the shared, tenant-less Redis cache (sc-296)."""

    outcome: ProbeOutcome
    body: bytes | None = None
    shared: bool = False


_MISS = Probe("miss")


def _payload_bytes(dialect: str) -> ColumnElement[bytes]:
    """The stored JSON as bytes, so no text decode/encode runs on the event loop (PERF-006)."""
    if dialect == "postgresql":
        return func.convert_to(cast(RawFetch.payload, Text), "UTF8", type_=LargeBinary)
    return cast(RawFetch.payload, LargeBinary)


async def probe_visible_fetch(
    session: AsyncSession,
    query_key: str,
    *,
    tenant_id: uuid.UUID | None,
    since: datetime,
    fresh: Freshness,
) -> Probe:
    """Read ``query_key`` through the visibility rule, in at most four statements (045 PERF-002).

    1. the row's codes and ``fetched_at`` (no row: a miss, nothing else runs);
    2. the codes' ``raw_reports`` statuses, for ``fresh(fetched_at, statuses)`` (one status per
       code, in order; not fresh: a miss);
    3. the tenant scope, only when a code isn't publicly confirmed (grants are RLS'd);
    4. :func:`fetch_visible_clause` for the tenant and for "public only", and the payload when
       visible, pinned to the ``fetched_at`` of step 1 (a row replaced meanwhile is a miss).

    A row naming no report is public WCL data whose freshness is the caller's rule; the
    visibility clause never serves it. ``tenant_id`` None sees public reports only.
    """
    row = (
        await session.execute(
            select(RawFetch.report_codes, RawFetch.fetched_at).where(RawFetch.query_key == query_key)
        )
    ).first()
    if row is None:
        return _MISS
    codes = list(row.report_codes or [])
    if not codes or any(not isinstance(c, str) or not 0 < len(c) <= MAX_CODE for c in codes):
        return Probe("not_visible")
    statuses: dict[str, ReportStatus] = {}
    for r in await session.scalars(select(RawReport).where(RawReport.code.in_(codes))):
        statuses[r.code] = ReportStatus(r.code, r.visibility, r.end_time_ms, _aware(r.checked_at))
    if not fresh(_aware(row.fetched_at), [statuses.get(c) for c in codes]):
        return _MISS
    public = all(
        (s := statuses.get(c)) is not None and s.visibility == "public" and s.checked_at >= since for c in codes
    )
    if tenant_id is not None and not public:
        await scope_tenant(session, tenant_id)
    visible = fetch_visible_clause(RawFetch.query_key, tenant_id=tenant_id, since=since)
    found = (
        await session.execute(
            select(
                visible,
                fetch_visible_clause(RawFetch.query_key, tenant_id=None, since=since),
                case((visible, _payload_bytes(session.bind.dialect.name))),
            ).where(RawFetch.query_key == query_key, RawFetch.fetched_at == row.fetched_at)
        )
    ).first()
    if found is None:
        return _MISS
    if not found[0]:
        return Probe("not_visible")
    return Probe("hit", bytes(found[2]), bool(found[1]))


SUMMARY_OPS = ("ReportSummary", "ReportsBatch")  # our report summary queries (single, batch)
SUMMARY_LIST_TIMEOUT_MS = 2000  # statement timeout of the summaries list on Postgres (047 sc-324)

# Each report object of a stored summary body cut down to what the character lookup reads
# (code, title, start, zone name, actor names), in the body's own shape: a few KB, not the
# fights and full roster (047 sc-324). Per dialect; ``raw_fetches`` is the outer row.
_SUMMARY_PROJECTION = {
    "postgresql": """convert_to(jsonb_build_object('data', jsonb_build_object('reportData', (
        SELECT jsonb_object_agg(r.key, jsonb_build_object(
            'code', r.value->'code', 'title', r.value->'title', 'startTime', r.value->'startTime',
            'zone', jsonb_build_object('name', r.value#>'{zone,name}'),
            'masterData', jsonb_build_object('actors', (
                SELECT coalesce(jsonb_agg(jsonb_build_object('name', a->'name')), '[]'::jsonb)
                FROM jsonb_array_elements(CASE WHEN jsonb_typeof(r.value#>'{masterData,actors}') = 'array'
                     THEN r.value#>'{masterData,actors}' ELSE '[]'::jsonb END) AS a))))
        FROM jsonb_each(CASE WHEN jsonb_typeof(raw_fetches.payload#>'{data,reportData}') = 'object'
             THEN raw_fetches.payload#>'{data,reportData}' ELSE '{}'::jsonb END) AS r
        WHERE jsonb_typeof(r.value) = 'object')))::text, 'UTF8')""",
    "sqlite": """CAST(json_object('data', json_object('reportData', json((
        SELECT json_group_object(r.key, json_object(
            'code', json_extract(r.value, '$.code'), 'title', json_extract(r.value, '$.title'),
            'startTime', json_extract(r.value, '$.startTime'),
            'zone', json_object('name', json_extract(r.value, '$.zone.name')),
            'masterData', json_object('actors', json((
                SELECT json_group_array(json_object('name', json_extract(a.value, '$.name')))
                FROM json_each(r.value, '$.masterData.actors') AS a WHERE a.type = 'object')))))
        FROM json_each(raw_fetches.payload, '$.data.reportData') AS r WHERE r.type = 'object')))) AS BLOB)""",
}


def _our_summary(query_key: str, params: object, codes: object) -> bool:
    """The row is a response to our own fixed summary query with exactly these codes.

    Rows keep no query text, but their key is :func:`_flight_key` of it: rebuilt here from our
    own query text and the stored params, it matches only a row our query wrote (a hand-written
    ``run_wcl_graphql`` query may be named ``ReportSummary``, but can't have that key). The
    params must also give exact codes, equal to the row's (the 039 rule).
    """
    if not isinstance(params, dict) or not params:
        return False
    if set(params) == {"code"}:
        query = REPORT_SUMMARY
    elif set(params) == {f"c{i}" for i in range(len(params))}:
        query = report_summaries_query(len(params))
    else:
        return False
    exact = exact_report_codes(query, params)
    return exact is not None and exact == codes and _flight_key(query, params) == query_key


async def list_visible_summaries(
    session: AsyncSession, *, tenant_id: uuid.UUID | None, since: datetime, limit: int
) -> list[bytes]:
    """The newest stored report summaries (JSON bytes) the tenant may see, at most ``limit``
    (045 sc-131), each cut down to the fields the character lookup reads (047 sc-324).

    Only rows of our own summary queries with exact codes (:func:`_our_summary`); visibility
    only through :func:`fetch_visible_clause`; freshness is the caller's concern. Served by the
    partial index ``ix_raw_fetches_summaries`` (0020). On Postgres the caller's transaction
    carries the tenant scope, and :data:`SUMMARY_LIST_TIMEOUT_MS` bounds the statement (it stays
    set for the rest of that transaction).
    """
    dialect = session.bind.dialect.name
    if dialect == "postgresql":
        await session.execute(
            text("SELECT set_config('statement_timeout', :ms, true)"), {"ms": str(SUMMARY_LIST_TIMEOUT_MS)}
        )
    projection = literal_column(_SUMMARY_PROJECTION["postgresql" if dialect == "postgresql" else "sqlite"])
    rows = await session.execute(
        select(RawFetch.query_key, RawFetch.params, RawFetch.report_codes, projection)
        .where(
            # Literal names, so the planner can match the partial index's predicate.
            RawFetch.operation_name.in_([literal_column(f"'{op}'") for op in SUMMARY_OPS]),
            fetch_visible_clause(RawFetch.query_key, tenant_id=tenant_id, since=since),
        )
        .order_by(RawFetch.fetched_at.desc())
        .limit(limit)
    )
    return [bytes(body) for key, params, codes, body in rows if _our_summary(key, params, codes)]


async def read_visible_fetch(
    session: AsyncSession,
    query_key: str,
    *,
    tenant_id: uuid.UUID | None,
    since: datetime,
    fresh: Freshness,
) -> bytes | None:
    """The stored body for ``query_key`` as JSON bytes, or None: :func:`probe_visible_fetch`'s
    body. Served only when every report the row names (codes up to :data:`MAX_CODE`) is public
    or granted to ``tenant_id``, each confirmed at or after ``since``, and ``fresh(fetched_at,
    statuses)`` holds. On Postgres the scope is set here when a grant is needed.
    """
    probe = await probe_visible_fetch(session, query_key, tenant_id=tenant_id, since=since, fresh=fresh)
    return probe.body


# --- Knowledge base backfill (feature 043, sc-113) -------------------------------------

SUMMARY_OPERATIONS = ("ReportSummary", "ReportsBatch")  # our report summary queries' names


@dataclass(frozen=True)
class IndexableFetch:
    """One stored row as the knowledge base backfill chunks it. Rows keep no query text."""

    query_key: str
    operation_name: str | None
    params: dict
    report_codes: list[str]
    body: bytes  # the stored JSON


async def list_fetch_keys(
    session: AsyncSession, *, after: str | None, limit: int, summaries: bool
) -> list[str]:
    """Up to ``limit`` keys of stored rows naming at least one report, in key order after
    ``after``: our summary queries (``summaries``) or every other row. For the knowledge base
    backfill only; it serves nothing (044's search applies :func:`fetch_visible_clause`)."""
    summary = RawFetch.operation_name.in_(SUMMARY_OPERATIONS)
    other = or_(~summary, RawFetch.operation_name.is_(None))
    stmt = (
        select(RawFetch.query_key)
        .where(_NonEmpty(RawFetch.report_codes), summary if summaries else other)
        .order_by(RawFetch.query_key)
        .limit(limit)
    )
    if after is not None:
        stmt = stmt.where(RawFetch.query_key > after)
    return list(await session.scalars(stmt))


async def load_fetch_for_index(session: AsyncSession, query_key: str) -> IndexableFetch | None:
    """One stored row for the knowledge base backfill (body as JSON bytes), or None if gone."""
    found = (
        await session.execute(
            select(
                RawFetch.operation_name,
                RawFetch.params,
                RawFetch.report_codes,
                _payload_bytes(session.bind.dialect.name),
            ).where(RawFetch.query_key == query_key)
        )
    ).first()
    if found is None:
        return None
    return IndexableFetch(query_key, found[0], dict(found[1] or {}), list(found[2] or []), bytes(found[3]))
