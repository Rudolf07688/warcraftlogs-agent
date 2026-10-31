"""Raw Warcraft Logs responses (features 020, 039): the global ``raw_fetches`` store.

The response body is bound as text and decoded by the database, which also drops the
client's injected ``data._cost`` field. No Python JSON work on a multi-MB body ever runs on
the event loop (020 research R3).

Feature 039: this is the ONLY module that reads ``raw_fetches`` (a guard test enforces it).
:func:`read_visible_fetch` applies the visibility rule — a row is served to a tenant only when
every report it names is public or granted to that tenant, both confirmed recently — so DB-first
reads and later search work can't bypass it (specs/039-local-first-data/data-model.md).
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Text, cast, delete, func, literal, select, text, update
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from wcl_agent.client.wcl_client import (
    _COST_RE,
    _REPORT_TOKEN_RE,
    FetchedResponse,
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


def _stored_codes(query: str, variables: dict) -> list[str]:
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


async def upsert_raw_fetch(session: AsyncSession, fetched: FetchedResponse) -> None:
    """Store one fetch; a row with the same ``query_key`` is replaced only by a newer fetch.

    An unchanged body (same hash) only moves ``fetched_at`` forward: the payload is neither
    sent nor rewritten (sc-177). Overlong labels never fail the insert: the operation name is
    truncated, and a code over :data:`MAX_CODE` leaves ``report_code`` empty (it stays in
    ``report_codes``, so deletion still finds it).
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
        return
    codes = _stored_codes(fetched.query, fetched.variables)
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
    )
    await session.execute(stmt)


# --- Visibility (feature 039) -------------------------------------------------------


async def grant_codes(
    session: AsyncSession, tenant_id: uuid.UUID, codes: Sequence[str], at: datetime
) -> None:
    """Record that ``tenant_id`` fetched these codes from WCL itself at ``at``.

    ``raw_fetch_grants`` is under RLS: the caller sets the transaction's tenant scope first.
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
        where=RawFetchGrant.granted_at < stmt.excluded.granted_at,
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


async def read_visible_fetch(
    session: AsyncSession,
    query_key: str,
    *,
    tenant_id: uuid.UUID | None,
    since: datetime,
    fresh: Freshness,
) -> str | None:
    """The stored body for ``query_key`` as JSON text, or None. The ONE read of the store.

    Served only when every report the row names (codes up to :data:`MAX_CODE`) is public or
    granted to ``tenant_id``, each confirmed at or after ``since``, and ``fresh(fetched_at,
    statuses)`` holds (one status per code, in order). A row naming no report is public WCL data, reachable only by its exact
    key; whether it is fresh is the caller's rule. ``tenant_id`` None sees public reports
    only. On Postgres the caller's transaction carries the tenant scope (grants are RLS'd).
    """
    row = (
        await session.execute(
            select(RawFetch.report_codes, RawFetch.fetched_at).where(RawFetch.query_key == query_key)
        )
    ).first()
    if row is None:
        return None
    codes = list(row.report_codes or [])
    if any(not isinstance(c, str) or not 0 < len(c) <= MAX_CODE for c in codes):
        return None
    statuses: dict[str, ReportStatus] = {}
    if codes:
        for r in await session.scalars(select(RawReport).where(RawReport.code.in_(codes))):
            statuses[r.code] = ReportStatus(
                r.code, r.visibility, r.end_time_ms, _aware(r.checked_at)
            )
        granted: set[str] = set()
        if tenant_id is not None:
            granted = set(
                await session.scalars(
                    select(RawFetchGrant.report_code).where(
                        RawFetchGrant.tenant_id == tenant_id,
                        RawFetchGrant.report_code.in_(codes),
                        RawFetchGrant.granted_at >= since,
                    )
                )
            )
        for code in codes:
            status = statuses.get(code)
            public = status is not None and status.visibility == "public" and status.checked_at >= since
            if not public and code not in granted:
                return None
    if not fresh(_aware(row.fetched_at), [statuses.get(c) for c in codes]):
        return None
    return await session.scalar(select(cast(RawFetch.payload, Text)).where(RawFetch.query_key == query_key))
