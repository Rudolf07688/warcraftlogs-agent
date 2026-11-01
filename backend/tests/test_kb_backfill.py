"""Knowledge base backfill (feature 043, sc-113)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from backend.app.db.models import RawFetch
from backend.app.repositories.raw_fetches import list_fetch_keys, load_fetch_for_index

NOW = datetime(2026, 11, 1, tzinfo=UTC)


def raw(key: str, op: str | None, codes: list[str], payload: dict | None = None) -> RawFetch:
    return RawFetch(query_key=key, operation_name=op, params={"code": "X"}, report_codes=codes,
                    fetched_at=NOW, payload=payload or {"data": {"x": 1}})


async def test_fetch_keys_page_summaries_first_and_skip_rows_without_reports(session):
    session.add_all([
        raw("a1", "ReportSummary", ["A"]), raw("a2", "ReportsBatch", ["A", "B"]),
        raw("b1", "ReportQ", ["A"]), raw("b2", None, ["B"]), raw("c1", "CharRef", []),
    ])
    await session.commit()
    assert await list_fetch_keys(session, after=None, limit=10, summaries=True) == ["a1", "a2"]
    assert await list_fetch_keys(session, after=None, limit=10, summaries=False) == ["b1", "b2"]
    assert await list_fetch_keys(session, after="a1", limit=10, summaries=True) == ["a2"]
    assert await list_fetch_keys(session, after=None, limit=1, summaries=False) == ["b1"]


async def test_load_fetch_for_index_returns_the_stored_body(session):
    session.add(raw("k", "ReportQ", ["A"], {"data": {"reportData": {"report": {"table": {"data": {}}}}}}))
    await session.commit()
    row = await load_fetch_for_index(session, "k")
    assert (row.query_key, row.operation_name, row.report_codes) == ("k", "ReportQ", ["A"])
    assert json.loads(row.body) == {"data": {"reportData": {"report": {"table": {"data": {}}}}}}
    assert await load_fetch_for_index(session, "missing") is None
