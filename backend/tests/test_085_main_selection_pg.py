"""085 (sc-583): the preamble's settings read under RLS on real Postgres. Another workspace's
row is invisible even when its id is asked for. Skipped unless ``TEST_DATABASE_URL`` points at a
migrated Postgres (runtime role), like test_074_settings_pg.py (``pg.py up <name>`` prints it)."""

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


def _member(tenant_id: uuid.UUID) -> RequestIdentity:
    return RequestIdentity(
        user_id=uuid.uuid4(), tenant_id=tenant_id, membership_role="tenant_admin",
        is_platform_admin=False, session_id=uuid.uuid4(),
    )


async def test_another_workspaces_main_is_never_read(maker):
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    async with maker() as s:
        for t in (mine, theirs):
            await s.execute(sa.text("INSERT INTO tenants (id, name) VALUES (:id, 'x')"), {"id": t})
        await s.commit()
    async with tenant_session(_member(theirs), maker) as db:
        await repo.set_main_selection(db, tenant_id=theirs, main_class="Mage", main_spec="Frost", main_content=None)
    async with tenant_session(_member(mine), maker) as db:
        await repo.set_main_selection(db, tenant_id=mine, main_class="Paladin", main_spec="Holy", main_content=None)

    async with tenant_session(_member(mine), maker) as db:
        assert await repo.get_main_selection(db, tenant_id=mine) == ("Paladin", "Holy")
        # The app predicate asks for the other workspace; RLS still hides its row.
        assert await repo.get_main_selection(db, tenant_id=theirs) == (None, None)
