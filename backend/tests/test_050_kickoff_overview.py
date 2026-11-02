"""A cheaper recent-raid kickoff (050, sc-358).

The kickoff answer request carried one compact Summary table per boss, each repeating the roster
(composition, playerDetails) and 25 rows per list, and every chat request carried the kickoff
playbook. Now the kickoff asks for the slim overview view, and only the kickoff turn's
instruction holds the playbook. Driven with the synthetic 20-player Heroic fixture; no WCL call.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from google.genai import types

from backend.app.api.raids import kickoff_prompt_for
from wcl_agent.agent import INSTRUCTION, RAID_KICKOFF_OPENING, build_instruction
from wcl_agent.cache.cache_models import FightSummary, PlayerRef, ReportSummary
from wcl_agent.tools import report_tools
from wcl_agent.tools.report_tools import OVERVIEW_TOP_N, compact_table

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "wcl_table_heroic_20.json").read_text())
SUMMARY = FIXTURE["Summary"]
BOSSES = 8  # one raid tier
SAVING_TOKENS = 15_000


def _ctx(text: str) -> SimpleNamespace:
    """The ADK ReadonlyContext surface ``build_instruction`` reads."""
    return SimpleNamespace(user_content=types.Content(role="user", parts=[types.Part(text=text)]))


def _serve(monkeypatch, table, seen: list | None = None) -> None:
    async def field(code, field_call, var_decls, variables, name):
        if seen is not None:
            seen.append((code, field_call, var_decls, variables, name))
        return table

    monkeypatch.setattr(report_tools, "_report_field", field)


def _chars(obj) -> int:
    return len(json.dumps(obj, default=str))


async def test_the_overview_is_the_top_10_rows_without_the_roster(monkeypatch):
    _serve(monkeypatch, SUMMARY)
    result = await report_tools.get_report_table("Heroic20", "Summary", fight_id=7, overview=True)
    table = result["table"]
    assert table["_overview"] is True and "_compact" not in table
    data = table["data"]
    assert "composition" not in data and "playerDetails" not in data
    lists = {k: v for k, v in data.items() if isinstance(v, list)}
    assert set(lists) == {"damageDone", "healingDone", "damageTaken", "deathEvents"}
    assert all(len(rows) <= OVERVIEW_TOP_N for rows in lists.values())
    totals = [r["total"] for r in data["damageDone"]]
    assert totals == sorted(totals, reverse=True)
    raw_top = max(SUMMARY["data"]["damageDone"], key=lambda e: e["total"])
    assert (data["damageDone"][0]["name"], data["damageDone"][0]["per_second"]) == (
        raw_top["name"], round(raw_top["total"] / (SUMMARY["data"]["totalTime"] / 1000), 1)
    )
    assert data["damageDone_omitted"] == 10 and table["_truncated"] is True
    assert result["completeness"]["truncated"] is True  # honest: rows were left out
    assert _chars(table) < _chars(compact_table(SUMMARY)) / 2


async def test_a_summary_request_without_overview_keeps_its_shape(monkeypatch):
    _serve(monkeypatch, SUMMARY)
    result = await report_tools.get_report_table("Heroic20", "Summary", fight_id=7)
    assert result["table"] == compact_table(SUMMARY)
    assert result["table"]["_compact"] is True and "playerDetails" in result["table"]["data"]


async def test_overview_sends_the_same_query_so_the_pre_fetch_answers_it(monkeypatch):
    seen: list = []
    _serve(monkeypatch, SUMMARY, seen)
    await report_tools.get_report_table("Heroic20", "Summary", fight_id=7)
    await report_tools.get_report_table("Heroic20", "Summary", fight_id=7, overview=True)
    assert len(seen) == 2 and seen[0] == seen[1]


def test_the_playbook_is_only_in_the_kickoff_turns_instruction():
    kickoff = build_instruction(_ctx(kickoff_prompt_for("RECENT1")))
    other = build_instruction(_ctx("Who topped damage on the last boss kill in report RECENT1?"))
    assert "<RECENT_RAID_KICKOFF>" in kickoff
    assert "<RECENT_RAID_KICKOFF>" not in other and "RECENT_RAID_KICKOFF" not in INSTRUCTION
    assert "RECENT_RAID_KICKOFF" not in build_instruction(None)
    # the playbook sits just before the time block: everything before it is the shared prefix
    head = kickoff.split("<RECENT_RAID_KICKOFF>")[0]
    assert other.startswith(head) and kickoff.index("</RECENT_RAID_KICKOFF>") < kickoff.index("<CURRENT_TIME>")


def test_the_playbook_names_the_kickoff_sequence():
    kickoff = build_instruction(_ctx(kickoff_prompt_for("RECENT1")))
    body = kickoff.split("<RECENT_RAID_KICKOFF>")[1].split("</RECENT_RAID_KICKOFF>")[0]
    assert "`get_report_fights` once" in body
    assert 'ONE parallel round of `get_report_table` with data_type "Summary" and overview true' in body
    assert "last kill, or its last pull" in body and "`last_kill_fight_id`, else `last_pull_fight_id`" in body
    assert "No per-player fetches" in body
    assert body.index("get_report_fights") < body.index("get_report_table")


def test_the_kickoff_prompt_opens_with_the_playbook_trigger_and_keeps_its_wording():
    assert kickoff_prompt_for("ABC") == (
        "Give me a bounded overview of this raid (report ABC): for each boss, "
        "one headline finding and the single biggest improvement opportunity, noting "
        "kills versus wipes. Stay at the report and per-boss level; go into cast-level "
        "detail only where a boss clearly warrants it."
    )
    assert kickoff_prompt_for("ABC").startswith(RAID_KICKOFF_OPENING)


async def test_the_kickoff_answer_request_is_at_least_15k_tokens_smaller(monkeypatch):
    """The request that writes the kickoff answer: instruction, kickoff prompt, the fight list
    and one Summary table per boss (8 bosses, the 20-player fixture for each)."""
    players = {i: PlayerRef(name=f"Raider{i:02d}", class_name="Mage") for i in range(1, 21)}
    fights = [
        FightSummary(id=n, name=f"Boss {n}", encounter_id=3000 + n, difficulty=4, kill=True,
                     start_time_ms=n * 1000, player_ids=list(players))
        for n in range(1, BOSSES + 1)
    ]
    summary = ReportSummary(code="Heroic20", start_time_ms=0, end_time_ms=1, players=players, fights=fights)

    async def load(_code):
        return summary

    monkeypatch.setattr(report_tools, "load_report_summary", load)
    _serve(monkeypatch, SUMMARY)
    prompt = kickoff_prompt_for("Heroic20")
    fight_list = await report_tools.get_report_fights("Heroic20")
    boss_ids = [b["last_kill_fight_id"] for b in fight_list["bosses"]]
    assert len(boss_ids) == BOSSES

    async def request(instruction: str, overview: bool) -> int:
        tables = [await report_tools.get_report_table("Heroic20", "Summary", fight_id=f, overview=overview)
                  for f in boss_ids]
        return (len(instruction) + len(prompt) + _chars(fight_list) + sum(_chars(t) for t in tables)) // 4

    kickoff_instruction = build_instruction(_ctx(prompt))
    before = await request(kickoff_instruction, overview=False)  # today: every instruction had the playbook
    after = await request(kickoff_instruction, overview=True)
    print(f"kickoff answer request ~tokens: before={before} after={after} saved={before - after}")
    assert before - after >= SAVING_TOKENS
    # and a non-kickoff request no longer carries the playbook
    assert len(kickoff_instruction) - len(build_instruction(None)) > 600
