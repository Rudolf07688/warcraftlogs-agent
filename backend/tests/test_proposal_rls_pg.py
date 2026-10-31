"""User-level RLS on ``profile_proposals`` on real Postgres (feature 036 / sc-222, migration 0017).

Two users of one tenant: with the application's ``user_id`` filter deliberately omitted, the
database itself hides, protects and refuses the other user's proposals. Skipped unless
``TEST_DATABASE_URL`` points at a migrated Postgres (runtime role), like test_rls.py. Run
recipe: specs/036-profile-write-hardening/quickstart.md §2.
"""

from __future__ import annotations

import os
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.db import repository as repo
from backend.app.db import session as db_session
from backend.app.repositories import tenants as tenants_repo
from backend.app.repositories import users as users_repo
from backend.app.schemas import ProfileChangeIn
from backend.app.services import profile_proposals as proposals
from backend.app.tenancy.context import RequestIdentity, set_scope, tenant_scope

_PG_URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"),
    reason="RLS tests require TEST_DATABASE_URL pointing at a migrated Postgres (runtime role).",
)


@pytest.fixture
async def pg(monkeypatch):
    engine = create_async_engine(_PG_URL, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "SessionLocal", maker)
    yield maker
    await engine.dispose()


def _identity(user_id: uuid.UUID, tenant_id: uuid.UUID) -> RequestIdentity:
    return RequestIdentity(
        user_id=user_id, tenant_id=tenant_id, membership_role="member",
        is_platform_admin=False, session_id=uuid.uuid4(),
    )


@pytest.fixture
async def two_users(pg) -> tuple[RequestIdentity, RequestIdentity]:
    """Users A and B in one fresh tenant (the database is a throwaway container)."""
    async with pg() as db:
        tenant = await tenants_repo.create_tenant(db, name="rls-036")
        users = []
        for who in ("a", "b"):
            user = await users_repo.create_user(db, email=f"rls-{who}-{uuid.uuid4().hex}@example.com")
            await tenants_repo.create_membership(db, tenant_id=tenant.id, user_id=user.id, role="member")
            users.append(user)
        await db.commit()
    return _identity(users[0].id, tenant.id), _identity(users[1].id, tenant.id)


async def _proposal_of(identity: RequestIdentity) -> uuid.UUID:
    async with tenant_scope(identity.tenant_id, user_id=identity.user_id) as db:
        conv = await repo.create_conversation(db, "gemini-3.6-flash", tenant_id=identity.tenant_id)
    change = ProfileChangeIn(action="add", target="friend", name="Kazrok", realm="Tarren Mill", region="eu")
    return (await proposals.create_proposal(identity, conv.id, [change])).id


async def test_another_user_of_the_tenant_cant_read_change_or_forge_a_proposal(pg, two_users):
    a, b = two_users
    b_proposal = await _proposal_of(b)
    async with pg() as db:
        await set_scope(db, tenant_id=a.tenant_id, user_id=a.user_id)
        # No user_id predicate here on purpose: RLS alone must hide B's row from A.
        visible = await db.scalar(
            sa.text("SELECT count(*) FROM profile_proposals WHERE tenant_id = :t"), {"t": str(a.tenant_id)}
        )
        assert visible == 0
        updated = await db.execute(
            sa.text("UPDATE profile_proposals SET status = 'cancelled' WHERE id = :id"), {"id": str(b_proposal)}
        )
        assert updated.rowcount == 0
        await db.rollback()

    async with pg() as db:
        await set_scope(db, tenant_id=a.tenant_id, user_id=a.user_id)
        # A row for B written in A's scope: WITH CHECK rejects it (before any foreign-key check).
        with pytest.raises(Exception, match="row-level security"):
            await db.execute(
                sa.text(
                    "INSERT INTO profile_proposals (id, tenant_id, user_id, conversation_id, items, expires_at) "
                    "VALUES (:id, :t, :u, :c, '[]', now())"
                ),
                {"id": str(uuid.uuid4()), "t": str(a.tenant_id), "u": str(b.user_id), "c": str(uuid.uuid4())},
            )
        await db.rollback()

    # B still sees and owns it; the service gives A not_found as before.
    assert (await proposals.get_proposal(b, b_proposal)).status == "pending"
    with pytest.raises(proposals.ProposalError):
        await proposals.get_proposal(a, b_proposal)


async def test_no_user_setting_sees_no_proposal(pg, two_users):
    _, b = two_users
    await _proposal_of(b)
    async with pg() as db:
        await set_scope(db, tenant_id=b.tenant_id)  # tenant only, as a background job would
        assert await db.scalar(sa.text("SELECT count(*) FROM profile_proposals")) == 0
        await db.rollback()
