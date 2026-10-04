"""Raid roles: spec→role mapping, PATCH override, validation, effective role (feature 007 / US4)."""

from __future__ import annotations

import pytest

from backend.app.db import repository as repo
from wcl_agent.constants import role_for_spec

# --- role_for_spec mapping ----------------------------------------------------


@pytest.mark.parametrize(
    "spec,role",
    [
        ("Protection", "tank"),   # Paladin/Warrior
        ("Blood", "tank"),        # Death Knight
        ("Vengeance", "tank"),    # Demon Hunter
        ("Guardian", "tank"),     # Druid
        ("Brewmaster", "tank"),   # Monk
        ("Holy", "healer"),       # Paladin/Priest
        ("Restoration", "healer"),  # Druid/Shaman
        ("Preservation", "healer"),  # Evoker
        ("Mistweaver", "healer"),  # Monk
        ("Discipline", "healer"),  # Priest
        ("Fire", "dps"),
        ("Assassination", "dps"),
        ("Balance", "dps"),
    ],
)
def test_role_for_spec_known(spec, role):
    assert role_for_spec(spec) == role


def test_role_for_spec_unknown_or_unset_is_none():
    assert role_for_spec(None) is None
    assert role_for_spec("") is None
    assert role_for_spec("NotASpec") is None


# --- repository update_friend_role --------------------------------------------


async def test_update_friend_role_in_place(session, tenant_id):
    f = await repo.add_friend(session, tenant_id=tenant_id, name="Thrall", server="S", region="US")
    await session.commit()
    updated = await repo.update_friend_role(
        session, f.id, tenant_id=tenant_id, raid_role="tank"
    )
    assert updated is not None and updated.id == f.id and updated.raid_role == "tank"
    # Clear back to inferred (null).
    cleared = await repo.update_friend_role(session, f.id, tenant_id=tenant_id, raid_role=None)
    assert cleared.raid_role is None
    # Still a single friend row (in-place, FR-028).
    assert len(await repo.list_friend_characters(session, tenant_id=tenant_id)) == 1


async def test_update_friend_role_unknown_is_none(session, tenant_id, other_tenant_id):
    import uuid

    assert await repo.update_friend_role(
        session, uuid.uuid4(), tenant_id=tenant_id, raid_role="dps"
    ) is None
    # A friend of another tenant is not updatable here (404 path).
    other = await repo.add_friend(
        session, tenant_id=other_tenant_id, name="X", server="S", region="US"
    )
    await session.commit()
    assert await repo.update_friend_role(
        session, other.id, tenant_id=tenant_id, raid_role="dps"
    ) is None


# --- Endpoint behavior --------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_guide_tasks(monkeypatch):
    monkeypatch.setattr("backend.app.api.profile.schedule_character_guide", lambda *_: None)
    monkeypatch.setattr("backend.app.api.profile.schedule_guild_summary", lambda *_: None)


async def test_multiple_friends_and_roles_roundtrip(as_user):
    client = as_user.client
    # At least three friends (no cap, FR-022), with an explicit role on one.
    for name in ("Aggra", "Nazgrim"):
        r = await client.post(
            "/api/profile/friends", json={"name": name, "server": "S", "region": "US"}
        )
        assert r.status_code == 201
    r = await client.post(
        "/api/profile/friends",
        json={"name": "Saurfang", "server": "S", "region": "US", "raid_role": "tank"},
    )
    assert r.status_code == 201
    assert r.json()["raid_role"] == "tank"
    assert r.json()["effective_role"] == "tank"

    prof = (await client.get("/api/profile")).json()
    assert len(prof["friends"]) == 3


async def test_patch_friend_sets_and_clears_role(as_user):
    client = as_user.client
    created = (
        await client.post("/api/profile/friends", json={"name": "Flex", "server": "S", "region": "US"})
    ).json()
    cid = created["id"]
    assert created["raid_role"] is None

    # Set override.
    r = await client.patch(f"/api/profile/friends/{cid}", json={"raid_role": "healer"})
    assert r.status_code == 200, r.text
    assert r.json()["raid_role"] == "healer"
    assert r.json()["effective_role"] == "healer"

    # Clear override → reverts to inferred (null here, no resolved spec).
    r = await client.patch(f"/api/profile/friends/{cid}", json={"raid_role": None})
    assert r.status_code == 200
    assert r.json()["raid_role"] is None
    assert r.json()["effective_role"] is None


async def test_patch_invalid_role_is_422(as_user):
    client = as_user.client
    created = (
        await client.post("/api/profile/friends", json={"name": "Val", "server": "S", "region": "US"})
    ).json()
    r = await client.patch(f"/api/profile/friends/{created['id']}", json={"raid_role": "bruiser"})
    assert r.status_code == 422
    # Character unchanged.
    prof = (await client.get("/api/profile")).json()
    assert prof["friends"][0]["raid_role"] is None


async def test_patch_unknown_friend_is_404(as_user):
    import uuid

    r = await as_user.client.patch(
        f"/api/profile/friends/{uuid.uuid4()}", json={"raid_role": "dps"}
    )
    assert r.status_code == 404


async def test_duplicate_friend_still_409(as_user):
    client = as_user.client
    await client.post("/api/profile/friends", json={"name": "Dup", "server": "S", "region": "US"})
    dup = await client.post(
        "/api/profile/friends", json={"name": "Dup", "server": "S", "region": "US"}
    )
    assert dup.status_code == 409
    assert dup.json()["detail"] == "duplicate_friend"


async def test_self_accepts_raid_role_override(as_user):
    r = await as_user.client.put(
        "/api/profile/self",
        json={"name": "Me", "server": "S", "region": "US", "raid_role": "dps"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["raid_role"] == "dps"
    assert r.json()["effective_role"] == "dps"
