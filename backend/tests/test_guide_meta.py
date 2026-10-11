"""Guide provenance: freshness, current patch, meta-block parsing, registry, preamble labels
(feature 009, US5)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.app.db.models import UserCharacter
from backend.app.services.guide import parse_guide_meta, registry_meta
from backend.app.services.profile_context import build_preamble, guide_heading_label
from backend.tests.wcl_fakes import install
from wcl_agent.guide_meta import (
    GuideCooldown,
    GuideMeta,
    clear_guide_meta,
    get_guide_meta,
    set_guide_meta,
)
from wcl_agent.patch import current_patch, current_patch_from_zones, guide_freshness

# --- (a) freshness --------------------------------------------------------------------


@pytest.mark.parametrize(
    "guide,current,expected",
    [
        ("12.1", "12.1", "current"),
        ("12.1.5", "12.1", "current"),
        ("12.2", "12.1", "current"),
        ("12.0", "12.1", "possibly_stale"),
        ("11.2", "12.1", "possibly_stale"),
        (None, "12.1", "unknown"),
        ("12.1", None, "unknown"),
        ("Season 2", "12.1", "unknown"),
        ("", "12.1", "unknown"),
    ],
)
def test_guide_freshness(guide, current, expected):
    assert guide_freshness(guide, current) == expected


# --- (b) current patch ------------------------------------------------------------------

MENU_PAYLOAD = {"data": {"worldData": {"zones": [
    {"id": 60, "name": "Mythic+ Season 2", "frozen": False,
     "difficulties": [{"id": 10, "name": "Mythic+"}],
     "partitions": [{"id": 1, "name": "Season 2", "default": True}], "encounters": []},
    {"id": 40, "name": "Old Raid", "frozen": True,
     "difficulties": [{"id": 3, "name": "Normal"}, {"id": 4, "name": "Heroic"}, {"id": 5, "name": "Mythic"}],
     "partitions": [{"id": 1, "name": "11.2", "default": True}], "encounters": []},
    {"id": 53, "name": "The Venomous Abyss", "frozen": False,
     "difficulties": [{"id": 3, "name": "Normal"}, {"id": 4, "name": "Heroic"}, {"id": 5, "name": "Mythic"}],
     "partitions": [{"id": 1, "name": "12.0", "default": False}, {"id": 2, "name": "12.1", "default": True}],
     "encounters": []},
]}}}


def test_current_patch_picks_newest_heroic_zone_default_partition(monkeypatch):
    fake = install(monkeypatch, lambda q, v: MENU_PAYLOAD)
    assert current_patch() == "12.1"
    assert fake.count("MenuDiscovery") == 1


def test_current_patch_from_zones_edge_cases():
    assert current_patch_from_zones([]) is None
    assert current_patch_from_zones(MENU_PAYLOAD["data"]["worldData"]["zones"][:1]) is None  # M+ only


def test_current_patch_swallows_errors(monkeypatch):
    def boom(q, v):
        raise RuntimeError("no WCL")

    install(monkeypatch, boom)
    assert current_patch() is None


# --- (c) parse_guide_meta ---------------------------------------------------------------

GUIDE = """# Fire Mage (patch 12.1)

## Major cooldowns
- Combustion — 120 s

```guide-meta
{"patch": " 12.1 ", "major_cooldowns": [
  {"name": "Combustion", "spell_id": 190319, "cooldown_s": 120, "charges": 1, "talent_modified": false},
  {"name": "Shifting Power", "spell_id": null, "cooldown_s": 60}
]}
```
"""


def test_parse_guide_meta_extracts_and_strips_last_block():
    text, meta = parse_guide_meta(GUIDE)
    assert meta is not None
    assert meta.patch == "12.1"
    assert [c.name for c in meta.major_cooldowns] == ["Combustion", "Shifting Power"]
    assert meta.major_cooldowns[1].charges == 1 and meta.major_cooldowns[1].spell_id is None
    assert "guide-meta" not in text
    assert text.endswith("- Combustion — 120 s")


def test_parse_guide_meta_missing_or_invalid_keeps_text():
    plain = "# Guide with no block"
    assert parse_guide_meta(plain) == (plain, None)
    bad_json = "# G\n\n```guide-meta\n{not json}\n```"
    assert parse_guide_meta(bad_json) == (bad_json, None)
    bad_schema = '# G\n\n```guide-meta\n{"patch": "12.1", "major_cooldowns": [{"name": "X", "cooldown_s": 5000}]}\n```'
    assert parse_guide_meta(bad_schema) == (bad_schema, None)
    too_many = '# G\n\n```guide-meta\n{"major_cooldowns": [' + ",".join(
        f'{{"name": "A{i}", "cooldown_s": 10}}' for i in range(16)
    ) + "]}\n```"
    assert parse_guide_meta(too_many)[1] is None
    charges = '```guide-meta\n{"major_cooldowns": [{"name": "A", "cooldown_s": 10, "charges": 9}]}\n```'
    assert parse_guide_meta(charges)[1] is None


def test_parse_guide_meta_uses_last_block_when_several():
    two = GUIDE + '\n```guide-meta\n{"patch": "12.2", "major_cooldowns": []}\n```'
    text, meta = parse_guide_meta(two)
    assert meta.patch == "12.2"
    assert text.count("```guide-meta") == 1  # the earlier block is left in the prose


# --- (d) registry -------------------------------------------------------------------------


def test_registry_round_trip():
    clear_guide_meta()
    meta = GuideMeta("Mage", "Fire", "12.1", datetime.now(UTC), (GuideCooldown("Combustion", 190319, 120.0),))
    set_guide_meta(meta)
    assert get_guide_meta("Mage", "Fire") is meta
    assert get_guide_meta("mage", "fire") is meta  # case-insensitive key
    assert get_guide_meta("Mage", "Frost") is None
    clear_guide_meta()
    assert get_guide_meta("Mage", "Fire") is None


def test_registry_meta_from_stored_json_skips_bad_rows():
    meta = registry_meta(
        "Mage", "Fire", "12.1", None,
        [{"name": "Combustion", "spell_id": 190319, "cooldown_s": 120, "charges": 1},
         {"name": "", "cooldown_s": 60}, {"name": "X"}, "junk",
         {"name": "Shifting Power", "cooldown_s": "60", "talent_modified": True}],
    )
    assert [c.name for c in meta.cooldowns] == ["Combustion", "Shifting Power"]
    assert meta.cooldowns[1].cooldown_s == 60.0 and meta.cooldowns[1].talent_modified is True
    assert registry_meta("Mage", "Fire", None, None, None).cooldowns == ()


# --- (e) preamble labels -------------------------------------------------------------------


def test_guide_heading_label():
    assert guide_heading_label("12.1", "current") == "guide for patch 12.1 · current"
    assert guide_heading_label("11.2", "possibly_stale") == "guide for patch 11.2 · may be out of date"
    assert guide_heading_label(None, "unknown") == "guide patch unknown · may be out of date"


def test_preamble_guide_heading_gets_label_only_when_given():
    self_char = UserCharacter(
        role="self", name="Thrall", server="Stormrage", region="US",
        class_name="Shaman", active_spec="Enhancement",
    )
    guides = {("Shaman", "Enhancement"): "Stormstrike on cooldown."}
    plain = build_preamble(self_char, [], None, spec_guides=guides)
    assert "## Thrall — Enhancement\n" in plain
    labelled = build_preamble(
        self_char, [], None, spec_guides=guides,
        guide_labels={("Shaman", "Enhancement"): "guide for patch 12.1 · current"},
    )
    assert "## Thrall — Enhancement (guide for patch 12.1 · current)" in labelled
    assert build_preamble(self_char, [], None, spec_guides=guides, guide_labels={}) == plain
