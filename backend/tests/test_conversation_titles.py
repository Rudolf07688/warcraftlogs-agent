"""Generated conversation titles (feature 019 / sc-155).

Covers the title-source rules: chats named at creation are marked explicit by every
naming caller (FR-018), the one-time generation claim (FR-016), and title cleaning (FR-013).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from backend.app.db import repository as repo
from backend.app.services.conversation_titles import TITLE_MAX_LEN, clean_title

_MODEL = "gemini-3.6-flash"
_OLD = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def _title_source(session_factory, conv_id, tenant_id) -> str:
    async with session_factory() as s:
        conv = await repo.get_conversation_row(s, uuid.UUID(str(conv_id)), tenant_id=tenant_id)
        return conv.title_source


# --- Explicit at creation, per naming caller (FR-018) ----------------------------


async def test_post_with_title_is_explicit_and_without_is_auto(as_user, session_factory):
    model = (await as_user.client.get("/api/models")).json()["default"]
    named = await as_user.client.post("/api/conversations", json={"model": model, "title": "Prog notes"})
    unnamed = await as_user.client.post("/api/conversations", json={"model": model})
    assert named.status_code == unnamed.status_code == 201

    assert await _title_source(session_factory, named.json()["id"], as_user.tenant_id) == "explicit"
    assert await _title_source(session_factory, unnamed.json()["id"], as_user.tenant_id) == "auto"


async def test_tracked_raid_investigation_is_explicit(as_user, session_factory):
    async with session_factory() as s:
        await repo.upsert_tracked_raid(
            s, tenant_id=as_user.tenant_id, report_code="RRRR", label="R raid"
        )
        await s.commit()

    resp = await as_user.client.post("/api/raids/RRRR/investigate", json={})
    assert resp.status_code == 201, resp.text
    conv_id = resp.json()["conversation_id"]
    assert await _title_source(session_factory, conv_id, as_user.tenant_id) == "explicit"


async def test_recent_raid_kickoff_is_explicit(as_user, session_factory):
    from backend.app.services.recent_raid_types import ListedReport

    started = datetime(2026, 10, 15, 19, 0, tzinfo=timezone.utc)
    async with session_factory() as s:
        char = await repo.add_character(
            s, tenant_id=as_user.tenant_id, role="self", name="Alpha", server="Realm", region="EU"
        )
        await repo.upsert_listed_reports(
            s,
            tenant_id=as_user.tenant_id,
            reports=[
                ListedReport(
                    code="RECENT1",
                    title="Title",
                    zone_id=53,
                    zone_name="The Venomous Abyss",
                    guild_name="Guild",
                    started_at=started,
                    ended_at=started,
                    character_ids=frozenset({char.id}),
                    is_raid=True,
                )
            ],
        )
        await s.commit()

    # The welcome page's recent-raid card starts its chat through the same endpoint.
    resp = await as_user.client.post("/api/raids/RECENT1/investigate", json={})
    assert resp.status_code == 201, resp.text
    conv_id = resp.json()["conversation_id"]
    assert await _title_source(session_factory, conv_id, as_user.tenant_id) == "explicit"


async def test_chat_started_over_the_socket_is_auto(session, tenant_id):
    # The WebSocket path creates the conversation without a title.
    conv = await repo.create_conversation(session, model=_MODEL, tenant_id=tenant_id)
    assert conv.title_source == "auto" and conv.title == "New chat"


# --- The one-time claim (FR-016) -------------------------------------------------


async def _conversation(session, tenant_id, *, title=None, source=None):
    conv = await repo.create_conversation(session, model=_MODEL, title=title, tenant_id=tenant_id)
    if source:
        conv.title_source = source
    conv.updated_at = _OLD
    await session.commit()
    return conv


async def test_claim_succeeds_once(session, tenant_id):
    conv = await _conversation(session, tenant_id)
    assert await repo.claim_title_generation(session, conv.id, tenant_id=tenant_id) is True
    assert await repo.claim_title_generation(session, conv.id, tenant_id=tenant_id) is False


@pytest.mark.parametrize("source", ["explicit", "legacy"])
async def test_named_and_legacy_chats_are_never_claimed(session, tenant_id, source):
    conv = await _conversation(session, tenant_id, title="Named", source=source)
    assert await repo.claim_title_generation(session, conv.id, tenant_id=tenant_id) is False


async def test_claim_is_tenant_scoped(session, tenant_id, other_tenant_id):
    conv = await _conversation(session, tenant_id)
    assert await repo.claim_title_generation(session, conv.id, tenant_id=other_tenant_id) is False
    assert await repo.claim_title_generation(session, conv.id, tenant_id=tenant_id) is True


async def test_generated_title_needs_a_claim_and_keeps_updated_at(session, tenant_id):
    conv = await _conversation(session, tenant_id)
    assert await repo.set_generated_title(session, conv.id, "Too early", tenant_id=tenant_id) is False

    await repo.claim_title_generation(session, conv.id, tenant_id=tenant_id)
    assert await repo.set_generated_title(session, conv.id, "Wipe review", tenant_id=tenant_id) is True
    await session.refresh(conv)
    assert conv.title == "Wipe review" and conv.title_source == "generated"
    assert conv.updated_at.replace(tzinfo=timezone.utc) == _OLD


async def test_generated_title_never_overwrites_an_explicit_name(session, tenant_id):
    conv = await _conversation(session, tenant_id, title="Raid: Undermine")
    assert await repo.set_generated_title(session, conv.id, "Other", tenant_id=tenant_id) is False


async def test_generated_title_on_a_deleted_chat_is_a_no_op(session, tenant_id):
    conv = await _conversation(session, tenant_id)
    await repo.claim_title_generation(session, conv.id, tenant_id=tenant_id)
    await repo.delete_conversation(session, conv.id, tenant_id=tenant_id)
    assert await repo.set_generated_title(session, conv.id, "Gone", tenant_id=tenant_id) is False


# --- Title cleaning (FR-013) -------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('"Wipes on Gallywix"', "Wipes on Gallywix"),
        ("“Curly quotes”", "Curly quotes"),
        ("`Parse` review", "Parse review"),
        ("**Title:** Raid recap", "Raid recap"),
        ("Title: Healer cooldowns.", "Healer cooldowns"),
        ("# Heading\nsecond line", "Heading"),
        ("\n\n  Mythic   prog \t notes  ", "Mythic prog notes"),
        ("...", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_clean_title(raw, expected):
    assert clean_title(raw) == expected


def test_clean_title_cuts_at_a_word_boundary():
    title = clean_title("Why our raid kept wiping on the last boss " * 3)
    assert len(title) <= TITLE_MAX_LEN
    assert not title.endswith(" ")
    assert ("Why our raid kept wiping on the last boss " * 3).startswith(title + " ")


def test_clean_title_hard_cuts_a_single_long_word():
    assert clean_title("x" * 80) == "x" * TITLE_MAX_LEN
