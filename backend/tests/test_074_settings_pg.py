"""Profile settings writes on real Postgres under RLS (074): the upserts run as the runtime
role on a tenant-scoped session. Skipped unless ``TEST_DATABASE_URL`` points at a migrated
Postgres (runtime role), like test_rls.py (``pg.py up <name>`` prints it)."""

from __future__ import annotations

import os
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.db import repository as repo
from backend.app.tenancy.context import RequestIdentity, tenant_session

_PG_URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"),
    reason="needs TEST_DATABASE_URL pointing at a migrated Postgres (runtime role).",
)


@pytest.fixture
async def maker():
    engine = create_async_engine(_PG_URL, pool_pre_ping=True)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_save_and_skip_upsert_under_rls(maker):
    tenant_id = uuid.uuid4()
    async with maker() as s:
        await s.execute(sa.text("INSERT INTO tenants (id, name) VALUES (:id, 'x')"), {"id": tenant_id})
        await s.commit()
    me = RequestIdentity(
        user_id=uuid.uuid4(), tenant_id=tenant_id, membership_role="tenant_admin",
        is_platform_admin=False, session_id=uuid.uuid4(),
    )

    async with tenant_session(me, maker) as db:
        assert await repo.get_profile_settings(db, tenant_id=tenant_id) == (None, True)
        await repo.set_main_selection(db, tenant_id=tenant_id, main_class="Druid", main_spec=None, main_content="raid")
    async with tenant_session(me, maker) as db:
        await repo.set_main_selection(db, tenant_id=tenant_id, main_class="Druid", main_spec="Feral", main_content="both")
        await repo.skip_onboarding(db, tenant_id=tenant_id)
    async with tenant_session(me, maker) as db:
        first = (await repo.get_profile_settings(db, tenant_id=tenant_id))[0].onboarding_dismissed_at
        await repo.skip_onboarding(db, tenant_id=tenant_id)
    async with tenant_session(me, maker) as db:
        row, pending = await repo.get_profile_settings(db, tenant_id=tenant_id)
        assert (row.main_class, row.main_spec, row.main_content, pending) == ("Druid", "Feral", "both", False)
        assert row.onboarding_dismissed_at == first
