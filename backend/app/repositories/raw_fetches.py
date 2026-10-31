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

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Text, cast, delete, func, literal, select, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from wcl_agent.client.wcl_client import FetchedResponse, operation_name, report_codes

from ..db.models import RawFetch, RawFetchGrant, RawReport
from ..db.repository import _insert

_UPDATED = ("operation_name", "params", "report_code", "report_codes", "fetched_at", "payload")
MAX_CODE = 32  # raw_reports.code / raw_fetch_grants.report_code; longer codes are never visible


@dataclass(frozen=True)
class ReportStatus:
    """What WCL last showed us about one report (a ``raw_reports`` row)."""

    code: str
    visibility: str | None
    end_time_ms: int | None
    checked_at: datetime


Freshness = Callable[[datetime, dict[str, ReportStatus]], bool]


def _aware(at: datetime) -> datetime:
    """SQLite returns naive datetimes; everything here is UTC."""
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def _payload(dialect: str, body: str) -> ColumnElement:
    """The response body as JSON without ``data._cost``, decoded in the database."""
    raw = literal(body, Text)
    if dialect == "postgresql":
        return raw.cast(JSONB).op("#-", return_type=JSONB)(literal(["data", "_cost"], ARRAY(Text)))
    return func.json_remove(raw, "$.data._cost")


async def upsert_raw_fetch(session: AsyncSession, fetched: FetchedResponse) -> None:
    """Store one fetch; a row with the same ``query_key`` is replaced only by a newer fetch."""
    codes = report_codes(fetched.query, fetched.variables)
    stmt = _insert(session, RawFetch).values(
        query_key=fetched.query_key,
        operation_name=operation_name(fetched.query),
        params=fetched.variables,
        report_code=codes[0] if len(codes) == 1 else None,
        report_codes=codes,
        fetched_at=fetched.fetched_at,
        payload=_payload(session.bind.dialect.name, fetched.content.decode()),
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
    statuses)`` holds. A row naming no report is public WCL data, reachable only by its exact
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
    if not fresh(_aware(row.fetched_at), statuses):
        return None
    return await session.scalar(select(cast(RawFetch.payload, Text)).where(RawFetch.query_key == query_key))
