"""The raw store on real Postgres (feature 039, migration 0018): RLS on grants, the JSONB
``report_codes ?`` delete and the whole visibility path as the runtime role.

Skipped unless ``TEST_DATABASE_URL`` points at a migrated Postgres (runtime role), like
test_rls.py. Run recipe: specs/039-local-first-data/quickstart.md §2.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.db import session as db_session
from backend.app.repositories import tenants as tenants_repo
from backend.app.repositories.raw_fetches import grant_codes, read_visible_fetch
from backend.app.services.fetch_persistence import PendingWrite, store_batch
from backend.app.tenancy.context import set_scope
from wcl_agent.client.queries import REPORT_SUMMARY
from wcl_agent.client.wcl_client import FetchedResponse, ReportGone, _flight_key

_PG_URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"),
    reason="Postgres tests require TEST_DATABASE_URL pointing at a migrated Postgres (runtime role).",
)

NOW = datetime.now(UTC)
TABLE_Q = "query ReportQ($code: String!) { reportData { report(code: $code) { table } } }"


def fetched(query: str, variables: dict, data: dict, at: datetime = NOW) -> FetchedResponse:
    body = json.dumps({"data": {"_cost": {"pointsSpentThisHour": 1}, **data}}).encode()
    return FetchedResponse(_flight_key(query, variables), query, variables, body, at)


def code() -> str:
    return uuid.uuid4().hex[:16]  # the database outlives one run: fresh codes per test


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
        a = await tenants_repo.create_tenant(db, name="raw-039-a")
        b = await tenants_repo.create_tenant(db, name="raw-039-b")
        await db.commit()
    return a.id, b.id


async def read(pg, item: FetchedResponse, tenant: uuid.UUID | None):
    async with pg() as db:
        await set_scope(db, tenant_id=tenant)
        return await read_visible_fetch(
            db, item.query_key, tenant_id=tenant, since=NOW - timedelta(days=7),
            fresh=lambda fetched_at, statuses: True,
        )


async def test_rls_hides_and_refuses_another_tenants_grants(pg, tenants):
    a, b = tenants
    c = code()
    await store_batch([PendingWrite(fetched(TABLE_Q, {"code": c}, {"reportData": {"report": {}}}), b)])
    async with pg() as db:
        await set_scope(db, tenant_id=a)
        # No tenant predicate on purpose: RLS alone must hide B's grant from A.
        visible = await db.scalar(sa.text("SELECT count(*) FROM raw_fetch_grants WHERE report_code = :c"), {"c": c})
        assert visible == 0
    async with pg() as db:
        await set_scope(db, tenant_id=b)
        own = await db.scalar(sa.text("SELECT count(*) FROM raw_fetch_grants WHERE report_code = :c"), {"c": c})
        assert own == 1
    async with pg() as db:
        await set_scope(db, tenant_id=a)
        with pytest.raises(sa.exc.DBAPIError):  # WITH CHECK: A can't write a grant for B
            await grant_codes(db, b, [c], NOW)
            await db.flush()


async def test_the_visibility_rule_on_postgres(pg, tenants):
    a, b = tenants
    unlisted, public = code(), code()
    rows = {c: fetched(TABLE_Q, {"code": c}, {"reportData": {"report": {"table": c}}}) for c in (unlisted, public)}
    status = lambda c, v: fetched(REPORT_SUMMARY, {"code": c},  # noqa: E731
                                  {"reportData": {"report": {"code": c, "visibility": v, "endTime": 1}}})
    await store_batch([PendingWrite(status(unlisted, "unlisted")), PendingWrite(status(public, "public")),
                       PendingWrite(rows[unlisted], a), PendingWrite(rows[public], a)])

    assert json.loads(await read(pg, rows[unlisted], a))["data"]["reportData"]["report"]["table"] == unlisted
    assert await read(pg, rows[unlisted], b) is None
    assert await read(pg, rows[unlisted], None) is None
    assert await read(pg, rows[public], b) is not None


async def test_gone_deletes_every_row_naming_the_code_via_the_gin_operator(pg, tenants):
    a, _ = tenants
    gone, kept = code(), code()
    batch_q = "query B($c0: String!, $c1: String!) { reportData { r0: report(code: $c0) { t } r1: report(code: $c1) { t } } }"
    items = [fetched(TABLE_Q, {"code": gone}, {}), fetched(batch_q, {"c0": kept, "c1": gone}, {}),
             fetched(TABLE_Q, {"code": kept}, {})]
    await store_batch([PendingWrite(i, a) for i in items])
    await store_batch([PendingWrite(ReportGone((gone,), NOW))])
    async with pg() as db:
        left = set(await db.scalars(sa.text(
            "SELECT query_key FROM raw_fetches WHERE report_codes ? :g OR report_codes ? :k"), {"g": gone, "k": kept}))
    assert left == {items[2].query_key}


async def test_nul_escapes_overlong_labels_and_unchanged_payloads_on_postgres(pg):
    """JSONB rejects \\u0000 and varchar(32/120) rejects longer values: none may fail (sc-177)."""
    long_code = code() * 3  # 48 chars
    query = f"query {'Op' * 80}($code: String!) {{ reportData {{ report(code: $code) {{ t }} }} }}"
    first = fetched(query, {"code": long_code}, {"s": "a\u0000b"}, NOW - timedelta(hours=1))
    await store_batch([PendingWrite(first)])
    again = FetchedResponse(first.query_key, first.query, first.variables,
                            first.content.replace(b'"pointsSpentThisHour": 1', b'"pointsSpentThisHour": 5'), NOW)
    await store_batch([PendingWrite(again)])
    async with pg() as db:
        row = (await db.execute(sa.text(
            "SELECT operation_name, report_code, payload, fetched_at FROM raw_fetches "
            "WHERE query_key = :k"), {"k": first.query_key})).one()
    assert len(row.operation_name) == 120 and row.report_code is None
    assert row.payload == {"data": {"s": "ab"}}
    assert row.fetched_at == NOW  # unchanged payload: only fetched_at moved
