"""Onboarding to profile setup (074, sc-166/167): the skippable prompt's state and the main
class/spec/content selector, through the real auth and tenant path."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from backend.app.db.models import ProfileSettings

URL = "/api/profile/settings"
SKIP = "/api/profile/onboarding/skip"
VALID = {"main_class": "Paladin", "main_spec": "Holy", "main_content": "both"}


async def _row(patched_db, tenant_id) -> tuple | None:
    async with patched_db() as db:
        row = (
            await db.execute(select(ProfileSettings).where(ProfileSettings.tenant_id == tenant_id))
        ).scalar_one_or_none()
        if row is None:
            return None
        return (row.main_class, row.main_spec, row.main_content, row.onboarding_dismissed_at)


async def test_a_new_workspace_is_pending_until_it_skips_and_then_never_again(as_user, patched_db):
    client = as_user.client
    fresh = (await client.get(URL)).json()
    assert fresh == {"main_class": None, "main_spec": None, "main_content": None, "onboarding_pending": True}

    first = await client.post(SKIP)
    assert first.status_code == 200 and first.json()["onboarding_pending"] is False
    skipped_at = (await _row(patched_db, as_user.tenant_id))[3]
    assert skipped_at is not None

    # Every later load reads the stored skip; a second skip keeps the first time.
    assert (await client.post(SKIP)).json()["onboarding_pending"] is False
    assert (await client.get(URL)).json()["onboarding_pending"] is False
    assert (await _row(patched_db, as_user.tenant_id))[3] == skipped_at


async def test_an_own_character_ends_onboarding_and_a_friend_does_not(as_user, monkeypatch):
    monkeypatch.setattr("backend.app.api.profile.schedule_character_guide", lambda *_: None)
    client = as_user.client
    body = {"server": "Stormrage", "region": "US"}
    assert (await client.post("/api/profile/friends", json={"name": "Aggra", **body})).status_code == 201
    assert (await client.get(URL)).json()["onboarding_pending"] is True
    assert (await client.post("/api/profile/self", json={"name": "Thrall", **body})).status_code == 201
    assert (await client.get(URL)).json()["onboarding_pending"] is False


async def test_the_main_selection_is_saved_shown_again_and_cleared(as_user):
    client = as_user.client
    saved = await client.put(URL, json=VALID)
    assert saved.status_code == 200, saved.text
    assert (await client.get(URL)).json() == {**VALID, "onboarding_pending": True}

    # A class alone is fine; nulls clear.
    assert (await client.put(URL, json={**VALID, "main_spec": None})).json()["main_spec"] is None
    cleared = (await client.put(URL, json={"main_class": None, "main_spec": None, "main_content": None})).json()
    assert cleared == {"main_class": None, "main_spec": None, "main_content": None, "onboarding_pending": True}


@pytest.mark.parametrize(
    "body",
    [
        {**VALID, "main_class": "Paladin "},  # trailing space
        {**VALID, "main_class": "paladin"},  # wrong case
        {**VALID, "main_spec": "holy"},
        {**VALID, "main_spec": "Fury"},  # a spec of another class
        {**VALID, "main_class": "P" * 10_000},
        {**VALID, "main_spec": "H" * 10_000},
        {**VALID, "main_class": None},  # a spec needs its class
        {**VALID, "main_content": "mythic"},
        {**VALID, "main_content": "Raid"},
        {"main_class": "Paladin", "main_spec": "Holy"},  # every key is required
        {**VALID, "tenant_id": "22222222-2222-2222-2222-222222222222"},  # never from the body
    ],
)
async def test_values_outside_the_roster_are_rejected_and_nothing_is_stored(as_user, patched_db, body):
    client = as_user.client
    await client.put(URL, json={"main_class": "Warrior", "main_spec": "Arms", "main_content": "raid"})
    before = await _row(patched_db, as_user.tenant_id)

    r = await client.put(URL, json=body)
    assert r.status_code == 422, r.text
    assert await _row(patched_db, as_user.tenant_id) == before


async def test_writes_change_only_the_session_workspace(as_user, make_authed_client, patched_db):
    other = await make_authed_client("other@example.com")
    try:
        await other.client.put(URL, json={"main_class": "Mage", "main_spec": "Fire", "main_content": "mplus"})
        other_before = await _row(patched_db, other.tenant_id)

        await as_user.client.put(URL, json=VALID)
        await as_user.client.post(SKIP)

        assert await _row(patched_db, other.tenant_id) == other_before
        assert (await other.client.get(URL)).json() == {
            "main_class": "Mage", "main_spec": "Fire", "main_content": "mplus", "onboarding_pending": True,
        }
    finally:
        await other.client.aclose()


async def test_unsafe_settings_calls_need_the_csrf_token(as_user):
    headers = {"x-csrf-token": "wrong"}
    assert (await as_user.client.put(URL, json=VALID, headers=headers)).status_code == 403
    assert (await as_user.client.post(SKIP, headers=headers)).status_code == 403
