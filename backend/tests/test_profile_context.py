"""The KNOWN PLAYER CONTEXT preamble (feature 005 / US1; feature 007 captured metadata + roles;
feature 015 whole coaching briefs per content type)."""

from __future__ import annotations

from backend.app.db.models import (
    GuildProfile,
    KnownEncounter,
    KnownPlayer,
    TrackedRaid,
    UserCharacter,
)
from backend.app.config import settings
from backend.app.services.profile_context import build_preamble
from wcl_agent.guides.guide_meta import BriefRecord


def _brief(cls: str, spec: str, text: str, content_type: str = "raid") -> BriefRecord:
    return BriefRecord(cls, spec, content_type, text, (), "12.1", None, None, "current", True)


def test_empty_profile_yields_empty_preamble():
    # No profile → no preamble, so behavior is unchanged (FR-006).
    assert build_preamble([], [], None) == ""


def test_preamble_includes_identities_and_scoping_rule():
    self_char = UserCharacter(
        role="self", name="Thrall", server="Stormrage", region="US",
        class_name="Shaman", active_spec="Enhancement",
    )
    friend = UserCharacter(
        role="friend", name="Aggra", server="Stormrage", region="US",
    )
    guild = GuildProfile(name="Horde", server="Orgrimmar", region="US", summary_status="none")

    text = build_preamble([self_char], [friend], guild)
    assert "KNOWN PLAYER CONTEXT" in text
    assert "population-level" in text  # the scoping rule is present
    assert "Thrall-Stormrage (US)" in text
    assert "Shaman — Enhancement" in text
    assert "Aggra-Stormrage (US)" in text
    assert "Horde-Orgrimmar (US)" in text


def test_whole_brief_inlined_with_index():
    self_char = UserCharacter(
        role="self", name="Thrall", server="Stormrage", region="US",
        class_name="Shaman", active_spec="Enhancement",
    )
    text_in = "COACHING BRIEF — Enhancement Shaman · Raid\nPRIORITY (in order)\n1. [G,H] Stormstrike."
    text = build_preamble(
        [self_char], [], None,
        briefs={("Shaman", "Enhancement"): _brief("Shaman", "Enhancement", text_in)},
        available={("Shaman", "Enhancement"): {"raid": True, "mplus": True}},
    )
    assert "- Coaching briefs — content type: Raid:" in text
    assert "  COACHING BRIEF — Enhancement Shaman · Raid\n  PRIORITY (in order)\n  1. [G,H] Stormstrike." in text
    assert (
        "  - Enhancement Shaman (Thrall) — Raid: inline · Mythic+: available (get_coaching_brief)"
        in text
    )


def test_briefs_fit_whole_or_are_omitted_whole(monkeypatch):
    monkeypatch.setattr(settings, "wcl_guide_preamble_briefs_max_chars", 1000)
    own = [_own("Alpha", "Mage", "Frost"), _own("Beta", "Priest", "Holy")]
    friend = UserCharacter(role="friend", name="Thrall", server="Draenor", region="EU",
                           class_name="Shaman", active_spec="Enhancement")
    briefs = {
        ("Mage", "Frost"): _brief("Mage", "Frost", "F" * 600),
        ("Priest", "Holy"): _brief("Priest", "Holy", "H" * 600),  # does not fit after Frost
        ("Shaman", "Enhancement"): _brief("Shaman", "Enhancement", "E" * 300),  # still fits
    }
    text = build_preamble(own, [friend], None, briefs=briefs)
    assert "F" * 600 in text and "E" * 300 in text
    assert "H" not in text.replace("Holy", "").replace("Healer", "").replace("Mythic+", "")
    assert "Holy Priest (Beta) — Raid: omitted (budget) — use get_coaching_brief" in text
    assert "Frost Mage (Alpha) — Raid: inline" in text  # own characters first
    assert "Enhancement Shaman (Thrall) — Raid: inline" in text


def test_assumed_content_type_note_and_mplus_label():
    char = _own("Alpha", "Mage", "Fire")
    assumed = build_preamble([char], [], None, content_type_note="assumed Raid — the message did not say")
    assert "- Coaching briefs — content type: Raid (assumed Raid — the message did not say):" in assumed
    mplus = build_preamble(
        [char], [], None, content_type="mplus",
        available={("Mage", "Fire"): {"raid": True, "mplus": False}},
    )
    assert "Fire Mage (Alpha) — Mythic+: none (no verified guidance) · Raid: available (get_coaching_brief)" in mplus


def test_no_brief_means_none_in_the_index():
    # A resolved character whose spec has no published brief ⇒ no brief text, and the
    # index says there is no verified guidance (never another spec's or type's brief).
    self_char = UserCharacter(
        role="self", name="Thrall", server="Stormrage", region="US",
        class_name="Shaman", active_spec="Enhancement",
    )
    text = build_preamble(
        [self_char], [], None, briefs={("Mage", "Fire"): _brief("Mage", "Fire", "irrelevant")}
    )
    assert "irrelevant" not in text
    assert "Enhancement Shaman (Thrall) — Raid: none (no verified guidance)" in text


def test_unresolved_spec_character_gets_no_brief_block():
    # No class/spec ⇒ no brief block at all, even if the map is non-empty.
    char = UserCharacter(role="self", name="Thrall", server="Stormrage", region="US")
    text = build_preamble([char], [], None, briefs={("Shaman", "Enhancement"): _brief("Shaman", "Enhancement", "x")})
    assert "Coaching briefs" not in text and "Brief index" not in text


# --- feature 007: captured-metadata block (US1) -------------------------------


def test_empty_captured_metadata_is_byte_identical():
    # With a profile but no captured metadata and an empty guide map, output must equal the
    # pre-feature output (the new kwargs default to empty), so there is no regression
    # (FR-011, SC-003; feature 008 FR-016 byte-equality).
    self_char = UserCharacter(
        role="self", name="Thrall", server="Stormrage", region="US",
        class_name="Shaman", active_spec="Enhancement",
    )
    baseline = build_preamble([self_char], [], None)
    with_empty = build_preamble(
        [self_char], [], None,
        known_raids=[], known_players=[], known_encounters=[], known_guilds=[],
        briefs={}, available={},
    )
    assert with_empty == baseline
    assert "RECENTLY SEEN" not in with_empty
    # Fully empty everything ⇒ "" exactly as today (SC-008).
    assert build_preamble([], [], None, known_raids=[], known_players=[]) == ""


def test_captured_metadata_block_appended_and_bounded():
    raids = [TrackedRaid(report_code=f"R{i}", label=f"Raid {i}") for i in range(10)]
    players = [
        KnownPlayer(name=f"P{i}", server="Stormrage", region="US", class_name="Mage", spec="Fire")
        for i in range(15)
    ]
    encounters = [KnownEncounter(encounter_id=i, encounter_name=f"Boss {i}", zone_name="Zone") for i in range(10)]
    guilds = ["Alpha", "Beta"]

    text = build_preamble(
        [], [], None,
        known_raids=raids, known_players=players,
        known_encounters=encounters, known_guilds=guilds,
    )
    assert "RECENTLY SEEN (this account)" in text
    assert "- Raids:" in text and "Raid 0" in text
    assert "- Players:" in text and "P0-Stormrage (US) — Mage — Fire" in text
    assert "- Encounters:" in text and "Boss 0 (Zone)" in text
    assert "- Guilds:" in text and "Alpha" in text
    # The whole captured block stays within its fixed char budget (SC-003).
    recent = text[text.index("RECENTLY SEEN"):]
    assert len(recent) <= 1501  # _RECENT_CHARS (+ a trailing ellipsis char)


def test_discovered_player_in_profile_is_not_double_listed():
    self_char = UserCharacter(
        role="self", name="Thrall", server="Stormrage", region="US",
    )
    known = [
        KnownPlayer(name="Thrall", server="Stormrage", region="US"),  # same as profile
        KnownPlayer(name="Sylvanas", server="Stormrage", region="US"),
    ]
    text = build_preamble([self_char], [], None, known_players=known)
    assert "Sylvanas-Stormrage (US)" in text
    # Thrall appears once (in the profile line), not again under Players.
    assert "- Players: Sylvanas-Stormrage (US)" in text
    assert text.count("Thrall-Stormrage (US)") == 1


# --- feature 007: effective raid role in _ident (US4) -------------------------


def test_effective_role_appended_from_spec_and_override():
    inferred = UserCharacter(
        role="self", name="Tankadin", server="S", region="US",
        class_name="Paladin", active_spec="Protection",
    )
    overridden = UserCharacter(
        role="friend", name="Flex", server="S", region="US",
        class_name="Druid", active_spec="Balance", raid_role="healer",
    )
    text = build_preamble([inferred], [overridden], None)
    assert "Tankadin-S (US) — Paladin — Protection — Tank" in text  # inferred from spec
    assert "Flex-S (US) — Druid — Balance — Healer" in text  # override beats inferred (dps)


def test_unset_role_leaves_line_unchanged():
    # No raid_role and no resolvable spec ⇒ no role suffix (byte-identical, FR-030).
    char = UserCharacter(
        role="self", name="Nobody", server="S", region="US",
    )
    text = build_preamble([char], [], None)
    assert "Nobody-S (US)" in text
    assert "Nobody-S (US) —" not in text


# --- feature 012: several own characters --------------------------------------


def _own(name: str, cls: str | None = None, spec: str | None = None) -> UserCharacter:
    return UserCharacter(role="self", name=name, server="Draenor", region="EU", class_name=cls, active_spec=spec)


def test_single_own_character_line_is_unchanged():
    # One own character ⇒ the exact pre-feature line (FR-011).
    text = build_preamble([_own("Alpha", "Mage", "Frost")], [], None)
    assert "\n- You (self): Alpha-Draenor (EU) — Mage — Frost — DPS\n" in text + "\n"
    assert "can mean any" not in text


def test_several_own_characters_listed_on_one_line():
    alpha = _own("Alpha", "Mage", "Frost")
    beta = _own("Beta", "Priest", "Holy")
    text = build_preamble([alpha, beta], [], None)
    assert (
        '- You (self) — the user plays all of these characters; "I/me/my" can mean any of '
        "them: Alpha-Draenor (EU) — Mage — Frost — DPS; Beta-Draenor (EU) — Priest — Holy — Healer"
    ) in text
    assert "Friends:" not in text


def test_shared_spec_brief_injected_once_under_both_names():
    briefs = {("Mage", "Frost"): _brief("Mage", "Frost", "Frostbolt into Flurry.")}
    text = build_preamble([_own("Alpha", "Mage", "Frost"), _own("Gamma", "Mage", "Frost")], [], None, briefs=briefs)
    assert "Frost Mage (Alpha, Gamma) — Raid: inline" in text
    assert text.count("Frostbolt into Flurry.") == 1


def test_distinct_specs_each_get_their_brief():
    friend = UserCharacter(role="friend", name="Thrall", server="Draenor", region="EU", class_name="Shaman", active_spec="Enhancement")
    briefs = {("Mage", "Frost"): _brief("Mage", "Frost", "frost brief"),
              ("Shaman", "Enhancement"): _brief("Shaman", "Enhancement", "enh brief")}
    text = build_preamble([_own("Alpha", "Mage", "Frost")], [friend], None, briefs=briefs)
    assert text.index("frost brief") < text.index("enh brief")
    assert "Frost Mage (Alpha) — Raid: inline" in text and "Enhancement Shaman (Thrall) — Raid: inline" in text


def test_every_own_character_excluded_from_recently_seen():
    known = [
        KnownPlayer(name="Alpha", server="Draenor", region="EU"),
        KnownPlayer(name="Beta", server="Draenor", region="EU"),
        KnownPlayer(name="Stranger", server="Draenor", region="EU"),
    ]
    text = build_preamble([_own("Alpha"), _own("Beta")], [], None, known_players=known)
    assert "- Players: Stranger-Draenor (EU)" in text
    assert text.count("Alpha-Draenor (EU)") == 1 and text.count("Beta-Draenor (EU)") == 1
