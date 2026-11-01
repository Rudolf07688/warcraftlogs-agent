"""Compact big report tables (046, sc-334).

A whole-raid table over the table cap comes back as the top rows of each list (name, class,
spec, total, per second, plain fields) with omitted counts, never a text preview. Driven with
the synthetic 20-player Heroic kill fixture (``fixtures/wcl_table_heroic_20.json``): no WCL call.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import pytest

from backend.app.agent_tools import stored_data_tools
from backend.app.tenancy.context import RequestIdentity
from wcl_agent.agent import INSTRUCTION
from wcl_agent.tools import report_tools
from wcl_agent.tools.report_tools import TABLE_MAX_CHARS, compact_table

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "wcl_table_heroic_20.json").read_text())
TOKEN_BUDGET = 10_000


def _tokens(obj) -> int:
    return len(json.dumps(obj, default=str)) // 4


def _serve(monkeypatch, value) -> None:
    async def field(*_args, **_kwargs):
        return value

    monkeypatch.setattr(report_tools, "_report_field", field)


@pytest.mark.parametrize("data_type", ["DamageDone", "Summary"])
async def test_a_20_player_heroic_table_result_stays_under_10k_tokens(monkeypatch, data_type):
    table = FIXTURE[data_type]
    assert _tokens(table) > 4 * TOKEN_BUDGET  # the raw table is far over budget, as live
    _serve(monkeypatch, table)
    started = time.perf_counter()
    result = await report_tools.get_report_table("Heroic20", data_type, fight_id=7)
    elapsed = time.perf_counter() - started
    assert result["status"] == "success"
    assert _tokens(result["table"]) < TOKEN_BUDGET
    assert _tokens(result) < TOKEN_BUDGET
    assert "_preview" not in json.dumps(result)
    assert result["table"]["_compact"] is True
    assert elapsed < 1.0


async def test_the_projection_is_the_top_rows_sorted_by_total(monkeypatch):
    _serve(monkeypatch, FIXTURE["DamageDone"])
    result = await report_tools.get_report_table("Heroic20", "DamageDone", fight_id=7)
    data = result["table"]["data"]
    rows = data["entries"]
    assert len(rows) == 20 and data["entries_omitted"] == 0
    totals = [r["total"] for r in rows]
    assert totals == sorted(totals, reverse=True)
    top = rows[0]
    raw = max(FIXTURE["DamageDone"]["data"]["entries"], key=lambda e: e["total"])
    assert (top["name"], top["id"], top["class"], top["spec"]) == (
        raw["name"], raw["id"], raw["type"], raw["icon"].split("-", 1)[1]
    )
    assert top["per_second"] == round(raw["total"] / (data["totalTime"] / 1000), 1)
    for dropped in ("abilities", "targets", "gear", "talents", "pets", "icon"):
        assert dropped not in top
    assert "source_id" in result["table"]["_note"]
    # every row is complete, so the result is not partial
    assert result["completeness"]["truncated"] is False


async def test_omitted_rows_are_counted_and_mark_the_result_partial(monkeypatch):
    _serve(monkeypatch, FIXTURE["Summary"])
    result = await report_tools.get_report_table("Heroic20", "Summary", fight_id=7)
    data = result["table"]["data"]
    assert len(data["damageTaken"]) == 25 and data["damageTaken_omitted"] == 5
    assert set(data["playerDetails"]) >= {"tanks", "healers", "dps", "dps_omitted"}
    assert "combatantInfo" not in data["playerDetails"]["tanks"][0]
    assert data["deathEvents"][0]["ability"] == "Reactive Toxin"  # nested {name} kept as its name
    assert result["completeness"]["truncated"] is True


async def test_a_small_table_comes_back_unchanged(monkeypatch):
    small = {"data": {"entries": [{"name": "Vagxsu", "type": "Mage", "icon": "Mage-Fire", "total": 5}], "totalTime": 1000}}
    _serve(monkeypatch, small)
    result = await report_tools.get_report_table("Small1", "DamageDone", fight_id=1)
    assert result["table"] == small


def test_auras_sort_by_uptime_and_an_unfittable_table_returns_the_note_only():
    auras = [{"name": f"Aura {i}", "guid": i, "totalUptime": i, "bands": [{"startTime": 0, "endTime": i}] * 200}
             for i in range(400)]
    out = compact_table({"data": {"auras": auras, "totalTime": 400_000}})
    assert [a["totalUptime"] for a in out["data"]["auras"]][:3] == [399, 398, 397]
    assert out["data"]["auras_omitted"] == 375 and "bands" not in out["data"]["auras"][0]

    wide = [{"name": "x" * 10_000, "total": i} for i in range(50)]  # five rows still don't fit
    out = compact_table({"data": {"entries": wide}})
    assert out == {"_compact": True, "_truncated": True, "_note": report_tools.TOO_LARGE_NOTE}
    assert len(json.dumps(out)) <= TABLE_MAX_CHARS


async def test_other_tools_keep_the_old_cap(monkeypatch):
    graph = {"series": [{"name": "x", "data": list(range(30_000))}]}
    _serve(monkeypatch, graph)
    result = await report_tools.get_report_graph("G1", "DamageDone", fight_id=1)
    assert result["graph"]["_truncated"] is True and "_preview" in result["graph"]


async def test_the_stored_table_lookup_is_compacted_too(monkeypatch):
    identity = RequestIdentity(uuid.uuid4(), uuid.uuid4(), "member", False, uuid.uuid4())
    monkeypatch.setattr(stored_data_tools, "_identity", lambda _ctx: identity)

    async def read(_identity, _query, _variables):
        return {"data": {"reportData": {"report": {"table": FIXTURE["DamageDone"]}}}}

    monkeypatch.setattr(stored_data_tools, "_read", read)
    out = await stored_data_tools.get_stored_fight_table("Heroic20", "DamageDone", fight_id=7, tool_context=None)
    assert out["status"] == "success" and out["table"]["_compact"] is True
    assert _tokens(out) < TOKEN_BUDGET


def test_the_instruction_forbids_per_player_fan_out_for_top_n():
    assert "`_compact`" in INSTRUCTION
    assert "never fetch players one by one" in INSTRUCTION
