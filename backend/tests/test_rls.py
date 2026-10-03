"""Postgres-only RLS verification (US3, research R4).

Skipped unless ``TEST_DATABASE_URL`` points at a Postgres instance where migrations have
been applied under the runtime (non-privileged) role. Verifies the guide's RLS matrix:
even with the application ``WHERE tenant_id`` predicate deliberately omitted, RLS blocks
cross-tenant reads/writes; a missing ``app.tenant_id`` yields no rows; a reused pooled
connection does not retain a prior transaction's tenant context.

Run against Postgres from quickstart.md; these are the automated counterpart.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_PG_URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"),
    reason="RLS tests require TEST_DATABASE_URL pointing at a migrated Postgres (runtime role).",
)


@pytest.fixture
async def pg_sessionmaker():
    engine = create_async_engine(_PG_URL, pool_pre_ping=True)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _set_tenant(session, tenant_id: str) -> None:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id}
    )


async def test_missing_app_tenant_returns_no_rows(pg_sessionmaker):
    async with pg_sessionmaker() as s:
        # No app.tenant_id set → the RLS predicate matches nothing.
        rows = (await s.execute(text("SELECT count(*) FROM conversations"))).scalar()
        assert rows == 0


async def test_cross_tenant_select_blocked_without_app_predicate(pg_sessionmaker):
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    async with pg_sessionmaker() as s:
        await _set_tenant(s, tenant_a)
        # Even selecting with NO WHERE tenant_id, RLS restricts to tenant A.
        res = await s.execute(text("SELECT tenant_id FROM conversations"))
        assert all(str(r[0]) == tenant_a for r in res.fetchall())
        await s.rollback()

    # A new transaction on a (possibly pooled) connection must NOT retain tenant_a.
    async with pg_sessionmaker() as s:
        rows = (await s.execute(text("SELECT count(*) FROM conversations"))).scalar()
        assert rows == 0  # app.tenant_id is unset again → no leakage


async def test_write_outside_tenant_rejected(pg_sessionmaker):
    tenant_a = str(uuid.uuid4())
    other = str(uuid.uuid4())
    async with pg_sessionmaker() as s:
        await _set_tenant(s, tenant_a)
        # WITH CHECK must reject an insert whose tenant_id != app.tenant_id.
        with pytest.raises(Exception):
            await s.execute(
                text(
                    "INSERT INTO conversations (id, tenant_id, title, model) "
                    "VALUES (:id, :tid, 'x', 'm')"
                ),
                {"id": str(uuid.uuid4()), "tid": other},
            )
            await s.flush()
        await s.rollback()
