"""Profile CRUD + invariants (feature 005 / US1): single self, one main guild."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from backend.app.db import repository as repo
from backend.app.db.session import get_session
from backend.app.main import app


# --- Repository-level invariants ----------------------------------------------


async def test_upsert_self_keeps_single_row(session):
    await repo.upsert_self(session, name="Thrall", server="Stormrage", region="US")
    await repo.upsert_self(session, name="Jaina", server="Proudmoore", region="US")
    await session.commit()

    self_char, friends, guild = await repo.get_profile(session)
    assert self_char is not None
    assert self_char.name == "Jaina"  # replaced, not duplicated
    assert self_char.guide_status == "pending"
    assert friends == []
    assert guild is None


async def test_set_guild_replaces_single_row(session):
    await repo.set_guild(session, name="Old", server="Stormrage", region="US")
    await repo.set_guild(session, name="New", server="Area 52", region="US")
    await session.commit()

    guild = await repo.get_guild_profile(session)
    assert guild is not None
    assert guild.name == "New"  # one-main-guild limit (FR-003)
    # Exactly one row remains.
    _, _, g = await repo.get_profile(session)
    assert g is not None and g.name == "New"


async def test_add_friend_rejects_identical_duplicate(session):
    await repo.add_friend(session, name="Muradin", server="Ironforge", region="EU")
    await session.commit()
    with pytest.raises(IntegrityError):
        await repo.add_friend(session, name="Muradin", server="Ironforge", region="EU")
        await session.flush()


async def test_delete_friend(session):
    f = await repo.add_friend(session, name="Vol'jin", server="Sen'jin", region="US")
    await session.commit()
    assert await repo.delete_friend(session, f.id) is True
    await session.commit()
    _, friends, _ = await repo.get_profile(session)
    assert friends == []


# --- Endpoint smoke (scheduling stubbed so no real background guide runs) ------


def _client_with(session_factory) -> AsyncClient:
    async def override_get_session():
        async with session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_session] = override_get_session
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_profile_endpoints_roundtrip(session_factory, monkeypatch):
    # Don't spawn real guide tasks (they'd hit WCL / the model).
    monkeypatch.setattr("backend.app.api.profile.schedule_character_guide", lambda *_: None)
    monkeypatch.setattr("backend.app.api.profile.schedule_guild_summary", lambda *_: None)

    client = _client_with(session_factory)
    try:
        # Empty profile.
        empty = (await client.get("/api/profile")).json()
        assert empty["self"] is None and empty["friends"] == [] and empty["guild"] is None

        # Set self (serialized under the "self" key).
        r = await client.put(
            "/api/profile/self", json={"name": "Thrall", "server": "Stormrage", "region": "US"}
        )
        assert r.status_code == 200
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

        # Guild.
        g = await client.put(
            "/api/profile/guild", json={"name": "Horde", "server": "Orgrimmar", "region": "US"}
        )
        assert g.status_code == 200

        prof = (await client.get("/api/profile")).json()
        assert prof["self"]["name"] == "Thrall"
        assert len(prof["friends"]) == 1
        assert prof["guild"]["name"] == "Horde"
    finally:
        app.dependency_overrides.clear()
        await client.aclose()
