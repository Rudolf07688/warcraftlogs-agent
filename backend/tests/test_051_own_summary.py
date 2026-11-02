"""The stored-reports lookup filters on the own-summary flag (feature 051, sc-354). Over SQLite.

The flag is set when a row is written, only for our own fixed summary query with exact codes; the
lookup filters on it before its limit, so look-alike rows can't crowd out real ones; a summary is
listed whenever it was fetched once a recent grant makes it visible. The Postgres candidate scan,
RLS and the 0021 backfill are in test_051_raw_store_pg.py.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from backend.app.db.models import RawFetch
from backend.app.repositories.raw_fetches import (
    ReportStatus,
    grant_codes,
    list_visible_summaries,
    record_report_status,
)
from backend.app.services.fetch_persistence import PendingWrite, store_batch
from wcl_agent.client.queries import REPORT_SUMMARY, report_summaries_query
from wcl_agent.client.wcl_client import FetchedResponse, _flight_key

FORGED = (
    "query ReportSummary($code: String!) { reportData { report(code: $code) "
    "{ code title startTime zone { name } masterData { actors { name } } } } }"
)


def report(code: str) -> dict:
    return {"code": code, "visibility": "unlisted", "title": f"Raid {code}", "startTime": 1, "endTime": 2,
            "zone": {"id": 1, "name": "Zone"}, "guild": {"name": "G"},
            "masterData": {"actors": [{"id": 1, "name": "P", "subType": "Warrior"}]}, "fights": []}


def fetched(query: str, variables: dict, data: dict, at: datetime) -> FetchedResponse:
    body = json.dumps({"data": data}).encode()
    return FetchedResponse(_flight_key(query, variables), query, variables, body, at)


def single(code: str, at: datetime) -> FetchedResponse:
    return fetched(REPORT_SUMMARY, {"code": code}, {"reportData": {"report": report(code)}}, at)


def codes_of(bodies: list[bytes]) -> set[str]:
    return {r["code"] for b in bodies for r in json.loads(b)["data"]["reportData"].values()}


async def flags(factory) -> dict[str, bool]:
    async with factory() as session:
        rows = (await session.execute(RawFetch.__table__.select())).mappings().all()
    return {r["query_key"]: r["own_summary"] for r in rows}


async def test_the_flag_is_set_only_for_our_own_summary_queries(patched_db, tenant_id):
    now = datetime.now(UTC)
    ours = single("Own1", now)
    batch = fetched(report_summaries_query(2), {"c0": "Own2", "c1": "Own3"},
                    {"reportData": {"r0": report("Own2"), "r1": report("Own3")}}, now)
    forged = fetched(FORGED, {"code": "Fg1"}, {"reportData": {"report": report("Fg1")}}, now)
    extra = fetched(REPORT_SUMMARY, {"code": "Ex1", "x": 1}, {"reportData": {"report": report("Ex1")}}, now)
    padded = fetched(REPORT_SUMMARY, {"code": "Pd1 "}, {"reportData": {"report": report("Pd1")}}, now)
    await store_batch([PendingWrite(f, tenant_id) for f in (ours, batch, forged, extra, padded)])
    assert await flags(patched_db) == {
        ours.query_key: True, batch.query_key: True,
        forged.query_key: False, extra.query_key: False, padded.query_key: False,
    }


async def test_look_alike_rows_beyond_the_limit_cannot_crowd_out_real_ones(patched_db, tenant_id):
    """AC2: 250 visible hand-written ``ReportSummary`` rows, all newer than the real ones."""
    now = datetime.now(UTC)
    real = [single(f"Real{i}", now - timedelta(hours=1)) for i in range(3)]
    await store_batch([PendingWrite(f, tenant_id) for f in real])
    forged = [f"Fake{i}" for i in range(250)]
    async with patched_db() as session:
        await session.execute(RawFetch.__table__.insert(), [
            {"query_key": _flight_key(FORGED, {"code": c}), "operation_name": "ReportSummary",
             "params": {"code": c}, "report_code": c, "report_codes": [c], "fetched_at": now,
             "payload": {"data": {"reportData": {"report": report(c)}}},
             "payload_hash": None}
            for c in forged
        ])
        await record_report_status(session, [ReportStatus(c, "public", 2, now) for c in forged])
        await session.commit()
    async with patched_db() as session:
        bodies = await list_visible_summaries(session, tenant_id=tenant_id, since=now - timedelta(days=1), limit=200)
    assert codes_of(bodies) == {f"Real{i}" for i in range(3)}


async def test_an_old_summary_visible_through_a_recent_grant_is_listed(patched_db, tenant_id, other_tenant_id):
    """AC3: fetched (and its status checked) long before the window; another query of the report
    granted it to the tenant today."""
    now = datetime.now(UTC)
    since = now - timedelta(days=1)
    old = now - timedelta(days=30)
    await store_batch([PendingWrite(single("Old1", old), tenant_id)])
    async with patched_db() as session:
        await grant_codes(session, tenant_id, ["Old1"], now)
        await session.commit()
    async with patched_db() as session:
        mine = await list_visible_summaries(session, tenant_id=tenant_id, since=since, limit=200)
        theirs = await list_visible_summaries(session, tenant_id=other_tenant_id, since=since, limit=200)
        nobody = await list_visible_summaries(session, tenant_id=None, since=since, limit=200)
    assert codes_of(mine) == {"Old1"} and theirs == [] and nobody == []


async def test_an_old_summary_without_a_recent_grant_or_status_is_not_listed(patched_db, tenant_id):
    now = datetime.now(UTC)
    await store_batch([PendingWrite(single("Old2", now - timedelta(days=30)), tenant_id)])
    async with patched_db() as session:
        assert await list_visible_summaries(session, tenant_id=tenant_id, since=now - timedelta(days=1), limit=200) == []

