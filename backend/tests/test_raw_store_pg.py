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


async def test_db_first_read_as_the_runtime_role(pg, tenants):
    """sc-129 on Postgres: the read service scopes its own transaction to the turn's tenant."""
    from backend.app.services.raw_fetch_reads import read_stored_fetch
    from backend.app.tenancy.context import RequestIdentity, current_identity

    a, b = tenants
    c = code()
    ended = int((NOW - timedelta(days=2)).timestamp() * 1000)
    row = fetched(TABLE_Q, {"code": c}, {"reportData": {"report": {"table": 1}}})
    await store_batch([
        PendingWrite(fetched(REPORT_SUMMARY, {"code": c},
                             {"reportData": {"report": {"code": c, "visibility": "unlisted", "endTime": ended}}})),
        PendingWrite(row, a),
    ])

    async def as_tenant(tenant):
        token = current_identity.set(RequestIdentity(uuid.uuid4(), tenant, "member", False, uuid.uuid4()))
        try:
            return await read_stored_fetch(row.query_key, row.query, row.variables)
        finally:
            current_identity.reset(token)

    assert json.loads((await as_tenant(a)).content) == {"data": {"reportData": {"report": {"table": 1}}}}
    assert await as_tenant(b) is None


async def test_the_045_probe_budget_and_visibility_clause_on_postgres(pg, tenants):
    """045 sc-295: a miss is one statement, a granted hit at most four (with one set_config),
    the payload comes back as bytes, and the clause works as the runtime role under RLS."""
    from sqlalchemy import event, select

    from backend.app.repositories.raw_fetches import fetch_visible_clause, probe_visible_fetch

    a, b = tenants
    c, p = code(), code()
    ended = int((NOW - timedelta(days=2)).timestamp() * 1000)
    status = lambda x, v: fetched(REPORT_SUMMARY, {"code": x},  # noqa: E731
                                  {"reportData": {"report": {"code": x, "visibility": v, "endTime": ended}}})
    own = fetched(TABLE_Q, {"code": c}, {"reportData": {"report": {"table": c}}})
    pub = fetched(TABLE_Q, {"code": p}, {"reportData": {"report": {"table": p}}})
    await store_batch([PendingWrite(status(c, "unlisted")), PendingWrite(status(p, "public")),
                       PendingWrite(own, a), PendingWrite(pub, a)])
    since = NOW - timedelta(days=1)
    seen: list[str] = []
    engine = pg.kw["bind"].sync_engine
    listener = lambda conn, cur, stmt, params, ctx, many: seen.append(stmt)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        async with pg() as db:
            miss = await probe_visible_fetch(db, "no-such-key", tenant_id=a, since=since, fresh=lambda f, s: True)
            assert miss.outcome == "miss" and len(seen) == 1
            seen.clear()
            hit = await probe_visible_fetch(db, own.query_key, tenant_id=a, since=since, fresh=lambda f, s: True)
            assert hit.outcome == "hit" and not hit.shared and isinstance(hit.body, bytes)
            assert len(seen) == 4 and sum("set_config" in s for s in seen) == 1
            assert json.loads(hit.body) == {"data": {"reportData": {"report": {"table": c}}}}
        async with pg() as db:
            seen.clear()
            shared = await probe_visible_fetch(db, pub.query_key, tenant_id=b, since=since, fresh=lambda f, s: True)
            assert shared.outcome == "hit" and shared.shared and len(seen) == 3  # public: no set_config
        async with pg() as db:
            hidden = await probe_visible_fetch(db, own.query_key, tenant_id=b, since=since, fresh=lambda f, s: True)
            assert hidden.outcome == "not_visible"
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    async with pg() as db:  # the clause by column, scoped to B: A's grant is invisible under RLS
        await set_scope(db, tenant_id=b)
        keys = set(await db.scalars(select(sa.literal_column("query_key")).select_from(sa.table("raw_fetches")).where(
            fetch_visible_clause(sa.literal_column("raw_fetches.query_key"), tenant_id=b, since=since),
            sa.literal_column("raw_fetches.query_key").in_([own.query_key, pub.query_key]),
        )))
    assert keys == {pub.query_key}
