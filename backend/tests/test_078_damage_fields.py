"""sc-574: Deaths and DamageTaken results label the damage fields of a hit.

The Gravebound answer quoted unmitigatedAmount (30.9M) and overkill (20.7M) as the hit; the
hit WCL shows is amount + absorbed + overkill (23.6M). The figures below are the killing hit
from report bjXfNc92d8CPGhvB, fight 1 (live-check:078-pre).
"""

from __future__ import annotations

import pytest

from backend.tests import wcl_fakes
from wcl_agent.tools import report_tools

HIT = {"timestamp": 1109129, "type": "damage", "amount": 618352, "absorbed": 2325962,
       "mitigated": 7300688, "overkill": 20651938, "unmitigatedAmount": 30896940}


def _install(monkeypatch, field, value):
    wcl_fakes.install(monkeypatch, lambda q, v: {"data": {"reportData": {"report": {field: value}}}})


@pytest.mark.parametrize("data_type", ["Deaths", "DamageTaken"])
async def test_damage_tables_label_the_hit_fields(monkeypatch, data_type):
    _install(monkeypatch, "table", {"data": {"entries": [{"name": "Veritass", "id": 11, "events": [HIT]}]}})
    res = await report_tools.get_report_table("bjXfNc92d8CPGhvB", data_type, fight_id=1)
    note = res["damage_fields"]
    assert "amount + absorbed + overkill" in note and "unmitigatedAmount" in note
    assert res["table"]["data"]["entries"][0]["events"][0] == HIT  # fields untouched


async def test_damage_events_label_the_hit_fields(monkeypatch):
    _install(monkeypatch, "events", {"data": [HIT], "nextPageTimestamp": None})
    res = await report_tools.get_report_events("bjXfNc92d8CPGhvB", "DamageTaken", fight_id=1)
    assert "damage_fields" in res


@pytest.mark.parametrize("data_type", ["DamageDone", "Casts"])
async def test_other_tables_carry_no_note(monkeypatch, data_type):
    _install(monkeypatch, "table", {"data": {"entries": []}})
    res = await report_tools.get_report_table("bjXfNc92d8CPGhvB", data_type, fight_id=1)
    assert "damage_fields" not in res
