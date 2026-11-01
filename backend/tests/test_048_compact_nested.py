"""Compact tables keep the rows nested in wrapper rows, and count what they leave out (048).

QA BUG-003: Interrupts and Dispels tables nest their real rows one or two levels down (a
wrapper row's ``entries``, each with the players in ``details``). Compaction used to drop those
lists without counting them, so a big Interrupts table came back as one wrapper row marked
complete. Driven with synthetic tables in the WCL shapes: no WCL call.
"""

from __future__ import annotations

import json

import pytest

from wcl_agent.tools import report_tools
from wcl_agent.tools.report_tools import TABLE_MAX_CHARS, compact_table

CLASSES = ("Mage", "Rogue", "Shaman", "Warrior")


def _player(i: int, total: int, **extra) -> dict:
    kind = CLASSES[i % len(CLASSES)]
    return {"name": f"Player{i}", "id": i, "guid": 1000 + i, "type": kind, "icon": f"{kind}-Spec", "total": total, **extra}


def interrupts_table(spells: int = 80, players: int = 20) -> dict:
    """The Interrupts shape: one wrapper row, interrupted spells in ``entries``, who in ``details``."""
    entries = [
        {
            "name": f"Shadow Bolt Volley {s}", "guid": 400_000 + s, "type": 32, "abilityIcon": "spell_shadow.jpg",
            "spellsInterrupted": s, "spellsCompleted": 2, "total": s,
            "details": [_player(p, total=(s * p) % 7 + 1) for p in range(players)],
        }
        for s in range(spells)
    ]
    wrapper = {"name": "Interrupted Abilities", "spellsInterrupted": 999, "spellsCompleted": 160, "total": 999, "entries": entries}
    return {"data": {"entries": [wrapper], "totalTime": 300_000}}


@pytest.fixture
def interrupts():
    table = interrupts_table()
    assert len(json.dumps(table)) > 3 * TABLE_MAX_CHARS  # far over the cap, as a busy raid's is
    return table


def test_an_interrupts_table_keeps_its_top_spells_and_players_and_is_marked_truncated(interrupts):
    out = compact_table(interrupts)
    assert out["_compact"] is True and len(json.dumps(out)) <= TABLE_MAX_CHARS
    [wrapper] = out["data"]["entries"]
    spells = wrapper["entries"]
    assert spells and wrapper["entries_omitted"] == 80 - len(spells)
    assert [s["spellsInterrupted"] for s in spells] == sorted((s["spellsInterrupted"] for s in spells), reverse=True)
    assert spells[0]["name"] == "Shadow Bolt Volley 79"
    top = spells[0]["details"]
    assert top and spells[0]["details_omitted"] == 20 - len(top)
    assert {"name", "id", "class", "spec", "total"} <= set(top[0])
    assert out["_truncated"] is True  # rows were left out, so the model must not treat it as complete


async def test_the_tool_result_reports_the_table_as_partial(monkeypatch, interrupts):
    async def field(*_args, **_kwargs):
        return interrupts

    monkeypatch.setattr(report_tools, "_report_field", field)
    result = await report_tools.get_report_table("Int1", "Interrupts", fight_id=3)
    assert result["status"] == "success"
    assert result["table"]["_truncated"] is True
    assert result["completeness"]["truncated"] is True


def test_nested_rows_that_all_fit_are_kept_whole_and_not_marked_truncated():
    # Over the cap only because of per-row breakdowns, which stay dropped by design (046).
    table = interrupts_table(spells=5, players=3)
    for spell in table["data"]["entries"][0]["entries"]:
        for player in spell["details"]:
            player["abilities"] = [{"name": "x" * 50, "guid": g, "total": g} for g in range(60)]
    assert len(json.dumps(table)) > TABLE_MAX_CHARS
    out = compact_table(table)
    [wrapper] = out["data"]["entries"]
    assert len(wrapper["entries"]) == 5 and wrapper["entries_omitted"] == 0
    assert all(len(s["details"]) == 3 and s["details_omitted"] == 0 for s in wrapper["entries"])
    assert "abilities" not in wrapper["entries"][0]["details"][0]
    assert out["_truncated"] is False
