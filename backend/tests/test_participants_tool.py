"""get_report_participants (feature 030, sc-206) over faked WCL responses.

The ``playerDetails`` payloads are Inferred from the shape ``guide_pipeline/datasheet.py``
parses (``data.playerDetails.{tanks,healers,dps}``, entries with ``name``, ``type``,
``server`` and ``specs``); the owner checks a real report at review.
"""

from __future__ import annotations

import json

import pytest

from backend.tests import wcl_fakes
from wcl_agent.tools.participants import get_report_participants

CLASSES = ["Warrior", "Paladin", "Shaman", "Mage", "Priest", "Rogue", "Druid", "Hunter"]
DPS_SPECS = {"Warrior": "Arms", "Paladin": "Retribution", "Shaman": "Elemental", "Mage": "Fire",
             "Priest": "Shadow", "Rogue": "Outlaw", "Druid": "Balance", "Hunter": "Marksmanship"}


def player(name, cls, spec, server="Draenor", count=10):
    entry = {"name": name, "guid": 1, "type": cls, "specs": [{"spec": spec, "count": count}]}
    if server is not None:
        entry["server"] = server
    return entry


def payload(tanks=(), healers=(), dps=(), region="eu"):
    return {"data": {"reportData": {"report": {
        "region": {"slug": region},
        "playerDetails": {"data": {"playerDetails": {
            "tanks": list(tanks), "healers": list(healers), "dps": list(dps)}}},
    }}}}


def mplus():
    return payload(
        tanks=[player("Kazrok", "Warrior", "Protection")],
        healers=[player("Brightmane", "Paladin", "Holy", "Tarren Mill")],
        dps=[player("Zulkar", "Shaman", "Elemental", "Silvermoon"),
             player("Mira", "Mage", "Fire"), player("Tess", "Rogue", "Outlaw")],
    )


def raid():
    dps = [player(f"{CLASSES[i % 8]}{i}", CLASSES[i % 8], DPS_SPECS[CLASSES[i % 8]]) for i in range(34)]
    dps += [{"name": "Wolf", "type": "Pet", "specs": []}, {"name": "Boss", "type": "NPC"}]
    return payload(
        tanks=[player("Tank1", "Warrior", "Protection"), player("Tank2", "Druid", "Guardian")],
        healers=[player(f"Heal{i}", "Priest", "Holy" if i % 2 else "Discipline") for i in range(4)],
        dps=dps,
    )


async def run(monkeypatch, result, fight_id=0, code="abc"):
    fake = wcl_fakes.install(monkeypatch, lambda q, v: result)
    return await get_report_participants(code, fight_id), fake


async def test_mplus_rows_sorted_and_compact(monkeypatch):
    out, fake = await run(monkeypatch, mplus(), fight_id=7)
    assert out["status"] == "success" and out["region"] == "eu"
    rows = out["participants"]
    assert [r["role"] for r in rows] == ["tank", "healer", "dps", "dps", "dps"]
    assert rows[0] == {"name": "Kazrok", "realm": "Draenor", "region": "eu",
                       "class": "Warrior", "spec": "Protection", "role": "tank"}
    assert all(len(json.dumps(r)) <= 120 for r in rows)
    assert len(json.dumps(out)) <= 1500
    assert fake.calls[0][1]["fightIDs"] == [7]
    assert out["provenance"]["report_code"] == "abc"


async def test_raid_excludes_pets_and_npcs_within_budget(monkeypatch):
    out, fake = await run(monkeypatch, raid())
    rows = out["participants"]
    assert len(rows) == 40
    assert {"Wolf", "Boss"}.isdisjoint(r["name"] for r in rows)
    assert all(len(json.dumps(r)) <= 120 for r in rows)
    assert len(json.dumps(out)) <= 6000
    assert "_truncated" not in json.dumps(out)
    assert fake.calls[0][1]["fightIDs"] is None


async def test_missing_realm_is_null_and_row_kept(monkeypatch):
    res = payload(dps=[player("Nomad", "Mage", "Frost", server=None)])
    out, _ = await run(monkeypatch, res)
    assert out["participants"][0]["realm"] is None
    assert out["participants"][0]["name"] == "Nomad"


async def test_missing_keys_tolerated(monkeypatch):
    res = payload(dps=[{"name": "Bare", "type": "Mage"}, {"type": "Mage"}], region=None)
    res["data"]["reportData"]["report"]["region"] = None
    out, _ = await run(monkeypatch, res)
    row = out["participants"][0]
    assert (row["name"], row["realm"], row["region"], row["spec"]) == ("Bare", None, None, None)
    assert row["role"] == "dps"
    assert len(out["participants"]) == 1


async def test_spec_swapper_is_one_row_with_most_played_spec(monkeypatch):
    res = payload(
        healers=[player("Flex", "Priest", "Holy", count=3)],
        dps=[player("Flex", "Priest", "Shadow", count=9)],
    )
    out, _ = await run(monkeypatch, res)
    assert len(out["participants"]) == 1
    row = out["participants"][0]
    assert (row["spec"], row["role"]) == ("Shadow", "dps")


async def test_role_falls_back_to_group_without_spec(monkeypatch):
    res = payload(healers=[{"name": "NoSpec", "type": "Priest", "server": "Draenor"}])
    out, _ = await run(monkeypatch, res)
    assert out["participants"][0]["role"] == "healer"


@pytest.mark.parametrize("result", [
    {"data": {"reportData": {"report": None}}},
    payload(dps=[{"name": "Wolf", "type": "Pet"}]),
])
async def test_empty_or_inaccessible_report_is_an_error(monkeypatch, result):
    out, _ = await run(monkeypatch, result)
    assert out["status"] == "error" and out["error_message"]


async def test_request_failure_is_an_error(monkeypatch):
    def boom(q, v):
        raise RuntimeError("down")

    wcl_fakes.install(monkeypatch, boom)
    out = await get_report_participants("abc")
    assert out["status"] == "error" and "down" in out["error_message"]


async def test_filters_apply_to_rows(monkeypatch):
    rows = (await run(monkeypatch, mplus()))[0]["participants"]
    no_shaman = [r for r in rows if r["class"] != "Shaman"]
    healers = [r for r in rows if r["role"] == "healer"]
    assert [r["name"] for r in no_shaman] == ["Kazrok", "Brightmane", "Mira", "Tess"]
    assert [r["name"] for r in healers] == ["Brightmane"]


def test_participants_lookup_tracks_the_raid():
    from backend.app.services.raids import REPORT_SCOPED_TOOLS

    assert "get_report_participants" in REPORT_SCOPED_TOOLS
