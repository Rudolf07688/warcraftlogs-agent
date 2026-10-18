"""Turn content-type classification (feature 015, US2, research R8)."""

from __future__ import annotations

import pytest

from backend.app.services.content_type import classify_content_type

DUNGEONS = ["Altar of Fangs", "Den of Nalorakk", "Murder Row"]
BOSSES = ["Nek'zali the Soulcoiler", "Sszorak", "The Twin Fangs"]
MPLUS_ZONE = "Mythic+ Season 2"


def classify(text, recent=None):
    return classify_content_type(text, recent, MPLUS_ZONE, DUNGEONS, BOSSES)


@pytest.mark.parametrize(
    "text",
    [
        "How did my M+ run go?",
        "check my mythic+ pulls",
        "my last mythic plus key",
        "why did we deplete the keystone",
        "how did my 15 key go?",
        "check key level 12 please",
        "I timed a +12 yesterday, what went wrong?",
        "review my Den of Nalorakk run",
        "which affixes hurt me most",
    ],
)
def test_mplus_keywords(text):
    assert classify(text) == "mplus"


@pytest.mark.parametrize(
    "text",
    [
        "How was my raid last night?",
        "what killed me on Sszorak",
        "our heroic prog on the second boss",
        "my mythic parses this week",
        "LFR cooldown usage",
    ],
)
def test_raid_terms_and_bosses(text):
    assert classify(text) == "raid"


def test_patch_numbers_are_not_key_levels():
    assert classify("is this guide for 12.1+ ?") == "unknown"


def test_recent_zone_fills_silence():
    assert classify("how did I do?", recent=MPLUS_ZONE) == "mplus"
    assert classify("how did I do?", recent="The Venomous Abyss") == "raid"
    assert classify("how did I do?") == "unknown"


def test_message_beats_history_and_ties_use_history():
    assert classify("my +15 last night", recent="The Venomous Abyss") == "mplus"
    assert classify("my raid vs my +12 key", recent=MPLUS_ZONE) == "mplus"
    assert classify("my raid vs my +12 key") == "unknown"
    assert classify("raid boss vs my dungeon run") == "raid"  # a strong word beats a weak one


@pytest.mark.parametrize(
    "text",
    [
        "What are the key mistakes on this boss?",
        "On heroic, what was the key reason I died?",
        "we timed the pull badly on mythic",
        "I got +10% haste from the buff, was my heroic pull ok?",
    ],
)
def test_ordinary_english_does_not_mean_mythic_plus(text):
    # QA SPEC-001 / BUG-008: "key", "timed" and "+10%" are not Mythic+ signals.
    assert classify(text) == "raid"


def test_ordinary_key_without_context_is_unknown():
    assert classify("Which stat is key for fire mage?") == "unknown"
