"""get_cooldown_usage (feature 009, US4) — pure helpers + faked-WCL tool runs."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.tests.test_guide_meta import MENU_PAYLOAD
from backend.tests.wcl_fakes import install
from wcl_agent.cooldowns import get_cooldown_usage, match_uses, opportunities
from wcl_agent.guide_meta import GuideCooldown, GuideMeta, clear_guide_meta, set_guide_meta

# --- pure helpers -------------------------------------------------------------------


@pytest.mark.parametrize(
    "eligible,cd,charges,expected",
    [(263, 120, 1, 3), (60, 120, 1, 1), (263, 120, 2, 4), (0, 120, 1, 1), (100, 0, 1, 0), (119.9, 120, 1, 1)],
)
def test_opportunities(eligible, cd, charges, expected):
    assert opportunities(eligible, cd, charges) == expected


def test_match_uses_by_spell_id_then_name():
    cds = [
        GuideCooldown("Combustion", 190319, 120.0),
        GuideCooldown("shifting power", None, 60.0),
        GuideCooldown("Ice Block", 45438, 240.0),
        GuideCooldown("Nothing", None, 30.0),
    ]
    abilities = [
        {"guid": 190319, "name": "Combustion (renamed)", "total": 2},
        {"guid": 382440, "name": "Shifting Power", "total": 3},
        {"guid": 999, "name": "Ice Block", "total": 1},  # name matches, id does not
    ]
    assert match_uses(cds, abilities) == [2, 3, 1, 0]


# --- tool-level (faked WCL + registry) ------------------------------------------------------

CODE, FIGHT = "ABC", 9
START, END = 1_000_000, 1_300_000  # 300 s
CASTS_ENTRY = {
    "name": "Hrslkks", "id": 7, "icon": "Mage-Fire", "itemLevel": 301, "total": 103,
    "activeTime": 5_000,  # deliberately misleading: must never drive eligible time
    "abilities": [
        {"guid": 133, "name": "Fireball", "total": 100},
        {"guid": 190319, "name": "Combustion", "total": 1},
        {"guid": 382440, "name": "Shifting Power", "total": 2},
    ],
}


def make_responder(*, deaths=(), intermission=True, duplicate=False):
    actors = [
        {"id": 7, "name": "Hrslkks", "server": "Azshara", "subType": "Mage"},
        {"id": 8, "name": "Other", "server": "Azshara", "subType": "Warrior"},
    ]
    friendly = [7, 8]
    if duplicate:
        actors.append({"id": 9, "name": "Hrslkks", "server": "Elsewhere", "subType": "Mage"})
        friendly.append(9)
    transitions = [
        {"id": 1, "startTime": START},
        {"id": 2, "startTime": START + 100_000},  # intermission 100–160 s
        {"id": 3, "startTime": START + 160_000},
    ]

    def responder(query, variables):
        if "MenuDiscovery" in query:
            return MENU_PAYLOAD
        if "phaseTransitions" in query:
            return {"data": {"reportData": {"report": {
                "masterData": {"actors": actors},
                "phases": [{"encounterID": 3470, "phases": [
                    {"id": 1, "name": "Stage One", "isIntermission": False},
                    {"id": 2, "name": "Intermission", "isIntermission": intermission},
                    {"id": 3, "name": "Stage Two", "isIntermission": False}]}],
                "fights": [{"id": FIGHT, "startTime": START, "endTime": END, "kill": True,
                            "encounterID": 3470, "difficulty": 4, "friendlyPlayers": friendly,
                            "phaseTransitions": transitions}],
            }}}}
        if "dataType: Deaths" in query:
            return {"data": {"reportData": {"report": {"table": {"data": {"entries": [
                {"name": "Hrslkks", "id": 7, "timestamp": START + d} for d in deaths]}}}}}}
        if "events(dataType: Casts" in query:
            return {"data": {"reportData": {"report": {"events": {"data": [], "nextPageTimestamp": None}}}}}
        if "dataType: Casts" in query:
            return {"data": {"reportData": {"report": {"table": {"data": {"entries": [
                CASTS_ENTRY, {"name": "Other", "id": 8, "icon": "Warrior-Fury", "total": 1, "abilities": []}]}}}}}}
        raise AssertionError(f"unexpected query: {query[:80]}")

    return responder


def _register(game_patch="12.1"):
    clear_guide_meta()
    set_guide_meta(GuideMeta(
        "Mage", "Fire", game_patch, datetime(2026, 10, 7, tzinfo=UTC),
        (GuideCooldown("Combustion", 190319, 120.0), GuideCooldown("Shifting Power", None, 60.0)),
    ))


async def test_death_and_intermission_shrink_eligible_time(monkeypatch):
    _register()
    install(monkeypatch, make_responder(deaths=[240_000]))  # dead for the last 60 s
    res = await get_cooldown_usage(CODE, FIGHT, "Hrslkks")
    assert res["status"] == "success"
    t = res["time"]
    assert (t["fight_s"], t["dead_s"], t["intermission_s"], t["eligible_s"]) == (300.0, 60.0, 60.0, 180.0)
    assert "target immunity outside intermissions" in t["excluded_windows_unknown"]
    assert res["player"] == {"name": "Hrslkks", "source_id": 7, "class": "Mage", "spec": "Fire"}
    assert res["guide"]["available"] is True and res["guide"]["freshness"] == "current"
    comb = next(c for c in res["cooldowns"] if c["name"] == "Combustion")
    assert comb["uses"] == 1 and comb["opportunities"] == 2  # 1 + floor(180/120); 3 without exclusions
    assert comb["approximate"] is True and comb["freshness_caveat"] is False
    shift = next(c for c in res["cooldowns"] if c["name"] == "Shifting Power")
    assert shift["uses"] == 2 and shift["opportunities"] == 4  # matched by name
    fireball = next(r for r in res["rates"] if r["ability"]["guid"] == 133)
    assert fireball["casts"] == 100 and fireball["casts_per_min"] == pytest.approx(100 / 3, abs=0.01)
    assert res["provenance"]["source_id"] == 7 and res["provenance"]["encounter_id"] == 3470
    assert res["completeness"]["truncated"] is False


async def test_eligible_time_ignores_wcl_active_time(monkeypatch):
    _register()
    install(monkeypatch, make_responder(intermission=False))
    res = await get_cooldown_usage(CODE, FIGHT, "Hrslkks")
    assert res["time"]["eligible_s"] == 300.0  # not the 5 s activeTime in the Casts entry
    assert res["time"]["intermission_s"] == 0.0
    assert next(c for c in res["cooldowns"] if c["name"] == "Combustion")["opportunities"] == 3
    assert "activeTime" not in str(res)


async def test_no_guide_entry_means_rates_only(monkeypatch):
    clear_guide_meta()
    install(monkeypatch, make_responder())
    res = await get_cooldown_usage(CODE, FIGHT, "Hrslkks")
    assert res["guide"]["available"] is False and res["guide"]["game_patch"] is None
    assert res["cooldowns"] == []
    assert len(res["rates"]) == 3


async def test_unknown_patch_guide_flags_every_cooldown(monkeypatch):
    _register(game_patch=None)
    install(monkeypatch, make_responder())
    res = await get_cooldown_usage(CODE, FIGHT, "Hrslkks")
    assert res["guide"]["freshness"] == "unknown"
    assert res["cooldowns"] and all(c["freshness_caveat"] for c in res["cooldowns"])


async def test_player_errors(monkeypatch):
    _register()
    install(monkeypatch, make_responder())
    missing = await get_cooldown_usage(CODE, FIGHT, "Nobody")
    assert missing["status"] == "error" and missing["players_present"] == ["Hrslkks", "Other"]
    install(monkeypatch, make_responder(duplicate=True))
    dup = await get_cooldown_usage(CODE, FIGHT, "Hrslkks")
    assert dup["status"] == "error" and [c["source_id"] for c in dup["candidates"]] == [7, 9]
    assert (await get_cooldown_usage(CODE, FIGHT, "Hrslkks", source_id=7))["status"] == "success"
    assert (await get_cooldown_usage(CODE, 0, "Hrslkks"))["status"] == "error"


def test_tool_summary_for_cooldowns():
    from backend.app.services.tool_summary import summarize_tool_result

    ok = {"status": "success", "cooldowns": [1, 2, 3], "guide": {"available": True},
          "time": {"eligible_s": 252.0, "fight_s": 264.0}}
    assert summarize_tool_result("get_cooldown_usage", True, ok) == "3 cooldowns · eligible 4m12s of 4m24s"
    none = {"status": "success", "cooldowns": [], "guide": {"available": False},
            "time": {"eligible_s": 252.0, "fight_s": 264.0}}
    assert summarize_tool_result("get_cooldown_usage", True, none) == "rates only — no guide cooldowns · eligible 4m12s of 4m24s"
