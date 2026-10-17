"""compare_player_to_cohort (feature 009, US2) — pure helpers + faked-WCL tool runs."""

from __future__ import annotations

from typing import Any

import pytest

from backend.tests.wcl_fakes import install, rate_limit_payload
from wcl_agent import benchmark
from wcl_agent.benchmark import (
    CastsEntry,
    aggregate_measures,
    band_pages,
    budget_size,
    cohort_label,
    compare_player_to_cohort,
    reduce_casts_entry,
    select_cohort,
)

# --- pure helpers -------------------------------------------------------------------


def test_band_pages_typical_population():
    b = band_pages(2159)
    assert (b.lo_rank, b.hi_rank) == (108, 539)
    assert b.pages == [3, 4, 5]  # centred on rank ~324 (page 4)
    assert all(b.lo_rank <= (p - 1) * 100 + 1 and p * 100 >= b.lo_rank for p in b.pages)
    assert len(b.pages) <= 3 and not b.clipped


def test_band_pages_clipped_past_page_20():
    b = band_pages(60_000)
    assert b.pages == [18, 19, 20] and b.clipped


def test_band_pages_small_population():
    assert band_pages(60).pages == [1]
    assert band_pages(None).pages == [1]
    assert band_pages(0).clipped is False


def _entries(durations: list[int], names=None) -> list[dict[str, Any]]:
    return [
        {"name": (names or {}).get(i, f"P{i}"), "duration": d, "amount": 100 + i,
         "report": {"code": f"R{i}", "fightID": i}, "bracketData": 300,
         "server": {"name": "S", "region": "EU"}}
        for i, d in enumerate(durations)
    ]


def test_select_cohort_window_exclusion_and_order():
    entries = _entries([300_000, 310_000, 340_000, 360_000, 250_000, 100_000, 299_000],
                       names={0: "Me"})
    sel = select_cohort(entries, "me", 300_000, 5)
    assert not sel.widened and sel.window_pct == 15
    # Me excluded; within ±15% of 300 s: 310, 340, 250(no: 16.7%), 299 → nearest first
    assert [m["name"] for m in sel.members] == ["P6", "P1", "P2"]


def test_select_cohort_widens_when_fewer_than_three():
    entries = _entries([300_000, 350_000, 370_000, 380_000, 500_000])
    sel = select_cohort(entries, "Me", 300_000, 5)
    assert sel.widened and sel.window_pct == 25
    assert [m["name"] for m in sel.members] == ["P0", "P1", "P2"]  # 380 s is 26.7% → out


@pytest.mark.parametrize(
    "size,unmet,label",
    [(1, [], "anecdotal"), (0, [], "anecdotal"), (2, [], "directional"),
     (5, ["band clipped"], "directional"), (3, [], "matched"), (5, [], "matched")],
)
def test_cohort_label(size, unmet, label):
    assert cohort_label(size, unmet) == label


@pytest.mark.parametrize(
    "requested,remaining,expected",
    [(5, 500, 5), (9, 500, 5), (0, 500, 1), (5, 99, 3), (2, 99, 2), (5, 39, 1), (5, None, 5)],
)
def test_budget_size(requested, remaining, expected):
    assert budget_size(requested, remaining) == expected


CASTS_TABLE = {"data": {"entries": [
    {"name": "Hrslkks", "id": 7, "icon": "Mage-Fire", "itemLevel": 301.2, "total": 203,
     "activeTime": 90_000, "abilities": [
         {"guid": 133, "name": "Fireball", "total": 200},
         {"guid": 190319, "name": "Combustion", "total": 3}]},
    {"name": "Other", "id": 8, "icon": "Warrior-Fury", "itemLevel": 299, "total": 50,
     "abilities": [{"guid": 1, "name": "Slam", "total": 50}]},
]}}


def test_reduce_casts_entry_by_name_and_id():
    by_name = reduce_casts_entry(CASTS_TABLE, name="hrslkks")
    assert by_name.source_id == 7 and by_name.class_spec == "Mage-Fire"
    assert by_name.abilities == [
        {"guid": 133, "name": "Fireball", "total": 200},
        {"guid": 190319, "name": "Combustion", "total": 3},
    ]
    assert not hasattr(by_name, "activeTime")
    assert reduce_casts_entry(CASTS_TABLE, source_id=8).name == "Other"
    assert reduce_casts_entry(CASTS_TABLE, name="Nobody") is None
    assert reduce_casts_entry(None, name="x") is None


def test_aggregate_measures_rates_and_median():
    player = CastsEntry("Me", 7, "Mage-Fire", 300, 103,
                        [{"guid": 1, "name": "A", "total": 100}, {"guid": 2, "name": "B", "total": 3}])
    members = [
        (CastsEntry("M1", 1, None, None, 120, [{"guid": 1, "name": "A", "total": 120}]), 5.0),
        (CastsEntry("M2", 2, None, None, 100, [{"guid": 1, "name": "A", "total": 100}, {"guid": 2, "name": "B", "total": 5}]), 5.0),
        (CastsEntry("M3", 3, None, None, 80, [{"guid": 1, "name": "A", "total": 80}]), 4.0),
    ]
    measures = aggregate_measures(player, 2.5, members)
    a = next(m for m in measures if m["ability"]["guid"] == 1)
    assert a["player_casts_per_min"] == 40.0  # 100 casts over 2.5 min alive
    assert (a["cohort_median_per_min"], a["cohort_min"], a["cohort_max"], a["cohort_users"]) == (20.0, 20.0, 24.0, 3)
    b = next(m for m in measures if m["ability"]["guid"] == 2)
    assert b["cohort_users"] == 1 and b["cohort_median_per_min"] == 0.0


# --- tool-level (faked WCL) --------------------------------------------------------------

PLAYER_CODE, FIGHT = "PLAYER", 9
FIGHT_START, FIGHT_END = 1_000_000, 1_300_000  # 300 s


def make_responder(*, kill=True, deaths=(), duplicate=False, remaining=500, total_parses=2159):
    actors = [
        {"id": 7, "name": "Hrslkks", "server": "Azshara", "subType": "Mage"},
        {"id": 8, "name": "Other", "server": "Azshara", "subType": "Warrior"},
    ]
    friendly = [7, 8]
    if duplicate:
        actors.append({"id": 9, "name": "Hrslkks", "server": "Elsewhere", "subType": "Mage"})
        friendly.append(9)
    rankings = {"data": [{
        "fightID": FIGHT, "partition": 1, "encounter": {"id": 3470, "name": "Boss"},
        "difficulty": 4, "kill": kill, "duration": FIGHT_END - FIGHT_START,
        "roles": {"dps": {"characters": [
            {"id": 555, "name": "Hrslkks", "server": {"name": "Azshara"}, "class": "Mage",
             "spec": "Fire", "amount": 1000.0, "bracketData": 301.2, "bracket": 30,
             "totalParses": total_parses, "rankPercent": 80.0, "bracketPercent": 85.0},
        ]}},
    }]}

    def responder(query, variables):
        if "rateLimitData" in query:
            return rate_limit_payload(remaining)
        if "rankings(fightIDs" in query:
            return {"data": {"reportData": {"report": {
                "masterData": {"actors": actors},
                "fights": [{"id": FIGHT, "startTime": FIGHT_START, "endTime": FIGHT_END,
                            "kill": kill, "encounterID": 3470, "difficulty": 4,
                            "friendlyPlayers": friendly}],
                "rankings": rankings if kill else {"data": []},
            }}}}
        if "characterRankings" in query:
            page = variables["page"]
            assert variables["className"] == "Mage" and variables["specName"] == "Fire"
            assert variables["partition"] == 1 and variables["difficulty"] == 4
            entries = [
                {"name": f"M{page}_{i}", "class": "Mage", "spec": "Fire", "amount": 900 + i,
                 "duration": 300_000 + (i - 50) * 2000,  # 200–400 s
                 "report": {"code": f"R{page}_{i}", "fightID": i + 1}, "bracketData": 300 + i / 10,
                 "server": {"name": "S", "region": "EU"}}
                for i in range(100)
            ]
            return {"data": {"worldData": {"encounter": {"characterRankings": {
                "page": page, "hasMorePages": True, "count": 100, "rankings": entries}}}}}
        if "dataType: Deaths" in query:
            return {"data": {"reportData": {"report": {"table": {"data": {"entries": [
                {"name": "Hrslkks", "id": 7, "timestamp": FIGHT_START + d} for d in deaths
            ]}}}}}}
        if "events(dataType: Casts" in query:
            return {"data": {"reportData": {"report": {"events": {"data": [], "nextPageTimestamp": None}}}}}
        if "dataType: Casts" in query:
            code = variables["code"]
            if code == PLAYER_CODE:
                return {"data": {"reportData": {"report": {"table": CASTS_TABLE}}}}
            # member report: one entry named like the leaderboard row
            page, i = code[1:].split("_")
            return {"data": {"reportData": {"report": {"table": {"data": {"entries": [
                {"name": f"M{page}_{i}", "id": 1, "icon": "Mage-Fire", "total": 254,
                 "abilities": [{"guid": 133, "name": "Fireball", "total": 250},
                               {"guid": 190319, "name": "Combustion", "total": 4}]}]}}}}}}
        raise AssertionError(f"unexpected query: {query[:80]}")

    return responder


async def test_wipe_is_limited(monkeypatch):
    install(monkeypatch, make_responder(kill=False))
    res = await compare_player_to_cohort(PLAYER_CODE, FIGHT, "Hrslkks")
    assert res["status"] == "limited"
    assert "wipe" in res["reason"]
    assert res["player"]["source_id"] == 7
    assert res["provenance"]["report_code"] == PLAYER_CODE


async def test_unknown_player_lists_present(monkeypatch):
    install(monkeypatch, make_responder())
    res = await compare_player_to_cohort(PLAYER_CODE, FIGHT, "Nobody")
    assert res["status"] == "error"
    assert res["players_present"] == ["Hrslkks", "Other"]


async def test_duplicate_name_needs_source_id(monkeypatch):
    install(monkeypatch, make_responder(duplicate=True))
    res = await compare_player_to_cohort(PLAYER_CODE, FIGHT, "Hrslkks")
    assert res["status"] == "error"
    assert [c["source_id"] for c in res["candidates"]] == [7, 9]
    ok = await compare_player_to_cohort(PLAYER_CODE, FIGHT, "Hrslkks", source_id=7)
    assert ok["status"] == "success" and ok["player"]["source_id"] == 7


async def test_success_shape_and_links(monkeypatch):
    fake = install(monkeypatch, make_responder())
    res = await compare_player_to_cohort(PLAYER_CODE, FIGHT, "Hrslkks")
    assert res["status"] == "success"
    cohort = res["cohort"]
    assert cohort["size"] == 5 and cohort["requested_size"] == 5
    assert cohort["label"] == "matched" and cohort["unmet_criteria"] == []
    assert cohort["criteria"]["partition"] == 1 and cohort["criteria"]["duration_window_pct"] == 15
    assert cohort["criteria"]["percentile_band"] == [75, 95]
    for m in cohort["members"]:
        assert m["link"] == f"https://www.warcraftlogs.com/reports/{m['report_code']}#fight={m['fight_id']}"
        assert abs(m["duration_s"] - 300) <= 45
    assert res["throughput"]["player_amount"] == 1000.0 and res["throughput"]["cohort_median"] is not None
    fireball = next(m for m in res["measures"] if m["ability"]["guid"] == 133)
    assert fireball["player_casts_per_min"] == 40.0  # 200 casts / 5 min alive (no deaths)
    assert fireball["cohort_users"] == 5
    player = res["player"]
    assert player["dead_s"] == 0 and player["alive_s"] == 300 and player["rate_basis"] == "alive_time"
    assert player["percentile"]["rank_percent"] == 80.0 and player["percentile"]["bracket_percent"] == 85.0
    assert player["link"].endswith("#fight=9")
    assert res["provenance"]["partition"] == 1 and res["provenance"]["source_id"] == 7
    assert res["completeness"]["sample_size"] == 5 and res["completeness"]["sample_scope"] == "full"
    assert fake.count("characterRankings") == 3  # ≤3 band pages
    # heavy Casts tables never returned raw
    assert "activeTime" not in str(res)


async def test_early_death_rates_use_alive_time(monkeypatch):
    install(monkeypatch, make_responder(deaths=[180_000]))  # died at 60% of a 300 s kill
    res = await compare_player_to_cohort(PLAYER_CODE, FIGHT, "Hrslkks")
    player = res["player"]
    assert player["dead_s"] == pytest.approx(120, abs=1)
    assert player["alive_s"] == pytest.approx(180, abs=1)
    assert player["rate_basis"] == "alive_time"
    fireball = next(m for m in res["measures"] if m["ability"]["guid"] == 133)
    assert fireball["player_casts_per_min"] == pytest.approx(200 / 3, abs=0.1)  # ÷ 180 s, not 300 s


async def test_low_budget_shrinks_cohort(monkeypatch):
    install(monkeypatch, make_responder(remaining=30))
    res = await compare_player_to_cohort(PLAYER_CODE, FIGHT, "Hrslkks")
    assert res["cohort"]["size"] == 1 and res["cohort"]["label"] == "anecdotal"
    assert any("budget" in u for u in res["cohort"]["unmet_criteria"])


async def test_band_clipped_is_disclosed(monkeypatch):
    install(monkeypatch, make_responder(total_parses=60_000))
    res = await compare_player_to_cohort(PLAYER_CODE, FIGHT, "Hrslkks")
    assert res["completeness"]["sample_scope"] == "band_clipped"
    assert res["cohort"]["label"] == "directional"
    assert any("clipped" in u for u in res["cohort"]["unmet_criteria"])


async def test_bad_inputs():
    assert (await compare_player_to_cohort("X", 1, "a", metric="wdps"))["status"] == "error"
    assert (await compare_player_to_cohort("X", 0, "a"))["status"] == "error"
    assert benchmark.MAX_SIZE == 5


# --- tool_summary branch (T017) -----------------------------------------------------------


def test_tool_summary_for_cohort():
    from backend.app.services.tool_summary import summarize_tool_result

    ok = {"status": "success", "cohort": {"size": 5, "label": "matched",
                                           "criteria": {"duration_window_pct": 15}}}
    assert summarize_tool_result("compare_player_to_cohort", True, ok) == "cohort of 5 (matched) — ±15% duration"
    limited = {"status": "limited", "reason": "wipe — no ranked population; any comparison is limited"}
    assert summarize_tool_result("compare_player_to_cohort", True, limited).startswith("limited: wipe")
    err = {"status": "error", "error_message": "Player name 'X' matches 2 actors in this fight; pass source_id."}
    assert "pass source_id" in summarize_tool_result("compare_player_to_cohort", False, err)
