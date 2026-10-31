"""Overlapping approve / cancel of one proposal on real Postgres (feature 034 / sc-242).

Two calls for the same proposal must apply it once and save exactly one follow-up line, with
no 500. Only Postgres has the row lock (``FOR UPDATE``) the fix relies on, so these tests are
skipped unless ``TEST_DATABASE_URL`` points at a migrated Postgres (runtime role), like
test_rls.py. Run recipe: specs/034-epic203-qa-fixes/quickstart.md §2.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.api import proposals as routes
from backend.app.db import repository as repo
from backend.app.db import session as db_session
from backend.app.db.models import Message, UserCharacter
from backend.app.repositories import tenants as tenants_repo
from backend.app.repositories import users as users_repo
from backend.app.schemas import ProfileChangeIn
from backend.app.services import profile_proposals as proposals
from backend.app.tenancy.context import RequestIdentity, tenant_scope

_PG_URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"),
    reason="Overlap tests require TEST_DATABASE_URL pointing at a migrated Postgres (runtime role).",
)


@pytest.fixture
async def pg(monkeypatch):
    """Point the app's sessions at Postgres; no guide jobs (they would call WCL / the model)."""
    engine = create_async_engine(_PG_URL, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "SessionLocal", maker)
    monkeypatch.setattr(proposals, "schedule_character_guide", lambda *_: None)
    yield maker
    await engine.dispose()


@pytest.fixture
async def me(pg) -> RequestIdentity:
    """A fresh user and tenant per test (the database is a throwaway container)."""
    async with pg() as db:
        user = await users_repo.create_user(db, email=f"race-{uuid.uuid4().hex}@example.com")
        tenant = await tenants_repo.create_tenant(db, name="race")
        await tenants_repo.create_membership(db, tenant_id=tenant.id, user_id=user.id, role="tenant_admin")
        await db.commit()
    return RequestIdentity(
        user_id=user.id,
        tenant_id=tenant.id,
        membership_role="tenant_admin",
        is_platform_admin=False,
        session_id=uuid.uuid4(),
    )


@pytest.fixture
async def proposal(me):
    async with tenant_scope(me.tenant_id, user_id=me.user_id) as db:
        conv = await repo.create_conversation(db, "gemini-3.6-flash", tenant_id=me.tenant_id)
    changes = [
        ProfileChangeIn(action="add", target="friend", name=name, realm="Tarren Mill", region="eu")
        for name in ("Kazrok", "Brightmane")
    ]
    return await proposals.create_proposal(me, conv.id, changes)


@pytest.fixture
def slow_follow_up(monkeypatch):
    """Hold the row lock a little longer while the line is saved, so the second call is
    certain to arrive while the first one still holds it."""
    real = repo.add_message

    async def slow(*args, **kwargs):
        await asyncio.sleep(0.3)
        return await real(*args, **kwargs)

    monkeypatch.setattr(routes.repo, "add_message", slow)


async def _state(me, proposal) -> tuple[list[str], list[str]]:
    """(friend names, agent lines in the proposal's chat)."""
    async with tenant_scope(me.tenant_id, user_id=me.user_id) as db:
        friends = await db.scalars(
            sa.select(UserCharacter.name).where(UserCharacter.tenant_id == me.tenant_id).order_by(UserCharacter.name)
        )
        lines = await db.scalars(
            sa.select(Message.content).where(
                Message.conversation_id == proposal.conversation_id, Message.role == "agent"
            )
        )
        return list(friends), list(lines)


@pytest.mark.parametrize(
    ("action", "status", "friends", "line"),
    [
        ("approve", "applied", ["Brightmane", "Kazrok"], "Done. Added 2 friends: Kazrok and Brightmane."),
        ("cancel", "cancelled", [], "Cancelled. Your profile is unchanged."),
    ],
)
async def test_overlapping_decisions_apply_once_and_save_one_line(
    me, proposal, slow_follow_up, action, status, friends, line
):
    handler = getattr(routes, action)
    first, second = await asyncio.gather(handler(proposal.id, me), handler(proposal.id, me))

    assert first.proposal.status == second.proposal.status == status  # no 500, no 409
    assert [d.follow_up is not None for d in (first, second)].count(True) == 1
    assert await _state(me, proposal) == (friends, [line])


async def test_a_failed_follow_up_rolls_the_whole_decision_back(me, proposal, monkeypatch):
    async def broken(*_, **__):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(routes.repo, "add_message", broken)
    with pytest.raises(RuntimeError):
        await routes.approve(proposal.id, me)
    assert (await proposals.get_proposal(me, proposal.id)).status == "pending"
    assert await _state(me, proposal) == ([], [])  # no friend added, no line
