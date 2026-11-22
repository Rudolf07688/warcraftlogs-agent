"""get_report_rankings compare/timeframe + flattened percentiles (feature 009, US3)."""

from __future__ import annotations

import pytest

from backend.tests.test_provenance import REPORT_RANKINGS_FIXTURE
from backend.tests.wcl_fakes import install
from wcl_agent.tools.report_tools import get_report_rankings


# A report summary: trash (no encounter), a boss wipe, a boss kill and a Mythic+ key run.
FIGHTS = [
    {"id": 1, "name": "Trash", "encounterID": 0},
    {"id": 4, "name": "Ulgrax", "encounterID": 2902, "kill": True},
    {"id": 2, "name": "Ulgrax", "encounterID": 2902, "kill": False},
    {"id": 7, "name": "Ara-Kara", "encounterID": 12660, "kill": True, "keystoneLevel": 12},
]


def _summary(fights):
    return {"startTime": 0, "endTime": 1, "zone": None, "masterData": {"actors": []}, "fights": fights}


def _responder(query, variables, fights=FIGHTS):
    if "rankings(" not in query:  # the report summary (fights)
        return {"data": {"reportData": {"report": _summary(fights)}}}
    assert "rankings(fightIDs: $fightIDs" in query
    return {"data": {"reportData": {"report": {"rankings": REPORT_RANKINGS_FIXTURE}}}}


async def test_compare_and_timeframe_are_sent_and_echoed(monkeypatch):
    fake = install(monkeypatch, _responder)
    res = await get_report_rankings("ABC", 9, compare="Parses", timeframe="Today")
    assert res["status"] == "success"
    query, variables = fake.calls[0]
    assert "compare: Parses" in query and "timeframe: Today" in query
    assert variables["fightIDs"] == [9]
    assert res["rankings"] == REPORT_RANKINGS_FIXTURE  # raw key unchanged
    assert res["provenance"]["compare"] == "Parses"
    assert res["provenance"]["timeframe"] == "Today"
    assert res["provenance"]["report_code"] == "ABC" and res["provenance"]["fight_id"] == 9
    mage = next(p for p in res["percentiles"] if p["name"] == "Hrslkks")
    assert mage["population"] == "parses" and mage["timeframe"] == "today"
    assert mage["rank_percent"] == 76.9 and mage["bracket_percent"] == 81.2
    assert mage["total_parses"] == 2159 and mage["partition"] == 1


async def test_defaults_are_rankings_historical(monkeypatch):
    fake = install(monkeypatch, _responder)
    res = await get_report_rankings("ABCdefaults")
    query, variables = fake.calls[-1]
    assert "compare: Rankings" in query and "timeframe: Historical" in query
    assert variables["fightIDs"] == [2, 4, 7]
    assert res["provenance"]["compare"] == "Rankings"
    assert res["provenance"]["timeframe"] == "Historical"
    assert "fight_id" not in res["provenance"]
    assert res["percentiles"][0]["population"] == "rankings"
    assert res["percentiles"][0]["timeframe"] == "historical"


@pytest.mark.parametrize("kwargs", [{"compare": "Best"}, {"timeframe": "Yesterday"}])
async def test_invalid_enums_rejected_without_a_call(monkeypatch, kwargs):
    fake = install(monkeypatch, _responder)
    res = await get_report_rankings("ABC", 9, **kwargs)
    assert res["status"] == "error"
    assert res["valid"] in (["Parses", "Rankings"], ["Historical", "Today"])
    assert fake.calls == []


# sc-587: WCL answers rankings(fightIDs: null) with "Internal server error" on some reports
# (live-check:086-pre, three Veritass reports); an explicit list of the encounter fights works.
async def test_whole_report_rankings_never_send_fight_ids_null(monkeypatch):
    fake = install(monkeypatch, _responder)
    res = await get_report_rankings("ABCwhole")
    sent = [v for q, v in fake.calls if "rankings(" in q]
    assert sent == [{"code": "ABCwhole", "fightIDs": [2, 4, 7]}]  # encounter fights only, no trash
    assert res["status"] == "success" and "fight_id" not in res["provenance"]


async def test_whole_report_rankings_without_boss_fights_is_an_error_without_a_rankings_call(monkeypatch):
    fake = install(monkeypatch, lambda q, v: _responder(q, v, fights=FIGHTS[:1]))
    res = await get_report_rankings("ABCtrash")
    assert res == {"status": "error", "error_message": "Report 'ABCtrash' has no boss fights to rank."}
    assert fake.count("rankings(") == 0


async def test_a_long_progression_night_is_still_one_rankings_call(monkeypatch):
    """Bound: 1,000 boss pulls are one summary read and one rankings request, never one per fight."""
    pulls = [{"id": i, "name": "Ulgrax", "encounterID": 2902, "kill": False} for i in range(1, 1001)]
    fake = install(monkeypatch, lambda q, v: _responder(q, v, fights=pulls))
    res = await get_report_rankings("ABCprog")
    assert res["status"] == "success"
    assert len(fake.calls) == 2 and fake.count("rankings(") == 1
    assert fake.calls[-1][1]["fightIDs"] == list(range(1, 1001))
