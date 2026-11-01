"""The stored-reports lookup on real Postgres (feature 047, sc-324, migration 0020).

It walks the partial index ``ix_raw_fetches_summaries``, runs under a statement timeout, never
lists a forged summary row and reads a projection, not the stored payloads. Skipped unless
``TEST_DATABASE_URL`` points at a migrated Postgres (runtime role), like test_raw_store_pg.py.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.db import session as db_session
from backend.app.repositories import tenants as tenants_repo
from backend.app.repositories.raw_fetches import list_visible_summaries
from backend.app.services.fetch_persistence import PendingWrite, store_batch
from backend.app.tenancy.context import set_scope
from wcl_agent.client.queries import REPORT_SUMMARY
from wcl_agent.client.wcl_client import FetchedResponse, _flight_key

_PG_URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"),
    reason="Postgres tests require TEST_DATABASE_URL pointing at a migrated Postgres (runtime role).",
)

NOW = datetime.now(UTC)
ENDED = int((NOW - timedelta(days=3)).timestamp() * 1000)
FORGED = (
    "query ReportSummary($code: String!) { reportData { report(code: $code) "
    "{ code title startTime zone { name } masterData { actors { name } } fights { id name } } } }"
)


def code() -> str:
    return uuid.uuid4().hex[:16]  # the database outlives one run: fresh codes per test


def report(c: str) -> dict:
    return {
        "code": c, "visibility": "unlisted", "title": f"Raid {c}", "startTime": 1, "endTime": ENDED,
        "zone": {"id": 46, "name": "Zone"}, "guild": {"name": "G"},
        "masterData": {"actors": [{"id": i, "name": f"P{i}", "subType": "Warrior"} for i in range(20)]},
        "fights": [{"id": i, "name": "Boss", "encounterID": 1, "difficulty": 5, "kill": True, "size": 20,
                    "startTime": i, "friendlyPlayers": list(range(20))} for i in range(300)],
    }


def fetched(query: str, variables: dict, data: dict) -> FetchedResponse:
    body = json.dumps({"data": data}).encode()
    return FetchedResponse(_flight_key(query, variables), query, variables, body, NOW)


@pytest.fixture
async def pg(monkeypatch):
    engine = create_async_engine(_PG_URL, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "SessionLocal", maker)
    yield maker
    await engine.dispose()


@pytest.fixture
async def tenant(pg) -> uuid.UUID:
    async with pg() as db:
        t = await tenants_repo.create_tenant(db, name="raw-047")
        await db.commit()
    return t.id


async def test_the_lookup_is_strict_bounded_and_uses_the_index(pg, tenant):
    ours, forged = code(), code()
    real = fetched(REPORT_SUMMARY, {"code": ours}, {"reportData": {"report": report(ours)}})
    fake = fetched(FORGED, {"code": forged}, {"reportData": {"report": report(forged)}})
    await store_batch([PendingWrite(real, tenant), PendingWrite(fake, tenant)])

    seen: list[tuple[str, object]] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if "jsonb_object_agg" in statement:
            seen.append((statement, parameters))

    engine = pg.kw["bind"].sync_engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        async with pg() as db:
            await set_scope(db, tenant_id=tenant)
            bodies = await list_visible_summaries(db, tenant_id=tenant, since=NOW - timedelta(days=1), limit=500)
            timeout = await db.scalar(sa.text("SHOW statement_timeout"))
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    listed = {r["code"]: r for b in bodies for r in json.loads(b)["data"]["reportData"].values()}
    assert ours in listed and forged not in listed  # the forged row is visible, but not ours
    assert timeout == "2s"
    # A projection: the 300 fights and the actors' other fields never leave the database.
    assert set(listed[ours]) == {"code", "title", "startTime", "zone", "masterData"}
    assert max(len(b) for b in bodies) * 20 < len(real.content)

    [(statement, parameters)] = seen
    async with pg() as db:
        await set_scope(db, tenant_id=tenant)
        await db.execute(sa.text("SET LOCAL enable_seqscan = off"))
        raw = await db.connection()
        plan = (await raw.exec_driver_sql("EXPLAIN " + statement, parameters)).scalars().all()
    assert any("ix_raw_fetches_summaries" in line for line in plan), "\n".join(plan)
