"""US3 GATING: two-tenant isolation matrix (contracts/tenant-scoping.md).

Two users with look-alike data; neither can read, list, mutate, or export the other's
conversations / raids / profile / reports by any means (guessed ids, direct ids). Cross-
tenant access returns 404/empty, never the other tenant's data. Also covers the WCL cache
scope key and session-invalidation (disable/revoke) used to stop an in-flight socket.
"""

from __future__ import annotations

import uuid

import pytest

from backend.app.auth.dependencies import authenticate_session
from backend.app.db import repository as repo


@pytest.fixture
async def tenant_b(make_authed_client):
    b = await make_authed_client("userb@example.com")
    try:
        yield b
    finally:
        await b.client.aclose()


async def _seed_conversation(session_factory, tid, title="Secret raid"):
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash", title=title, tenant_id=tid)
        await repo.add_message(s, conv.id, "user", "my private question", tenant_id=tid)
        await s.commit()
        return conv.id


# --- Conversations ------------------------------------------------------------


async def test_conversations_isolated(as_user, tenant_b, session_factory):
    await _seed_conversation(session_factory, as_user.tenant_id, "A's raid")
    await _seed_conversation(session_factory, tenant_b.tenant_id, "B's raid")

    a_list = (await as_user.client.get("/api/conversations")).json()["conversations"]
    b_list = (await tenant_b.client.get("/api/conversations")).json()["conversations"]
    assert len(a_list) == 1 and a_list[0]["title"] == "A's raid"
    assert len(b_list) == 1 and b_list[0]["title"] == "B's raid"


async def test_cannot_read_foreign_conversation_by_id(as_user, tenant_b, session_factory):
    b_conv = await _seed_conversation(session_factory, tenant_b.tenant_id)
    # A guesses / knows B's real conversation id → 404, never B's data.
    resp = await as_user.client.get(f"/api/conversations/{b_conv}")
    assert resp.status_code == 404


async def test_cannot_delete_foreign_conversation(as_user, tenant_b, session_factory):
    b_conv = await _seed_conversation(session_factory, tenant_b.tenant_id)
    resp = await as_user.client.delete(f"/api/conversations/{b_conv}")
    assert resp.status_code == 404
    # B's conversation still exists.
    assert (await tenant_b.client.get(f"/api/conversations/{b_conv}")).status_code == 200


async def test_guessing_random_ids_is_404(as_user):
    assert (await as_user.client.get(f"/api/conversations/{uuid.uuid4()}")).status_code == 404


# --- Raids --------------------------------------------------------------------


async def test_raids_isolated(as_user, tenant_b, session_factory):
    async with session_factory() as s:
        await repo.upsert_tracked_raid(s, tenant_id=as_user.tenant_id, report_code="AAAA", label="A raid")
        await repo.upsert_tracked_raid(s, tenant_id=tenant_b.tenant_id, report_code="BBBB", label="B raid")
        await s.commit()

    a_codes = [r["report_code"] for r in (await as_user.client.get("/api/raids")).json()["raids"]]
    b_codes = [r["report_code"] for r in (await tenant_b.client.get("/api/raids")).json()["raids"]]
    assert a_codes == ["AAAA"]
    assert b_codes == ["BBBB"]
    # A cannot investigate B's report (not in A's tenant) → 404.
    assert (await as_user.client.post("/api/raids/BBBB/investigate", json={})).status_code == 404


# --- Profile ------------------------------------------------------------------


async def test_profile_isolated(as_user, tenant_b, session_factory, monkeypatch):
    monkeypatch.setattr("backend.app.api.profile.schedule_character_guide", lambda *_: None)
    async with session_factory() as s:
        await repo.upsert_self(s, tenant_id=as_user.tenant_id, name="ASelf", server="S", region="US")
        await s.commit()

    a_prof = (await as_user.client.get("/api/profile")).json()
    b_prof = (await tenant_b.client.get("/api/profile")).json()
    assert a_prof["self"]["name"] == "ASelf"
    assert b_prof["self"] is None  # B sees nothing of A's


# --- WCL cache scope (FR-019) -------------------------------------------------


def test_wcl_cache_key_scoped_by_tenant():
    from wcl_agent.cache import cache_key

    q, v = "query reportData", {"code": "ABC"}
    key_a = cache_key(q, v, prefix="tenant-a")
    key_b = cache_key(q, v, prefix="tenant-b")
    assert key_a != key_b  # a cached lookup never crosses tenants


# --- Session invalidation stops an in-flight socket (FR-023) ------------------


async def test_disabled_user_session_becomes_invalid(as_user, session_factory):
    from backend.app.repositories import users as users_repo

    # Session is valid now.
    assert await authenticate_session(as_user.session_token) is not None
    # Admin disables the user.
    async with session_factory() as s:
        user = await users_repo.get_user_by_id(s, as_user.user_id)
        await users_repo.set_status(s, user, status="disabled")
        await s.commit()
    # Next revalidation (what the WS does each turn) now fails → socket would close.
    assert await authenticate_session(as_user.session_token) is None


async def test_revoked_session_becomes_invalid(as_user, session_factory):
    from backend.app.auth import sessions as session_svc

    assert await authenticate_session(as_user.session_token) is not None
    async with session_factory() as s:
        await session_svc.revoke_all_user_sessions(s, as_user.user_id)
        await s.commit()
    assert await authenticate_session(as_user.session_token) is None
