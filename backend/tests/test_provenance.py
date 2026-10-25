"""Provenance/completeness envelope on WCL tool results (feature 009, Phase 2).

WCL is faked with the shared ``wcl_fakes.install`` stub, whose ``query`` dispatches
on the GraphQL text. No network, no model.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.tests.wcl_fakes import install
from wcl_agent.tools import report_tools, tools
from wcl_agent.tools.provenance import (
    Completeness,
    Provenance,
    flatten_report_rankings,
    with_envelope,
)


def _install(monkeypatch, responder):
    return install(monkeypatch, responder)


# --- (a) with_envelope -----------------------------------------------------------


def test_envelope_only_on_non_error_results():
    err = {"status": "error", "error_message": "nope"}
    assert with_envelope(dict(err), Provenance(report_code="X")) == err

    ok = with_envelope({"status": "success", "x": 1}, Provenance(report_code="ABC", fight_id=None))
    assert ok["x"] == 1
    assert ok["provenance"]["report_code"] == "ABC"
    assert "fight_id" not in ok["provenance"]  # None keys dropped
    assert ok["provenance"]["fetched_at"].endswith("Z")
    assert ok["completeness"] == {
        "has_more": False,
        "truncated": False,
        "sample_size": None,
        "sample_scope": None,
    }


def test_envelope_detects_cap_truncation():
    big = report_tools._cap(["x" * 1000] * 100)
    assert big.get("_truncated") is True
    res = with_envelope({"status": "success", "table": big}, Provenance())
    assert res["completeness"]["truncated"] is True

    explicit = with_envelope(
        {"status": "success", "table": big},
        Provenance(),
        Completeness(has_more=True, sample_size=3, sample_scope="full"),
    )
    assert explicit["completeness"] == {
        "has_more": True,
        "truncated": True,
        "sample_size": 3,
        "sample_scope": "full",
    }


# --- (b) get_report_table --------------------------------------------------------


async def test_report_table_carries_provenance(monkeypatch):
    def responder(query, variables):
        assert "table(dataType: Casts" in query
        return {"data": {"reportData": {"report": {"table": {"data": {"entries": [{"name": "A"}]}}}}}}

    _install(monkeypatch, responder)
    res = await report_tools.get_report_table("ABC", "Casts", fight_id=9, source_id=7)
    assert res["status"] == "success"
    assert res["table"] == {"data": {"entries": [{"name": "A"}]}}
    assert res["provenance"]["report_code"] == "ABC"
    assert res["provenance"]["fight_id"] == 9
    assert res["provenance"]["source_id"] == 7
    assert res["completeness"]["truncated"] is False


async def test_report_table_all_fights_omits_fight_id(monkeypatch):
    _install(monkeypatch, lambda q, v: {"data": {"reportData": {"report": {"table": {}}}}})
    res = await report_tools.get_report_table("ABC", "Deaths")
    assert "fight_id" not in res["provenance"]
    assert "source_id" not in res["provenance"]


# --- (c) get_report_events has_more ---------------------------------------------


@pytest.mark.parametrize("next_ts,expected", [(123456, True), (None, False)])
async def test_report_events_has_more(monkeypatch, next_ts, expected):
    payload = {"data": [{"timestamp": 1}], "nextPageTimestamp": next_ts}
    _install(monkeypatch, lambda q, v: {"data": {"reportData": {"report": {"events": payload}}}})
    res = await report_tools.get_report_events("ABC", "Casts", fight_id=9, source_id=7, limit=1)
    assert res["status"] == "success"
    assert res["completeness"]["has_more"] is expected
    assert res["events"] == payload


# --- (d) get_rankings_distribution sample_scope ---------------------------------


def _rankings_page(n: int, has_more: bool):
    return {
        "data": {
            "worldData": {
                "encounter": {
                    "id": 3470,
                    "name": "Boss",
                    "characterRankings": {
                        "page": 1,
                        "hasMorePages": has_more,
                        "count": n,
                        "rankings": [
                            {"name": f"P{i}", "spec": "Fire", "amount": 1000 + i,
                             "server": {"name": "S", "region": "EU"},
                             "report": {"code": "R", "fightID": i}, "bracketData": 300}
                            for i in range(n)
                        ],
                    },
                }
            }
        }
    }


@pytest.mark.parametrize("has_more,scope", [(True, "top_of_leaderboard"), (False, "full")])
async def test_rankings_distribution_sample_scope(monkeypatch, has_more, scope):
    _install(monkeypatch, lambda q, v: _rankings_page(10, has_more))
    ctx = SimpleNamespace(state={})
    res = await tools.get_rankings_distribution(
        "Mage", "Fire", "dps", 1, ctx, encounter_id=3470, difficulty_id=4
    )
    assert res["status"] == "success"
    assert res["more_pages_available"] is has_more  # existing key untouched
    assert res["completeness"]["has_more"] is has_more
    assert res["completeness"]["sample_size"] == 10
    assert res["completeness"]["sample_scope"] == scope
    assert res["provenance"]["encounter_id"] == 3470
    assert res["provenance"]["difficulty"] == 4
    assert res["provenance"]["metric"] == "dps"


async def test_compare_specs_aggregates_completeness(monkeypatch):
    _install(monkeypatch, lambda q, v: _rankings_page(5, True))
    ctx = SimpleNamespace(state={})
    res = await tools.compare_specs("mage", "dps", 1, ctx, encounter_id=3470, difficulty_id=4)
    assert res["status"] == "success"
    assert [c["spec"] for c in res["comparison"]]  # existing key untouched
    assert res["completeness"]["sample_scope"] == "top_of_leaderboard"
    assert res["completeness"]["sample_size"] == 15  # 3 specs × 5
    assert res["provenance"]["encounter_id"] == 3470


# --- (e) whitelist fix ------------------------------------------------------------


async def test_resurrections_rejected_everywhere(monkeypatch):
    fake = _install(monkeypatch, lambda q, v: pytest.fail("must not query WCL"))
    for fn in (report_tools.get_report_table, report_tools.get_report_events, report_tools.get_report_graph):
        res = await fn("ABC", "Resurrections")
        assert res["status"] == "error"
        assert "Resurrections" not in res["valid"]
    assert fake.calls == []
    assert "Summons" in report_tools.TABLE_DATA_TYPES
    assert "Summons" in report_tools.EVENT_DATA_TYPES


# --- (f) flatten_report_rankings (shape per research R1) ------------------------


REPORT_RANKINGS_FIXTURE = {
    "data": [
        {
            "fightID": 9,
            "partition": 1,
            "zone": {"id": 53, "name": "The Venomous Abyss"},
            "encounter": {"id": 3470, "name": "Nek'zali the Soulcoiler"},
            "difficulty": 4,
            "kill": True,
            "duration": 264000,
            "deaths": 9,
            "roles": {
                "tanks": {"name": "Tanks", "characters": [
                    {"id": 11, "name": "Tank", "server": {"name": "Azshara", "region": "KR"},
                     "class": "Warrior", "spec": "Protection", "amount": 500.0,
                     "bracketData": 290.1, "bracket": 29, "rank": 100, "totalParses": 400,
                     "rankPercent": 75.0, "bracketPercent": 80.0}
                ]},
                "healers": {"name": "Healers", "characters": []},
                "dps": {"name": "DPS", "characters": [
                    {"id": 12, "name": "Hrslkks", "server": {"name": "Azshara", "region": "KR"},
                     "class": "Mage", "spec": "Fire", "amount": 1234567.8,
                     "bracketData": 301.2, "bracket": 30, "rank": 500, "totalParses": 2159,
                     "rankPercent": 76.9, "bracketPercent": 81.2},
                    {"id": 13, "name": "Nobody", "class": "Mage", "spec": "Frost"},
                ]},
            },
        }
    ]
}


def test_flatten_report_rankings():
    rows = flatten_report_rankings(
        REPORT_RANKINGS_FIXTURE, compare="Parses", timeframe="Today", metric="dps"
    )
    assert [r.name for r in rows] == ["Tank", "Hrslkks", "Nobody"]
    mage = rows[1]
    assert mage.role == "dps"
    assert mage.server == "Azshara"
    assert mage.class_name == "Mage" and mage.spec == "Fire"
    assert mage.population == "parses" and mage.timeframe == "today"
    assert mage.rank_percent == 76.9 and mage.bracket_percent == 81.2
    assert mage.bracket == 30 and mage.item_level == 301.2
    assert mage.total_parses == 2159
    assert mage.partition == 1 and mage.encounter_id == 3470 and mage.difficulty == 4
    assert mage.fight_id == 9 and mage.kill is True and mage.duration_s == 264.0
    assert mage.amount == 1234567.8 and mage.metric == "dps"
    # Missing keys degrade to None instead of raising.
    assert rows[2].rank_percent is None and rows[2].server is None and rows[2].total_parses is None
    assert rows[0].role == "tank"


def test_flatten_report_rankings_defaults_and_empty():
    assert flatten_report_rankings(None, compare="Rankings", timeframe="Historical", metric="dps") == []
    rows = flatten_report_rankings(
        {"data": [{"fightID": 1, "roles": {"dps": {"characters": [{"name": "A"}]}}}]},
        compare="Rankings", timeframe="Historical", metric="hps",
    )
    assert rows[0].population == "rankings" and rows[0].timeframe == "historical"
    assert rows[0].duration_s is None and rows[0].encounter_id is None


async def test_leaderboard_pages_after_the_first_are_fetched_together(monkeypatch):
    """PERF-005: pages 2..N run concurrently; pages past the end are dropped."""
    import asyncio

    from backend.tests.wcl_fakes import install
    from wcl_agent.tools.tools import _fetch_rankings

    inflight = peak = 0

    async def responder(query, variables):
        nonlocal inflight, peak
        inflight += 1
        peak = max(peak, inflight)
        await asyncio.sleep(0.02)
        inflight -= 1
        page = variables["page"]
        more = page < 3  # the board ends on page 3
        rankings = [{"amount": page}] if page <= 3 else []
        return {"data": {"worldData": {"encounter": {"characterRankings": {
            "page": page, "hasMorePages": more, "rankings": rankings}}}}}

    install(monkeypatch, responder)
    sel = {"encounterID": 1, "difficultyID": 5, "partition": None}
    entries, more = await _fetch_rankings(sel, "dps", None, None, 5)
    assert [e["amount"] for e in entries] == [1, 2, 3] and more is False
    assert peak >= 2  # pages 2..5 overlapped
