"""The ``raw_fetches`` table and its upsert (feature 020, data-model.md, contracts R1-R4).

The schema comes from ``metadata.create_all`` (as every test here); migration 0013 mirrors
it. The Postgres path (``CAST … #-``) is checked live (quickstart §3).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from backend.app.db.models import RawFetch
from backend.app.repositories.raw_fetches import upsert_raw_fetch
from wcl_agent.client.wcl_client import FetchedResponse, _flight_key
from wcl_agent.client.queries import REPORT_SUMMARY, character_reports_query, report_summaries_query

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
COST = {"limitPerHour": 3600, "pointsSpentThisHour": 1, "pointsResetIn": 10}


def fetched(query: str, variables: dict, data: dict, at: datetime = T0) -> FetchedResponse:
    body = json.dumps({"data": {"_cost": COST, **data}}).encode()
    return FetchedResponse(_flight_key(query, variables), query, variables, body, at)


async def rows(session) -> list[RawFetch]:
    session.expire_all()
    return list((await session.scalars(select(RawFetch))).all())


async def test_a_single_report_fetch_is_stored_with_every_column(session):
    report = {"reportData": {"report": {"title": "Raid", "endTime": 1}}}
    item = fetched(REPORT_SUMMARY, {"code": "aBcD1234"}, report)
    await upsert_raw_fetch(session, item)
    await session.commit()

    [row] = await rows(session)
    assert row.query_key == item.query_key
    assert row.operation_name == "ReportSummary"
    assert row.params == {"code": "aBcD1234"}
    assert row.report_code == "aBcD1234" and row.report_codes == ["aBcD1234"]
    assert row.fetched_at.replace(tzinfo=UTC) == T0
    assert row.payload == {"data": report}  # the injected _cost is gone


async def test_a_batch_row_lists_every_report_but_has_no_single_code(session):
    variables = {"c0": "AAA", "c1": "BBB"}
    await upsert_raw_fetch(session, fetched(report_summaries_query(2), variables, {"reportData": {}}))
    await session.commit()

    [row] = await rows(session)
    assert row.operation_name == "ReportsBatch"
    assert row.report_code is None and row.report_codes == ["AAA", "BBB"]


async def test_a_fetch_without_reports_has_an_empty_code_list(session):
    query = character_reports_query(1)
    await upsert_raw_fetch(session, fetched(query, {"id0": 7, "limit": 5}, {"characterData": {}}))
    anonymous = "{ rateLimitData { limitPerHour } }"
    await upsert_raw_fetch(session, fetched(anonymous, {}, {"rateLimitData": {"limitPerHour": 1}}))
    await session.commit()

    by_op = {r.operation_name: r for r in await rows(session)}
    assert by_op["RecentReportsByIds"].report_codes == [] and by_op["RecentReportsByIds"].report_code is None
    assert by_op[None].payload == {"data": {"rateLimitData": {"limitPerHour": 1}}}


# --- upsert (US3, AC 4) -----------------------------------------------------------


async def test_the_same_query_twice_keeps_one_row_with_the_newest_fetch(session):
    first = fetched(REPORT_SUMMARY, {"code": "FIN"}, {"v": 1}, T0)
    second = fetched(REPORT_SUMMARY, {"code": "FIN"}, {"v": 2}, T0 + timedelta(minutes=5))
    for item in (first, second, second):
        await upsert_raw_fetch(session, item)
    await session.commit()

    [row] = await rows(session)
    assert row.payload == {"data": {"v": 2}}
    assert row.fetched_at.replace(tzinfo=UTC) == T0 + timedelta(minutes=5)


async def test_an_older_fetch_arriving_late_never_overwrites_a_newer_one(session):
    newer = fetched(REPORT_SUMMARY, {"code": "OOO"}, {"v": "new"}, T0 + timedelta(seconds=1))
    older = fetched(REPORT_SUMMARY, {"code": "OOO"}, {"v": "old"}, T0)
    await upsert_raw_fetch(session, newer)
    await upsert_raw_fetch(session, older)
    await session.commit()

    [row] = await rows(session)
    assert row.payload == {"data": {"v": "new"}}
    assert row.fetched_at.replace(tzinfo=UTC) == T0 + timedelta(seconds=1)


async def test_different_variables_are_different_rows(session):
    await upsert_raw_fetch(session, fetched(REPORT_SUMMARY, {"code": "ONE"}, {}))
    await upsert_raw_fetch(session, fetched(REPORT_SUMMARY, {"code": "TWO"}, {}))
    await session.commit()
    assert await session.scalar(select(func.count()).select_from(RawFetch)) == 2
