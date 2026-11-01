"""Concurrent messages in one conversation never collide on their number (feature 047, sc-255).

Two sessions add a message to the same conversation at the same time: both commit, with
distinct consecutive ``seq``. Real Postgres (row locks, READ COMMITTED, RLS as the runtime role);
skipped unless ``TEST_DATABASE_URL`` points at a migrated Postgres, like test_raw_store_pg.py.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.db import repository as repo
from backend.app.repositories import tenants as tenants_repo
from backend.app.tenancy.context import set_scope

_PG_URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"),
    reason="Postgres tests require TEST_DATABASE_URL pointing at a migrated Postgres (runtime role).",
)


@pytest.fixture
async def pg():
    engine = create_async_engine(_PG_URL, pool_pre_ping=True)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def scoped(maker, tenant: uuid.UUID):
    session = maker()
    await set_scope(session, tenant_id=tenant)
    return session


async def test_two_concurrent_adds_both_commit_with_consecutive_seq(pg):
    async with pg() as db:
        tenant = (await tenants_repo.create_tenant(db, name="seq-047")).id
        await db.commit()
    async with pg() as db:
        await set_scope(db, tenant_id=tenant)
        conv = await repo.create_conversation(db, model="m", tenant_id=tenant)
        await repo.add_message(db, conv.id, "user", "first", tenant_id=tenant)
        await db.commit()

    a, b = await scoped(pg, tenant), await scoped(pg, tenant)
    try:
        first = await repo.add_message(a, conv.id, "user", "from a", tenant_id=tenant)  # not committed yet
        second = asyncio.create_task(repo.add_message(b, conv.id, "agent", "from b", tenant_id=tenant))
        await asyncio.sleep(0.3)  # b is numbering its message while a's is still open
        await a.commit()
        second_msg = await second
        await b.commit()
    finally:
        await a.close()
        await b.close()

    assert (first.seq, second_msg.seq) == (1, 2)
    async with pg() as db:
        await set_scope(db, tenant_id=tenant)
        assert [m.seq for m in await repo.list_messages(db, conv.id, tenant_id=tenant)] == [0, 1, 2]


async def test_another_tenants_add_neither_waits_on_nor_changes_the_conversation(pg):
    """Tenant scoping is unchanged: the lock only ever finds the caller's own conversation, so
    another tenant naming this one (by id) is neither blocked by its open turn nor numbered
    into it; it fails exactly as before, on the numbering constraint."""
    async with pg() as db:
        owner = (await tenants_repo.create_tenant(db, name="seq-047-a")).id
        other = (await tenants_repo.create_tenant(db, name="seq-047-b")).id
        await db.commit()
    async with pg() as db:
        await set_scope(db, tenant_id=owner)
        conv = await repo.create_conversation(db, model="m", tenant_id=owner)
        await repo.add_message(db, conv.id, "user", "first", tenant_id=owner)
        await db.commit()

    a, b = await scoped(pg, owner), await scoped(pg, other)
    try:
        await repo.add_message(a, conv.id, "agent", "open turn", tenant_id=owner)  # holds the row
        with pytest.raises(IntegrityError):
            await asyncio.wait_for(repo.add_message(b, conv.id, "user", "intruder", tenant_id=other), 5)
        await a.commit()
    finally:
        await a.close()
        await b.close()
    async with pg() as db:
        await set_scope(db, tenant_id=owner)
        assert [m.content for m in await repo.list_messages(db, conv.id, tenant_id=owner)] == ["first", "open turn"]
