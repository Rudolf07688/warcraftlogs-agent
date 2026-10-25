"""Pinned chats (feature 019 / sc-165): repository rules and the tenant-scoped PATCH API.

Pins are per workspace, stored as ``conversations.pinned_at``. A foreign or unknown id
reads as not found and changes nothing (FR-008), and pinning never touches
``updated_at`` (FR-009).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from backend.app.db import repository as repo

_MODEL = "gemini-3.6-flash"
_OLD = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def _conversation(session, tenant_id, *, title=None):
    conv = await repo.create_conversation(session, model=_MODEL, title=title, tenant_id=tenant_id)
    conv.updated_at = _OLD  # a fixed activity time, to prove pinning leaves it alone
    await session.commit()
    return conv


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite drops the zone


# --- Repository ----------------------------------------------------------------


async def test_pin_sets_pinned_at_and_unpin_clears_it(session, tenant_id):
    conv = await _conversation(session, tenant_id)
    assert conv.pinned_at is None

    pinned = await repo.set_conversation_pinned(session, conv.id, True, tenant_id=tenant_id)
    assert pinned is not None and pinned.pinned_at is not None

    unpinned = await repo.set_conversation_pinned(session, conv.id, False, tenant_id=tenant_id)
    assert unpinned is not None and unpinned.pinned_at is None


async def test_repeated_pin_keeps_the_first_pin_time(session, tenant_id):
    conv = await _conversation(session, tenant_id)
    first = (await repo.set_conversation_pinned(session, conv.id, True, tenant_id=tenant_id)).pinned_at
    again = (await repo.set_conversation_pinned(session, conv.id, True, tenant_id=tenant_id)).pinned_at
    assert again == first


async def test_pinning_leaves_updated_at_alone(session, tenant_id):
    conv = await _conversation(session, tenant_id)
    for pinned in (True, False):
        row = await repo.set_conversation_pinned(session, conv.id, pinned, tenant_id=tenant_id)
        assert _aware(row.updated_at) == _OLD


async def test_foreign_or_unknown_conversation_is_none_and_unchanged(
    session, tenant_id, other_tenant_id
):
    conv = await _conversation(session, tenant_id)
    assert await repo.set_conversation_pinned(session, conv.id, True, tenant_id=other_tenant_id) is None
    assert await repo.set_conversation_pinned(session, uuid.uuid4(), True, tenant_id=tenant_id) is None
    row = await repo.get_conversation_row(session, conv.id, tenant_id=tenant_id)
    assert row.pinned_at is None


async def test_list_carries_pin_state_in_activity_order(session, tenant_id):
    older = await _conversation(session, tenant_id, title="older")
    newer = await _conversation(session, tenant_id, title="newer")
    newer.updated_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
    await session.commit()
    await repo.set_conversation_pinned(session, older.id, True, tenant_id=tenant_id)

    listed = await repo.list_conversations(session, tenant_id=tenant_id)
    # Order stays by activity; the client builds the Pinned group from pinned_at.
    assert [c.title for c in listed] == ["newer", "older"]
    assert [c.pinned_at is not None for c in listed] == [False, True]


# --- API -----------------------------------------------------------------------


@pytest.fixture
async def tenant_b(make_authed_client):
    b = await make_authed_client("userb@example.com")
    try:
        yield b
    finally:
        await b.client.aclose()


async def _seed(session_factory, tid, title="Pinned raid"):
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model=_MODEL, title=title, tenant_id=tid)
        await s.commit()
        return conv.id


async def test_patch_pins_and_unpins(as_user, session_factory):
    conv_id = await _seed(session_factory, as_user.tenant_id)

    resp = await as_user.client.patch(f"/api/conversations/{conv_id}", json={"pinned": True})
    assert resp.status_code == 200
    assert resp.json()["pinned_at"] is not None
    listed = (await as_user.client.get("/api/conversations")).json()["conversations"]
    assert listed[0]["pinned_at"] is not None

    resp = await as_user.client.patch(f"/api/conversations/{conv_id}", json={"pinned": False})
    assert resp.status_code == 200
    assert resp.json()["pinned_at"] is None


async def test_patch_foreign_conversation_is_404(as_user, tenant_b, session_factory):
    b_conv = await _seed(session_factory, tenant_b.tenant_id)
    resp = await as_user.client.patch(f"/api/conversations/{b_conv}", json={"pinned": True})
    assert resp.status_code == 404
    b_view = (await tenant_b.client.get(f"/api/conversations/{b_conv}")).json()
    assert b_view["pinned_at"] is None


async def test_patch_unknown_conversation_is_404(as_user):
    resp = await as_user.client.patch(f"/api/conversations/{uuid.uuid4()}", json={"pinned": True})
    assert resp.status_code == 404


async def test_patch_without_csrf_is_refused(as_user, session_factory):
    conv_id = await _seed(session_factory, as_user.tenant_id)
    resp = await as_user.client.patch(
        f"/api/conversations/{conv_id}", json={"pinned": True}, headers={"x-csrf-token": ""}
    )
    assert resp.status_code in (401, 403)
    async with session_factory() as s:
        row = await repo.get_conversation_row(s, conv_id, tenant_id=as_user.tenant_id)
        assert row.pinned_at is None


@pytest.mark.parametrize("body", [{}, {"pinned": "yes"}, {"pinned": True, "title": "x"}])
async def test_patch_rejects_bad_bodies(as_user, session_factory, body):
    conv_id = await _seed(session_factory, as_user.tenant_id)
    resp = await as_user.client.patch(f"/api/conversations/{conv_id}", json=body)
    assert resp.status_code == 422


async def test_pinned_conversation_can_be_deleted(as_user, session_factory):
    conv_id = await _seed(session_factory, as_user.tenant_id)
    async with session_factory() as s:
        await repo.set_conversation_pinned(s, conv_id, True, tenant_id=as_user.tenant_id)
        await s.commit()
    assert (await as_user.client.delete(f"/api/conversations/{conv_id}")).status_code == 204
    assert (await as_user.client.get(f"/api/conversations/{conv_id}")).status_code == 404
