"""The own-summary lookup on real Postgres (feature 051, sc-354, migration 0021).

Two workspaces under RLS see exactly what the visibility rule allows (public reports, their own
grants, never the other's), an old summary is listed through a recent grant, and 0021's backfill
flags exactly the rows the pre-051 lookup accepted. Skipped unless ``TEST_DATABASE_URL`` points at
a migrated Postgres (runtime role), like test_raw_store_pg.py.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.db import session as db_session
from backend.app.db.models import RawFetch
from backend.app.repositories import tenants as tenants_repo
from backend.app.repositories.raw_fetches import grant_codes, list_visible_summaries
from backend.app.services.fetch_persistence import PendingWrite, store_batch
from backend.app.tenancy.context import set_scope
from wcl_agent.client.queries import REPORT_SUMMARY, report_summaries_query
from wcl_agent.client.wcl_client import FetchedResponse, _flight_key

_PG_URL = os.getenv("TEST_DATABASE_URL", "")
_MIGRATION = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0021_raw_fetch_own_summary.py"

pytestmark = pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"),
    reason="Postgres tests require TEST_DATABASE_URL pointing at a migrated Postgres (runtime role).",
)

FORGED = (
    "query ReportSummary($code: String!) { reportData { report(code: $code) "
    "{ code title startTime zone { name } masterData { actors { name } } } } }"
)


def code() -> str:
    return uuid.uuid4().hex[:16]  # the database outlives one run: fresh codes per test


def report(c: str, visibility: str) -> dict:
    return {"code": c, "visibility": visibility, "title": f"Raid {c}", "startTime": 1, "endTime": 2,
            "zone": {"id": 1, "name": "Zone"}, "guild": {"name": "G"},
            "masterData": {"actors": [{"id": 1, "name": "P", "subType": "Warrior"}]}, "fights": []}


def fetched(query: str, variables: dict, data: dict, at: datetime) -> FetchedResponse:
    return FetchedResponse(_flight_key(query, variables), query, variables, json.dumps({"data": data}).encode(), at)


def single(c: str, visibility: str, at: datetime) -> FetchedResponse:
    return fetched(REPORT_SUMMARY, {"code": c}, {"reportData": {"report": report(c, visibility)}}, at)


@pytest.fixture
async def pg(monkeypatch):
    engine = create_async_engine(_PG_URL, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "SessionLocal", maker)
    yield maker
    await engine.dispose()


@pytest.fixture
async def tenants(pg) -> tuple[uuid.UUID, uuid.UUID]:
    async with pg() as db:
        a = await tenants_repo.create_tenant(db, name="raw-051-a")
        b = await tenants_repo.create_tenant(db, name="raw-051-b")
        await db.commit()
    return a.id, b.id


async def listed(pg, tenant: uuid.UUID | None, since: datetime, ours: set[str]) -> set[str]:
    async with pg() as db:
        await set_scope(db, tenant_id=tenant)
        bodies = await list_visible_summaries(db, tenant_id=tenant, since=since, limit=1000)
    return {r["code"] for b in bodies for r in json.loads(b)["data"]["reportData"].values()} & ours


async def test_two_workspaces_see_exactly_what_the_visibility_rule_allows(pg, tenants):
    a, b = tenants
    now = datetime.now(UTC)
    since = now - timedelta(days=1)
    pub, priv_a, priv_b, old_a, batch_pub = (code() for _ in range(5))
    batch = fetched(report_summaries_query(2), {"c0": batch_pub, "c1": priv_b},
                    {"reportData": {"r0": report(batch_pub, "public"), "r1": report(priv_b, "unlisted")}}, now)
    await store_batch([
        PendingWrite(single(pub, "public", now), a),
        PendingWrite(single(priv_a, "unlisted", now), a),
        PendingWrite(single(priv_b, "unlisted", now), b),
        PendingWrite(batch, b),  # names B's unlisted report: B only
        PendingWrite(single(old_a, "unlisted", now - timedelta(days=30)), a),  # grant and status too old ...
        PendingWrite(fetched(FORGED, {"code": pub}, {"reportData": {"report": report(pub, "public")}}, now), a),
    ])
    async with pg() as db:  # ... until another query of the report grants it to A today (AC3)
        await set_scope(db, tenant_id=a)
        await grant_codes(db, a, [old_a], now)
        await db.commit()
    ours = {pub, priv_a, priv_b, old_a, batch_pub}

    assert await listed(pg, a, since, ours) == {pub, priv_a, old_a}
    assert await listed(pg, b, since, ours) == {pub, priv_b, batch_pub}
    assert await listed(pg, None, since, ours) == {pub}


async def test_the_backfill_flags_exactly_what_the_old_lookup_accepted(pg, tenants):
    a, _ = tenants
    now = datetime.now(UTC)
    one, two, three, forged, inexact = (code() for _ in range(5))
    # Unlisted (granted to this test's tenant only): other tests share the database and its lookup.
    real = single(one, "unlisted", now)
    batch = fetched(report_summaries_query(2), {"c0": two, "c1": three},
                    {"reportData": {"r0": report(two, "unlisted"), "r1": report(three, "unlisted")}}, now)
    fake = fetched(FORGED, {"code": forged}, {"reportData": {"report": report(forged, "unlisted")}}, now)
    await store_batch([PendingWrite(f, a) for f in (real, batch, fake)])
    loose = {"code": inexact}  # our query's key, but the row names a code its params don't give
    loose_key = _flight_key(REPORT_SUMMARY, loose)
    keys = [real.query_key, batch.query_key, fake.query_key, loose_key]
    async with pg() as db:
        await db.execute(RawFetch.__table__.insert().values(
            query_key=loose_key, operation_name="ReportSummary", params=loose, report_code=None,
            report_codes=[inexact, code()], fetched_at=now, payload={"data": {}}, own_summary=True,
        ))
        await db.execute(sa.update(RawFetch).where(RawFetch.query_key.in_(keys)).values(own_summary=False))
        await db.commit()

    spec = importlib.util.spec_from_file_location("migration_0021", _MIGRATION)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    async with pg() as db:
        await (await db.connection()).run_sync(migration.backfill)
        await db.commit()
        flagged = dict((await db.execute(
            sa.select(RawFetch.query_key, RawFetch.own_summary).where(RawFetch.query_key.in_(keys))
        )).all())
    assert flagged == {real.query_key: True, batch.query_key: True, fake.query_key: False, loose_key: False}
