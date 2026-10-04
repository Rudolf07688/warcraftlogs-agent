"""Profile CRUD + invariants (feature 005 / US1): single self, one main guild."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from backend.app.db import repository as repo


# --- Repository-level invariants (tenant-scoped) ------------------------------


async def test_upsert_self_keeps_single_row(session, tenant_id):
    await repo.upsert_self(session, tenant_id=tenant_id, name="Thrall", server="Stormrage", region="US")
    await repo.upsert_self(session, tenant_id=tenant_id, name="Jaina", server="Proudmoore", region="US")
    await session.commit()

    self_char, friends, guild = await repo.get_profile(session, tenant_id=tenant_id)
    assert self_char is not None
    assert self_char.name == "Jaina"  # replaced, not duplicated
    # Feature 008: the resolved spec is reset on upsert; the background task re-resolves it
    # and points the character at the shared spec guide (no per-character guide columns).
    assert self_char.active_spec is None
    assert friends == []
    assert guild is None


async def test_set_guild_replaces_single_row(session, tenant_id):
    await repo.set_guild(session, tenant_id=tenant_id, name="Old", server="Stormrage", region="US")
    await repo.set_guild(session, tenant_id=tenant_id, name="New", server="Area 52", region="US")
    await session.commit()

    guild = await repo.get_guild_profile(session, tenant_id=tenant_id)
    assert guild is not None
    assert guild.name == "New"  # one-main-guild limit (FR-003)
    _, _, g = await repo.get_profile(session, tenant_id=tenant_id)
    assert g is not None and g.name == "New"


async def test_add_friend_rejects_identical_duplicate(session, tenant_id):
    await repo.add_friend(session, tenant_id=tenant_id, name="Muradin", server="Ironforge", region="EU")
    await session.commit()
    with pytest.raises(IntegrityError):
        await repo.add_friend(session, tenant_id=tenant_id, name="Muradin", server="Ironforge", region="EU")
        await session.flush()


async def test_same_character_allowed_in_different_tenants(session, tenant_id, other_tenant_id):
    # Per-tenant uniqueness: the same identity is fine across tenants (feature 006).
    await repo.add_friend(session, tenant_id=tenant_id, name="Muradin", server="Ironforge", region="EU")
    await repo.add_friend(session, tenant_id=other_tenant_id, name="Muradin", server="Ironforge", region="EU")
    await session.commit()
    assert len(await repo.list_friend_characters(session, tenant_id=tenant_id)) == 1
    assert len(await repo.list_friend_characters(session, tenant_id=other_tenant_id)) == 1


async def test_delete_friend(session, tenant_id):
    f = await repo.add_friend(session, tenant_id=tenant_id, name="Vol'jin", server="Sen'jin", region="US")
    await session.commit()
    assert await repo.delete_friend(session, f.id, tenant_id=tenant_id) is True
    await session.commit()
    _, friends, _ = await repo.get_profile(session, tenant_id=tenant_id)
    assert friends == []


# --- Endpoint smoke (authenticated; scheduling stubbed) -----------------------


async def test_profile_endpoints_roundtrip(as_user, monkeypatch):
    # Don't spawn real guide tasks (they'd hit WCL / the model).
    monkeypatch.setattr("backend.app.api.profile.schedule_character_guide", lambda *_: None)
    monkeypatch.setattr("backend.app.api.profile.schedule_guild_summary", lambda *_: None)

    client = as_user.client
    # Empty profile.
    empty = (await client.get("/api/profile")).json()
    assert empty["self"] is None and empty["friends"] == [] and empty["guild"] is None

    # Set self (serialized under the "self" key).
    r = await client.put(
        "/api/profile/self", json={"name": "Thrall", "server": "Stormrage", "region": "US"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "self"

    # Add a friend, then a duplicate → 409.
    r = await client.post(
        "/api/profile/friends", json={"name": "Aggra", "server": "Stormrage", "region": "US"}
    )
    assert r.status_code == 201
    dup = await client.post(
        "/api/profile/friends", json={"name": "Aggra", "server": "Stormrage", "region": "US"}
    )
    assert dup.status_code == 409

    g = await client.put(
        "/api/profile/guild", json={"name": "Horde", "server": "Orgrimmar", "region": "US"}
    )
    assert g.status_code == 200

    prof = (await client.get("/api/profile")).json()
    assert prof["self"]["name"] == "Thrall"
    assert len(prof["friends"]) == 1
    assert prof["guild"]["name"] == "Horde"
