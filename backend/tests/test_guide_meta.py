"""Guide provenance: freshness, current patch, Mythic+ zone, registry, preamble labels
(feature 009, US5; feature 015). The guide-meta block parser was replaced by structured
claims in feature 015."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.tests.wcl_fakes import install
from wcl_agent.guides.guide_meta import (
    BriefRecord,
    GuideCooldown,
    clear_brief_loader,
    get_brief,
    set_brief_loader,
)
from wcl_agent.game.patch import (
    current_mplus_season,
    current_patch,
    current_patch_from_zones,
    current_raid_tier,
    guide_freshness,
    is_mplus_zone_id,
    mplus_zone,
    mplus_zone_from,
)

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


async def test_current_patch_picks_newest_heroic_zone_default_partition(monkeypatch):
    fake = install(monkeypatch, lambda q, v: MENU_PAYLOAD)
    assert await current_patch() == "12.1"
    assert fake.count("MenuDiscovery") == 1


def test_current_patch_from_zones_edge_cases():
    assert current_patch_from_zones([]) is None
    assert current_patch_from_zones(MENU_PAYLOAD["data"]["worldData"]["zones"][:1]) is None  # M+ only


# --- (b2) Mythic+ zone (feature 015, research R9) ------------------------------------------

_FROZEN_MPLUS = {"id": 45, "name": "Mythic+ Season 1", "frozen": True,
                 "difficulties": [{"id": 10, "name": "Mythic+"}], "partitions": [], "encounters": []}


def test_mplus_zone_found_by_difficulty_and_frozen_ignored():
    zones = MENU_PAYLOAD["data"]["worldData"]["zones"] + [_FROZEN_MPLUS]
    assert mplus_zone_from(zones)["id"] == 60
    assert mplus_zone_from([_FROZEN_MPLUS]) is None
    assert mplus_zone_from(MENU_PAYLOAD["data"]["worldData"]["zones"][1:]) is None  # raids only


async def test_mplus_season_raid_tier_and_zone_ids(monkeypatch):
    payload = {"data": {"worldData": {"zones": MENU_PAYLOAD["data"]["worldData"]["zones"] + [_FROZEN_MPLUS]}}}
    install(monkeypatch, lambda q, v: payload)
    assert await current_mplus_season() == "Mythic+ Season 2"
    assert (await mplus_zone())["id"] == 60
    assert await current_raid_tier() == "The Venomous Abyss"
    assert await is_mplus_zone_id(60) is True
    assert await is_mplus_zone_id(45) is True  # an older season is still Mythic+
    assert await is_mplus_zone_id(53) is False
    assert await is_mplus_zone_id(None) is False


async def test_mplus_helpers_degrade_to_none(monkeypatch):
    def boom(q, v):
        raise RuntimeError("no WCL")

    install(monkeypatch, boom)
    assert await current_mplus_season() is None
    assert await current_raid_tier() is None
    assert await is_mplus_zone_id(60) is False


async def test_current_patch_swallows_errors(monkeypatch):
    def boom(q, v):
        raise RuntimeError("no WCL")

    install(monkeypatch, boom)
    assert await current_patch() is None


# --- (d) brief loader (feature 015 replaces the cooldown registry) -------------------------


async def test_get_brief_uses_the_registered_loader_only_for_valid_types():
    record = BriefRecord("Mage", "Fire", "raid", "brief", (GuideCooldown("Combustion", 190319, 120.0),),
                         "12.1", None, datetime.now(UTC), "current", True)
    asked = []

    async def loader(class_name, spec, content_type):
        asked.append((class_name, spec, content_type))
        return record if content_type == "raid" else None

    clear_brief_loader()
    assert await get_brief("Mage", "Fire", "raid") is None  # no loader (CLI)
    set_brief_loader(loader)
    try:
        assert await get_brief(" Mage ", "Fire", "raid") is record
        assert await get_brief("Mage", "Fire", "mplus") is None  # never the other type
        assert await get_brief("Mage", "Fire", "pvp") is None
        assert await get_brief("", "Fire", "raid") is None
        assert asked == [("Mage", "Fire", "raid"), ("Mage", "Fire", "mplus")]
    finally:
        clear_brief_loader()


async def test_get_brief_swallows_loader_errors():
    async def broken(*a):
        raise RuntimeError("db down")

    set_brief_loader(broken)
    try:
        assert await get_brief("Mage", "Fire", "raid") is None
    finally:
        clear_brief_loader()
