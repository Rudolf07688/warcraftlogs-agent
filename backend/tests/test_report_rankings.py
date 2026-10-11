"""get_report_rankings compare/timeframe + flattened percentiles (feature 009, US3)."""

from __future__ import annotations

import pytest

from backend.tests.test_provenance import REPORT_RANKINGS_FIXTURE
from backend.tests.wcl_fakes import install
from wcl_agent.report_tools import get_report_rankings


def _responder(query, variables):
    assert "rankings(fightIDs: $fightIDs" in query
    return {"data": {"reportData": {"report": {"rankings": REPORT_RANKINGS_FIXTURE}}}}


def test_compare_and_timeframe_are_sent_and_echoed(monkeypatch):
    fake = install(monkeypatch, _responder)
    res = get_report_rankings("ABC", 9, compare="Parses", timeframe="Today")
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


def test_defaults_are_rankings_historical(monkeypatch):
    fake = install(monkeypatch, _responder)
    res = get_report_rankings("ABC")
    query, variables = fake.calls[0]
    assert "compare: Rankings" in query and "timeframe: Historical" in query
    assert variables["fightIDs"] is None
    assert res["provenance"]["compare"] == "Rankings"
    assert res["provenance"]["timeframe"] == "Historical"
    assert "fight_id" not in res["provenance"]
    assert res["percentiles"][0]["population"] == "rankings"
    assert res["percentiles"][0]["timeframe"] == "historical"


@pytest.mark.parametrize("kwargs", [{"compare": "Best"}, {"timeframe": "Yesterday"}])
def test_invalid_enums_rejected_without_a_call(monkeypatch, kwargs):
    fake = install(monkeypatch, _responder)
    res = get_report_rankings("ABC", 9, **kwargs)
    assert res["status"] == "error"
    assert res["valid"] in (["Parses", "Rankings"], ["Historical", "Today"])
    assert fake.calls == []
