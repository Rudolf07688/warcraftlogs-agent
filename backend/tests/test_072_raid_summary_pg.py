"""The raid summary's raw-store reads on real Postgres (feature 072): the JSONB ``?`` lookup of the
newest own summary (single or batch), the ``#>`` projections of the parts, and the visibility rule
on both. Skipped unless ``TEST_DATABASE_URL`` points at a migrated Postgres (runtime role).
"""

from __future__ import annotations

import dataclasses
import json
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.db import session as db_session
from backend.app.repositories import tenants as tenants_repo
from backend.app.repositories.raw_fetches import (
    read_visible_parts,
    read_visible_summary,
    stored_summary_exists,
)
from backend.app.services.fetch_persistence import PendingWrite, store_batch
from backend.app.tenancy.context import set_scope
from wcl_agent.client.queries import REPORT_SUMMARY, report_summaries_query
from wcl_agent.client.wcl_client import FetchedResponse, _flight_key

_PG_URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"),
    reason="Postgres tests require TEST_DATABASE_URL pointing at a migrated Postgres (runtime role).",
)

TABLE_Q = "query ReportQ($code: String!, $f: [Int]) { reportData { report(code: $code) { table(fightIDs: $f) } } }"


def code() -> str:
    return uuid.uuid4().hex[:16]  # the database outlives one run: fresh codes per test


def report(c: str) -> dict:
    return {"code": c, "visibility": "unlisted", "startTime": 1, "endTime": 2, "masterData": {"actors": []},
            "fights": []}


def fetched(query: str, variables: dict, data: dict) -> FetchedResponse:
    body = json.dumps({"data": data}).encode()
    return FetchedResponse(_flight_key(query, variables), query, variables, body, datetime.now(UTC))


@pytest.fixture
async def pg(monkeypatch):
    engine = create_async_engine(_PG_URL, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "SessionLocal", maker)
    yield maker
    await engine.dispose()


async def tenant(pg) -> uuid.UUID:
    async with pg() as db:
        t = await tenants_repo.create_tenant(db, name="raw-072")
        await db.commit()
    return t.id


async def test_the_newest_visible_summary_is_found_in_a_batch_row_and_only_for_its_tenant(pg):
    mine, other = await tenant(pg), await tenant(pg)
    a, b = code(), code()
    single = fetched(REPORT_SUMMARY, {"code": a}, {"reportData": {"report": report(a)}})
    batch = fetched(report_summaries_query(2), {"c0": b, "c1": a},
                    {"reportData": {"r0": report(b), "r1": {**report(a), "title": "newer"}}})
    await store_batch([PendingWrite(single, mine), PendingWrite(batch, mine)])
    since = datetime.now(UTC) - timedelta(days=1)

    async with pg() as db:
        await set_scope(db, tenant_id=mine)
        body, _ = await read_visible_summary(db, a, tenant_id=mine, since=since)
        assert await stored_summary_exists(db, a)
        assert not await stored_summary_exists(db, code())
    assert json.loads(body)["data"]["reportData"]["r1"]["title"] == "newer"  # the newest row naming it

    async with pg() as db:
        await set_scope(db, tenant_id=other)
        assert await read_visible_summary(db, a, tenant_id=other, since=since) is None


async def test_parts_are_cut_out_in_the_database_and_follow_the_visibility_rule(pg):
    mine, other = await tenant(pg), await tenant(pg)
    c = code()
    details = {"tanks": [], "healers": [], "dps": [{"name": "Thrall", "server": "Tarren Mill", "type": "Shaman"}]}
    table = fetched(TABLE_Q, {"code": c, "f": [1]}, {"reportData": {"report": {"table": {"data": {
        "playerDetails": details, "damageDone": [{"name": f"P{i}", "total": i} for i in range(5000)]}}}}})
    summary = fetched(REPORT_SUMMARY, {"code": c}, {"reportData": {"report": report(c)}})
    await store_batch([PendingWrite(summary, mine), PendingWrite(table, mine)])
    since = datetime.now(UTC) - timedelta(days=1)
    paths = [("data", "reportData", "report", "table", "data", "playerDetails"), ("data", "nothing", "here")]

    async with pg() as db:
        await set_scope(db, tenant_id=mine)
        parts = await read_visible_parts(db, [table.query_key, "no-such-key"], paths, tenant_id=mine, since=since)
    assert list(parts) == [table.query_key]
    _, (cut, absent) = parts[table.query_key]
    assert json.loads(cut) == details and absent is None
    assert len(cut) * 100 < len(table.content)  # the damage rows never left the database

    async with pg() as db:
        await set_scope(db, tenant_id=other)
        assert await read_visible_parts(db, [table.query_key], paths, tenant_id=other, since=since) == {}


async def test_a_reverify_writes_status_and_grant_under_rls_and_serves_the_stored_rows(pg, monkeypatch):
    """decision:072-reverify on Postgres: the in-band status and grant pass the grants' RLS."""
    from backend.app.db import repository as repo
    from backend.app.services import raid_summary
    from backend.app.tenancy.context import RequestIdentity
    from backend.tests.wcl_fakes import install

    mine = await tenant(pg)
    c = code()
    stale = fetched(REPORT_SUMMARY, {"code": c}, {"reportData": {"report": report(c)}})
    await store_batch([PendingWrite(dataclasses.replace(stale, fetched_at=datetime.now(UTC) - timedelta(days=3)),
                                    mine)])
    identity = RequestIdentity(user_id=uuid.uuid4(), tenant_id=mine, membership_role="tenant_admin",
                               is_platform_admin=False, session_id=uuid.uuid4())
    fake = install(monkeypatch, lambda q, v: {"data": {"reportData": {"report": report(c)}}})

    async with pg() as db:
        await set_scope(db, tenant_id=mine)
        await repo.upsert_tracked_raid(db, tenant_id=mine, report_code=c, label=c)
        summary = await raid_summary.summarize(db, c, identity=identity, now=datetime.now(UTC))
        await db.commit()

    assert summary is not None and summary.has_data and summary.duration_ms == 1
    assert len(fake.calls) == 1
