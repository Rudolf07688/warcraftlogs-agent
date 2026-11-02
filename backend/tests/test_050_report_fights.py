"""The last boss kill and the per-boss summary of a report (050, sc-365); one difficulty map (sc-330).

The live miss (report BKNtypgnhrxXvj84): two timed Mythic+ keys open the report, so a key run
looked like a boss kill, and the fight list carries no times. ``get_report_fights`` now names the
last kill itself, by time, from the full fight list, outside the capped list. No WCL call.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.app.services import name_resolver, profile_context
from wcl_agent.agent import INSTRUCTION
from wcl_agent.cache.cache_models import FightSummary, PlayerRef, ReportSummary
from wcl_agent.game import constants
from wcl_agent.game.patch import MYTHIC_PLUS_DIFFICULTY_ID
from wcl_agent.tools import report_tools, tools
from wcl_agent.tools.report_tools import MAX_JSON_CHARS, boss_summary, last_kill

ROOT = Path(__file__).resolve().parents[2]
PLAYERS = {i: PlayerRef(name=f"Raider{i:02d}x", class_name="Mage") for i in range(1, 21)}


def _fight(id: int, start: int, encounter: int = 0, name: str = "Trash", difficulty: int | None = 4,
           kill: bool | None = None, keystone: int | None = None) -> FightSummary:
    return FightSummary(
        id=id, name=name, encounter_id=encounter, difficulty=difficulty, kill=kill, start_time_ms=start,
        keystone_level=keystone, player_ids=list(PLAYERS),
    )


def _night() -> ReportSummary:
    """A mixed night: two timed keys first, 200 trash pulls, wipes and kills on two difficulties.
    Rik'tok (fight 33) was killed BEFORE Ula'tek (fight 32) although its id is higher."""
    fights = [
        _fight(1, 0, 12_100, "Den of Nalorakk", 10, True, keystone=12),
        _fight(2, 1_000, 12_101, "Blinding Vale", 10, True, keystone=11),
        _fight(3, 10_000, 3001, "Vexie", kill=False),
        _fight(4, 11_000, 3001, "Vexie", kill=True),
        _fight(10, 20_000, 3002, "Cauldron", kill=False),
        _fight(11, 21_000, 3002, "Cauldron", kill=True),
        _fight(20, 30_000, 3001, "Vexie", 5, kill=True),
        _fight(33, 40_000, 3004, "Rik'tok", kill=True),
        _fight(32, 50_000, 3003, "Ula'tek", kill=True),
        _fight(34, 60_000, 3005, "Gallywix", kill=False),  # a wipe after the last kill
        _fight(40, 70_000, 12_102, "Den of Nalorakk", 10, True, keystone=14),  # a key after the raid
    ]
    fights += [_fight(100 + i, 5_000 + i * 300) for i in range(200)]  # trash all night
    return ReportSummary(code="Night1", title="Raid night", start_time_ms=0, end_time_ms=80_000,
                         guild_name="Rune Ward", players=PLAYERS, fights=fights)


def _serve(monkeypatch, summary: ReportSummary) -> None:
    async def load(_code):
        return summary

    monkeypatch.setattr(report_tools, "load_report_summary", load)


async def test_the_last_kill_is_the_latest_boss_kill_by_time_even_past_the_cap(monkeypatch):
    _serve(monkeypatch, _night())
    result = await report_tools.get_report_fights("Night1")
    assert result["status"] == "success"
    # the full list is over the cap: it comes back as a prefix, as on a long live night
    assert result["fights"]["_truncated"] is True
    assert len(json.dumps([f.model_dump() for f in _night().fights])) > MAX_JSON_CHARS
    assert result["last_kill"] == {
        "fight_id": 32, "name": "Ula'tek", "encounterID": 3003, "difficulty": 4, "difficulty_name": "Heroic",
    }
    assert result["completeness"]["truncated"] is True  # the list is partial; last_kill is not


async def test_the_boss_summary_covers_every_boss_and_difficulty_in_first_pull_order(monkeypatch):
    _serve(monkeypatch, _night())
    bosses = (await report_tools.get_report_fights("Night1"))["bosses"]
    rows = [(b["name"], b["difficulty_name"], b["pulls"], b["kills"], b["last_kill_fight_id"], b["last_pull_fight_id"])
            for b in bosses]
    assert rows == [
        ("Vexie", "Heroic", 2, 1, 4, 4),
        ("Cauldron", "Heroic", 2, 1, 11, 11),
        ("Vexie", "Mythic", 1, 1, 20, 20),
        ("Rik'tok", "Heroic", 1, 1, 33, 33),
        ("Ula'tek", "Heroic", 1, 1, 32, 32),
        ("Gallywix", "Heroic", 1, 0, None, 34),
    ]
    assert all(b["encounterID"] < 12_000 for b in bosses)  # no key run is a boss


def test_kills_are_ordered_by_time_not_by_fight_id():
    night = _night()
    for f in night.fights:
        if f.id == 32:
            f.start_time_ms = 39_000  # now Ula'tek died before Rik'tok
    assert last_kill(night)["fight_id"] == 33


def test_without_times_the_fight_id_orders_the_kills():
    night = _night()
    for f in night.fights:
        f.start_time_ms = None  # a summary cached before start times were fetched
    assert last_kill(night)["fight_id"] == 33


def test_key_runs_are_never_the_last_kill():
    keys_only = ReportSummary(code="K", start_time_ms=0, end_time_ms=1, fights=[
        _fight(1, 0, 12_100, "Den of Nalorakk", 10, True, keystone=12),
    ])
    assert last_kill(keys_only) is None and boss_summary(keys_only) == []


async def test_no_kill_gives_a_null_last_kill_and_still_lists_the_pulls(monkeypatch):
    wipes = ReportSummary(code="W", start_time_ms=0, end_time_ms=1, players=PLAYERS, fights=[
        _fight(1, 0), _fight(2, 100, 3001, "Vexie", kill=False), _fight(3, 200, 3001, "Vexie", kill=False),
    ])
    _serve(monkeypatch, wipes)
    result = await report_tools.get_report_fights("W")
    assert result["last_kill"] is None
    assert [(b["pulls"], b["kills"], b["last_kill_fight_id"], b["last_pull_fight_id"]) for b in result["bosses"]] == [
        (2, 0, None, 3)
    ]
    assert "keystoneLevel" not in result["fights"][1]


async def test_a_key_run_carries_its_level_in_the_fight_list(monkeypatch):
    small = ReportSummary(code="S", start_time_ms=0, end_time_ms=1, players=PLAYERS, fights=[
        _fight(1, 0, 12_100, "Den of Nalorakk", 10, True, keystone=12), _fight(2, 100, 3001, "Vexie", kill=True),
    ])
    _serve(monkeypatch, small)
    result = await report_tools.get_report_fights("S")
    assert result["fights"][0]["keystoneLevel"] == 12 and "keystoneLevel" not in result["fights"][1]
    assert result["last_kill"]["fight_id"] == 2


def test_the_instruction_and_the_tool_name_last_kill_for_last_boss_questions():
    assert '"The last kill" or "the last boss" of a report is `last_kill` from `get_report_fights`' in INSTRUCTION
    assert "Never pick it from\n  the order of the fight list" in INSTRUCTION
    assert "use ``last_kill``" in report_tools.get_report_fights.__doc__


# --- sc-330: one difficulty map --------------------------------------------------


def test_there_is_one_difficulty_map_and_every_user_imports_it():
    assert constants.DIFFICULTY_NAMES == {5: "Mythic", 4: "Heroic", 3: "Normal", 1: "LFR"}
    assert tools.DIFFICULTY_NAMES is constants.DIFFICULTY_NAMES
    assert profile_context.DIFFICULTY_NAMES is constants.DIFFICULTY_NAMES
    assert report_tools.DIFFICULTY_NAMES is constants.DIFFICULTY_NAMES
    assert name_resolver.DIFFICULTY_NAMES == {**constants.DIFFICULTY_NAMES, MYTHIC_PLUS_DIFFICULTY_ID: "Mythic+"}
    literal = re.compile(r"""\b4\s*:\s*["']Heroic["']""")
    holders = [
        path.relative_to(ROOT).as_posix()
        for package in ("wcl_agent", "backend/app")
        for path in (ROOT / package).rglob("*.py")
        if literal.search(path.read_text(encoding="utf-8"))
    ]
    assert holders == ["wcl_agent/game/constants.py"]
