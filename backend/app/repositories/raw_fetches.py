"""Raw Warcraft Logs responses (feature 020): the upsert into the global ``raw_fetches``.

The response body is bound as text and decoded by the database, which also drops the
client's injected ``data._cost`` field. No Python JSON work on a multi-MB body ever runs on
the event loop (research R3).
"""

from __future__ import annotations

from sqlalchemy import Text, func, literal
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from wcl_agent.client.wcl_client import FetchedResponse, operation_name, report_codes

from ..db.models import RawFetch
from ..db.repository import _insert

_UPDATED = ("operation_name", "params", "report_code", "report_codes", "fetched_at", "payload")


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
