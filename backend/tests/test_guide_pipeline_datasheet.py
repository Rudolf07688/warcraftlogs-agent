"""Guide data sheet from Warcraft Logs (feature 015, US6 — research R5/R6)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.app.config import settings
from backend.app.services.guide_pipeline import datasheet
from backend.app.services.guide_pipeline.models import GenerationBriefing
from backend.tests.test_guide_meta import MENU_PAYLOAD
from backend.tests.wcl_fakes import install
from wcl_agent.tools.benchmark import CastsEntry

ZONES = MENU_PAYLOAD["data"]["worldData"]["zones"]
RAID_ZONE = {**ZONES[2], "encounters": [{"id": 3470, "name": "Nek'zali"}, {"id": 3445, "name": "Sentinels"}]}
MPLUS_ZONE = {**ZONES[0], "encounters": [{"id": 12993, "name": "Altar of Fangs"}]}
MENU = {"data": {"worldData": {"zones": [MPLUS_ZONE, ZONES[1], RAID_ZONE]}}}


def briefing(content_type="raid", role="dps"):
    return GenerationBriefing(
        now_utc=datetime(2026, 10, 18, tzinfo=UTC), content_type=content_type, class_name="Mage",
        class_display="Mage", spec="Fire", role=role, class_specs=["Arcane", "Fire", "Frost"],
        live_patch="12.1.5", mplus_season="Mythic+ Season 2",
    )


def ranking(i, encounter, *, report=True, talents=None):
    entry = {
        "name": f"P{i}", "duration": 300_000, "bracketData": 280 + i % 5 if encounter < 9000 else 18 + i % 3,
        "talents": talents if talents is not None else [{"talentID": 1, "points": 1}, {"talentID": 2 + i % 2, "points": 1}],
    }
    if report:
        entry["report"] = {"code": f"R{encounter}x{i}", "fightID": 7}
    return entry


def responder(n_per_encounter=60, *, reportless=0):
    def respond(query, variables):
        if "MenuDiscovery" in query:
            return MENU
        if "SpecRankings" in query:
            enc = variables["encounterID"]
            rows = [ranking(i, enc, report=i >= reportless) for i in range(n_per_encounter)]
            return {"data": {"worldData": {"encounter": {"characterRankings": {"rankings": rows}}}}}
        code = variables.get("code", "")
        report = {}
        if "table(dataType: Casts" in query and "sourceID" in query:
            report["endTime"] = 1
            report["table"] = {"data": {"entries": [
                {"name": "Fireball", "guid": 133, "total": 100 + variables["sourceID"] % 3},
                {"name": "Combustion", "guid": 190319, "total": 2},
                {"name": "Shimmer", "guid": 212653, "total": 1},
            ]}}
        elif "ReportSummary" in query:
            report.update({
                "title": "t", "startTime": 0, "endTime": 1, "zone": {"id": 53, "name": "Abyss"},
                "masterData": {"actors": [{"id": 40 + k, "name": f"P{k}", "subType": "Mage"} for k in range(60)]},
                "fights": [],
            })
        elif "events(" in query:
            report["events"] = {"data": [
                {"type": "cast", "abilityGameID": 190319, "timestamp": 1_000},
                {"type": "cast", "abilityGameID": 190319, "timestamp": 121_000},
                {"type": "cast", "abilityGameID": 133, "timestamp": 2_000},
                {"type": "cast", "abilityGameID": 133, "timestamp": 4_500},
            ], "nextPageTimestamp": None}
        elif "dataType: Buffs" in query:
            report["endTime"] = 1
            report["table"] = {"data": {"totalTime": 300_000, "auras": [
                {"guid": 190319, "name": "Combustion", "totalUptime": 36_000},
                {"guid": 21562, "name": "Power Word: Fortitude", "totalUptime": 300_000}]}}
        elif "dataType: Debuffs" in query:
            report["endTime"] = 1
            report["table"] = {"data": {"totalTime": 300_000, "auras": [
                {"guid": 383608, "name": "Improved Scorch", "totalUptime": 270_000}]}}
        elif "playerDetails" in query:
            report["playerDetails"] = {"data": {"playerDetails": {"dps": [
                {"name": f"P{k}", "combatantInfo": {"stats": {"Crit": {"min": 1000 + k, "max": 1000 + k},
                                                              "Haste": {"min": 2000, "max": 2000}}}}
                for k in range(60)
            ]}}}
        else:
            raise AssertionError(f"unexpected query {query[:60]} {code}")
        return {"data": {"reportData": {"report": report}}}

    return respond


@pytest.fixture(autouse=True)
def _budget(monkeypatch):
    async def plenty():
        return 700.0, 720.0

    monkeypatch.setattr(datasheet, "_budget", plenty)


async def test_raid_sheet_from_logs_only_rankings(monkeypatch):
    fake = install(monkeypatch, responder())
    sheet = await datasheet.build_data_sheet(briefing())
    ranking_calls = [(q, v) for q, v in fake.calls if "SpecRankings" in q]
    assert ranking_calls and all("leaderboard: LogsOnly" in q and "includeCombatantInfo: true" in q for q, _ in ranking_calls)
    assert {v["metric"] for _, v in ranking_calls} == {"dps"} and {v["difficulty"] for _, v in ranking_calls} == {5}
    assert sheet.sufficient and sheet.scope.sample_size == settings.wcl_guide_datasheet_min_sample
    assert sheet.scope.zone_name == "The Venomous Abyss" and sheet.scope.encounters == ["Nek'zali", "Sentinels"]
    combust = next(a for a in sheet.abilities if a.ability_id == 190319)
    assert combust.casts_per_min_median == 0.4 and combust.min_gap_s == 120.0
    fireball = next(a for a in sheet.abilities if a.ability_id == 133)
    assert fireball.min_gap_s is None  # a 2.5 s gap is rotation, not a cooldown
    assert fireball.casts_per_min_p25 <= fireball.casts_per_min_median <= fireball.casts_per_min_p75
    uptimes = {u.ability_id: u for u in sheet.uptimes}
    assert uptimes[190319].kind == "buff" and uptimes[190319].uptime_pct_median == 12.0
    assert uptimes[383608].kind == "debuff" and uptimes[383608].uptime_pct_median == 90.0
    assert 21562 not in uptimes  # always-on raid buffs say nothing about the player
    assert {s.stat for s in sheet.stat_spread} == {"Crit", "Haste"}
    assert sheet.talent_builds and sum(b.share_pct for b in sheet.talent_builds) == 100.0
    assert {t.talent_id: t.pick_pct for t in sheet.talent_pick_rates}[1] == 100.0
    assert sheet.item_level_median is not None


async def test_cache_hit_on_second_call(monkeypatch, fake_redis):
    fake = install(monkeypatch, responder())
    first = await datasheet.build_data_sheet(briefing())
    n = fake.count("SpecRankings")
    second = await datasheet.build_data_sheet(briefing())
    assert fake.count("SpecRankings") == n and second == first


async def test_mplus_uses_playerscore_and_key_levels(monkeypatch):
    fake = install(monkeypatch, responder())
    sheet = await datasheet.build_data_sheet(briefing("mplus"))
    calls = [v for q, v in fake.calls if "SpecRankings" in q]
    assert {v["metric"] for v in calls} == {"playerscore"} and {v["difficulty"] for v in calls} == {10}
    assert sheet.scope.zone_name == "Mythic+ Season 2" and sheet.scope.key_level_floor == 18
    assert sheet.item_level_median is None


async def test_reportless_entries_skipped_and_thin_sample_insufficient(monkeypatch):
    fake = install(monkeypatch, responder(n_per_encounter=8, reportless=3))
    sheet = await datasheet.build_data_sheet(briefing())
    # P3..P7 have a report; the same names on the second boss are not counted twice.
    assert not sheet.sufficient and sheet.scope.sample_size == 5
    # Thin Mythic sample ⇒ Heroic was tried too.
    assert {v["difficulty"] for q, v in fake.calls if "SpecRankings" in q} == {5, 4}


async def test_low_budget_postpones_without_spending_points(monkeypatch):
    # QA PERF-001: below the chat reserve (40 % of the hourly limit) nothing is queried.
    async def low():
        return 200.0, 720.0

    monkeypatch.setattr(datasheet, "_budget", low)
    fake = install(monkeypatch, responder())
    with pytest.raises(datasheet.WclBudgetLow):
        await datasheet.build_data_sheet(briefing())
    assert fake.calls == []


async def test_budget_running_low_mid_sheet_postpones(monkeypatch):
    calls = iter([(700.0, 720.0), (700.0, 720.0), (100.0, 720.0)])

    async def draining():
        return next(calls, (100.0, 720.0))

    monkeypatch.setattr(datasheet, "_budget", draining)
    install(monkeypatch, responder())
    with pytest.raises(datasheet.WclBudgetLow):
        await datasheet.build_data_sheet(briefing())


async def test_source_ids_come_from_the_cached_report_summary(monkeypatch):
    fake = install(monkeypatch, responder())
    await datasheet.build_data_sheet(briefing())
    whole_raid = [q for q, _ in fake.calls if "table(dataType: Casts" in q and "sourceID" not in q]
    assert whole_raid == []  # no uncached whole-raid casts tables (QA PERF-005)


def test_pure_reducers():
    entries = [[ranking(i, 1) for i in range(3)], [ranking(i, 2) for i in range(2, 5)]]
    assert [e["name"] for e in datasheet.cohort_from(entries, 4)] == ["P0", "P2", "P1", "P3"]
    assert datasheet.merge_gaps([{1: 90.0}, {1: 60.0, 2: 30.0}]) == {1: 60.0, 2: 30.0}
    members = [(CastsEntry("a", 1, "Mage-Fire", None, 10, [{"guid": 5, "name": "X", "total": 10}]), 5.0),
               (CastsEntry("b", 2, "Mage-Fire", None, 0, []), 5.0)]
    assert datasheet.ability_stats(members, {}) == []  # one user of two is below the floor
    assert datasheet.talent_hash([{"talentID": 2}, {"talentID": 1}]) == datasheet.talent_hash([{"talentID": 1}, {"talentID": 2}])
