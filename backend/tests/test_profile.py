"""Profile CRUD + invariants (feature 005 / US1, feature 012): own characters, friends, one guild."""

from __future__ import annotations

import pytest

from backend.app.db import repository as repo
from backend.app.db.models import UserCharacter


# --- Repository-level invariants (tenant-scoped) ------------------------------


async def test_own_characters_listed_in_creation_order(session, tenant_id):
    await repo.add_character(session, tenant_id=tenant_id, role="self", name="Thrall", server="Stormrage", region="US")
    await repo.add_character(session, tenant_id=tenant_id, role="self", name="Jaina", server="Proudmoore", region="US")
    await session.commit()

    own, friends, guild = await repo.get_profile(session, tenant_id=tenant_id)
    assert [c.name for c in own] == ["Thrall", "Jaina"]  # several own characters (FR-001)
    assert all(c.role == "self" for c in own)
    assert friends == []
    assert guild is None


async def test_own_duplicate_rejected_case_insensitively(session, tenant_id):
    await repo.add_character(session, tenant_id=tenant_id, role="self", name="Thrall", server="Stormrage", region="US")
    with pytest.raises(repo.CharacterConflict) as exc:
        await repo.add_character(session, tenant_id=tenant_id, role="self", name="thrall", server="STORMRAGE", region="us")
    assert exc.value.code == "duplicate_character"


async def test_identity_cannot_be_both_own_and_friend(session, tenant_id):
    await repo.add_character(session, tenant_id=tenant_id, role="friend", name="Aggra", server="S", region="US")
    await repo.add_character(session, tenant_id=tenant_id, role="self", name="Thrall", server="S", region="US")
    with pytest.raises(repo.CharacterConflict) as as_own:
        await repo.add_character(session, tenant_id=tenant_id, role="self", name="Aggra", server="S", region="US")
    assert as_own.value.code == "already_friend"
    with pytest.raises(repo.CharacterConflict) as as_friend:
        await repo.add_character(session, tenant_id=tenant_id, role="friend", name="Thrall", server="S", region="US")
    assert as_friend.value.code == "already_own"


async def test_own_character_limit(session, tenant_id):
    for i in range(repo.MAX_OWN_CHARACTERS):
        await repo.add_character(session, tenant_id=tenant_id, role="self", name=f"Alt{i}", server="S", region="US")
    with pytest.raises(repo.CharacterConflict) as exc:
        await repo.add_character(session, tenant_id=tenant_id, role="self", name="OneTooMany", server="S", region="US")
    assert exc.value.code == "character_limit"
    # The limit applies to own characters only; friends are uncapped.
    await repo.add_character(session, tenant_id=tenant_id, role="friend", name="Pal", server="S", region="US")


async def test_preexisting_self_row_is_first_own_character(session, tenant_id):
    # An upgrade leaves the single pre-feature self row untouched (FR-006).
    session.add(UserCharacter(tenant_id=tenant_id, role="self", name="Old", server="S", region="EU", raid_role="tank"))
    await session.commit()
    own = await repo.list_own_characters(session, tenant_id=tenant_id)
    assert [(c.name, c.raid_role) for c in own] == [("Old", "tank")]


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
    await repo.add_character(session, tenant_id=tenant_id, role="friend", name="Muradin", server="Ironforge", region="EU")
    await session.commit()
    with pytest.raises(repo.CharacterConflict) as exc:
        await repo.add_character(session, tenant_id=tenant_id, role="friend", name="Muradin", server="Ironforge", region="EU")
    assert exc.value.code == "duplicate_friend"


async def test_same_character_allowed_in_different_tenants(session, tenant_id, other_tenant_id):
    # Per-tenant uniqueness: the same identity is fine across tenants (feature 006).
    await repo.add_character(session, tenant_id=tenant_id, role="friend", name="Muradin", server="Ironforge", region="EU")
    await repo.add_character(session, tenant_id=other_tenant_id, role="friend", name="Muradin", server="Ironforge", region="EU")
    await session.commit()
    assert len(await repo.list_friend_characters(session, tenant_id=tenant_id)) == 1
    assert len(await repo.list_friend_characters(session, tenant_id=other_tenant_id)) == 1


async def test_delete_friend(session, tenant_id):
    f = await repo.add_character(session, tenant_id=tenant_id, role="friend", name="Vol'jin", server="Sen'jin", region="US")
    await session.commit()
    assert await repo.delete_character(session, f.id, tenant_id=tenant_id, role="friend") is True
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
    assert empty["own"] == [] and empty["own_limit"] == 10
    assert empty["friends"] == [] and empty["guild"] is None

    # Add two own characters.
    r = await client.post(
        "/api/profile/self", json={"name": "Thrall", "server": "Stormrage", "region": "US"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "self"
    alt = await client.post(
        "/api/profile/self", json={"name": "Rehgar", "server": "Stormrage", "region": "US"}
    )
    assert alt.status_code == 201, alt.text

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
    assert [c["name"] for c in prof["own"]] == ["Thrall", "Rehgar"]
    assert len(prof["friends"]) == 1
    assert prof["guild"]["name"] == "Horde"


async def test_own_character_endpoints(as_user, monkeypatch):
    monkeypatch.setattr("backend.app.api.profile.schedule_character_guide", lambda *_: None)
    client = as_user.client
    body = {"name": "Thrall", "server": "Stormrage", "region": "US"}

    a = (await client.post("/api/profile/self", json=body)).json()
    b = (await client.post("/api/profile/self", json={**body, "name": "Rehgar"})).json()

    # Role change touches only that character (FR-002).
    r = await client.patch(f"/api/profile/self/{b['id']}", json={"raid_role": "healer"})
    assert r.status_code == 200 and r.json()["raid_role"] == "healer"
    prof = (await client.get("/api/profile")).json()
    roles = {c["name"]: c["raid_role"] for c in prof["own"]}
    assert roles == {"Thrall": None, "Rehgar": "healer"}

    # Conflicts map to distinct 409 codes.
    dup = await client.post("/api/profile/self", json={**body, "name": "THRALL"})
    assert (dup.status_code, dup.json()["detail"]) == (409, "duplicate_character")
    f = (await client.post("/api/profile/friends", json={**body, "name": "Aggra"})).json()
    clash = await client.post("/api/profile/self", json={**body, "name": "Aggra"})
    assert (clash.status_code, clash.json()["detail"]) == (409, "already_friend")
    clash = await client.post("/api/profile/friends", json=body)
    assert (clash.status_code, clash.json()["detail"]) == (409, "already_own")

    # Own and friend routes don't reach each other's rows.
    assert (await client.patch(f"/api/profile/self/{f['id']}", json={"raid_role": "dps"})).status_code == 404
    assert (await client.delete(f"/api/profile/self/{f['id']}")).status_code == 404
    assert (await client.delete(f"/api/profile/friends/{a['id']}")).status_code == 404

    # Remove one; removing the last is allowed too.
    assert (await client.delete(f"/api/profile/self/{a['id']}")).status_code == 204
    assert (await client.delete(f"/api/profile/self/{b['id']}")).status_code == 204
    assert (await client.get("/api/profile")).json()["own"] == []

    # The single-self PUT is gone.
    assert (await client.put("/api/profile/self", json=body)).status_code == 405


async def test_own_character_limit_endpoint(as_user, monkeypatch):
    monkeypatch.setattr("backend.app.api.profile.schedule_character_guide", lambda *_: None)
    client = as_user.client
    for i in range(10):
        r = await client.post("/api/profile/self", json={"name": f"Alt{i}", "server": "S", "region": "US"})
        assert r.status_code == 201, r.text
    r = await client.post("/api/profile/self", json={"name": "Eleven", "server": "S", "region": "US"})
    assert (r.status_code, r.json()["detail"]) == (409, "character_limit")
