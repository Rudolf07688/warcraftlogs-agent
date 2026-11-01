"""The WCL chunker (feature 043, sc-112 AC1/AC2): readable text, bounded chunks, filters from the
variables and the response, nothing for shapes it doesn't know. Bodies follow the fields of
``REPORT_SUMMARY`` and the WCL ``table`` JSON."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.app.kb.wcl_chunker import (
    MAX_PLAYERS,
    TOP_N,
    FetchSource,
    FightContext,
    chunk_fetch,
    infer_metric,
    needed_fights,
    source_from_query,
)
from backend.app.kb.chunks import PlayerRef
from wcl_agent.client.queries import REPORT_SUMMARY

TABLE_Q = (
    "query ReportQ($code: String!, $fightIDs: [Int], $sourceID: Int, $abilityID: Float) { reportData "
    "{ report(code: $code) { table(dataType: DamageDone, hostilityType: Friendlies, fightIDs: $fightIDs, "
    "sourceID: $sourceID, abilityID: $abilityID) } } }"
)
CODE = "BKNtypgnhrxXvj84"
CLASSES = [("Warrior", "Arms"), ("Mage", "Fire"), ("Priest", "Holy"), ("Rogue", "Outlaw")]


def summary_report(code: str = CODE) -> dict:
    return {
        "code": code, "visibility": "public", "title": "Liberation raid", "startTime": 1_760_000_000_000,
        "endTime": 1_760_010_000_000, "zone": {"id": 44, "name": "Liberation of Undermine"},
        "guild": {"name": "Rune Ward"},
        "masterData": {"actors": [
            {"id": 1, "name": "Vagxsu", "subType": "Warrior"}, {"id": 2, "name": "Lumi", "subType": "Priest"},
        ]},
        "fights": [
            {"id": 32, "name": "Ula'tek", "encounterID": 3012, "difficulty": 4, "kill": True,
             "averageItemLevel": 680.4, "size": 20, "friendlyPlayers": [1, 2], "startTime": 600_000},
            {"id": 33, "name": "Trash", "encounterID": 0, "difficulty": 4, "kill": None,
             "friendlyPlayers": [1], "startTime": 700_000},
        ],
    }


def entries(n: int) -> list[dict]:
    return [
        {"name": f"Player{i}", "id": 100 + i, "type": CLASSES[i % 4][0], "icon": "-".join(CLASSES[i % 4]),
         "total": 1_000_000 * (n - i)}
        for i in range(n)
    ]


def table_source(data: dict, *, fight: int | None = 32, query: str = TABLE_Q, source_id: int | None = None) -> FetchSource:
    variables = {"code": CODE, "fightIDs": [fight] if fight else None, "sourceID": source_id, "abilityID": None}
    body = {"data": {"reportData": {"report": {"table": {"data": data}}}}}
    return source_from_query("key", query, variables, [CODE], body)


CONTEXT = {32: FightContext(name="Ula'tek", encounter_id=3012, difficulty=4, kill=True, zone_id=44,
                            start_time=datetime(2026, 10, 9, tzinfo=UTC), guild="Rune Ward",
                            players=(PlayerRef("Vagxsu", "vagxsu", "Warrior", "Arms", 1),))}


def test_summary_gives_one_chunk_per_boss_fight_with_filters_and_roster():
    source = FetchSource("key", (CODE,), {"code": CODE}, {"data": {"reportData": {"report": summary_report()}}})
    [chunk] = chunk_fetch(source)  # the trash fight (encounterID 0) has no chunk
    assert chunk.chunk_key == f"fight:{CODE}:32" and chunk.label == "fight 32 summary"
    assert chunk.text.startswith(f"Report {CODE} (Liberation raid, Liberation of Undermine, guild Rune Ward), fight 32: Heroic Ula'tek, kill")
    assert "Roster: Vagxsu (Warrior), Lumi (Priest)." in chunk.text
    assert (chunk.report_code, chunk.zone_id, chunk.encounter_id, chunk.difficulty, chunk.fight_id, chunk.kill) == (
        CODE, 44, 3012, 4, 32, True,
    )
    assert chunk.start_time == datetime.fromtimestamp(1_760_000_600, UTC)
    assert chunk.guild == "Rune Ward"
    assert [p.as_json() for p in chunk.players] == [
        {"name": "Vagxsu", "key": "vagxsu", "class": "Warrior", "id": 1},
        {"name": "Lumi", "key": "lumi", "class": "Priest", "id": 2},
    ]


def test_batch_summary_uses_only_report_objects_whose_code_was_resolved():
    body = {"data": {"reportData": {"r0": summary_report("AAA"), "r1": summary_report("BBB")}}}
    source = FetchSource("key", ("AAA",), {"c0": "AAA", "c1": "BBB"}, body)  # BBB not exact-resolved
    assert [c.report_code for c in chunk_fetch(source)] == ["AAA"]


def test_table_chunk_lists_the_top_entries_with_the_fight_context():
    drafts = chunk_fetch(table_source({"entries": entries(5), "totalTime": 535_000}), CONTEXT)
    [chunk] = drafts  # 5 players: no per-player chunks
    assert chunk.chunk_key == "table" and chunk.label == "fight 32 Damage done"
    assert chunk.text == (
        f"Report {CODE}, fight 32 (Heroic Ula'tek, kill), 535 s. Damage done: Player0 (Arms Warrior) 5.0M; "
        "Player1 (Fire Mage) 4.0M; Player2 (Holy Priest) 3.0M; Player3 (Outlaw Rogue) 2.0M; Player4 (Arms Warrior) 1.0M."
    )
    assert (chunk.encounter_id, chunk.difficulty, chunk.kill, chunk.zone_id, chunk.guild) == (3012, 4, True, 44, "Rune Ward")
    assert chunk.extra == {"metric": "DamageDone", "hostility": "Friendlies", "fight_name": "Ula'tek"}
    assert [p.key for p in chunk.players] == [f"player{i}" for i in range(5)]


def test_large_table_adds_one_bounded_chunk_per_player():
    drafts = chunk_fetch(table_source({"entries": entries(60)}), CONTEXT)
    table, players = drafts[0], drafts[1:]
    assert f"(top {TOP_N} of 60)" in table.text and table.text.count(";") == TOP_N - 1
    assert len(players) == MAX_PLAYERS and len(table.players) == MAX_PLAYERS
    first = players[0]
    assert first.chunk_key == "player:player0" and first.label == "Player0, fight 32 Damage done"
    assert "Player0 (Arms Warrior) 60.0M, rank 1 of 60" in first.text
    assert (first.class_name, first.spec, first.role, first.fight_id) == ("Warrior", "Arms", "dps", 32)
    assert all(len(d.text) <= 2000 for d in drafts)


def test_a_table_without_context_still_chunks_with_the_ids_it_has():
    [chunk] = chunk_fetch(table_source({"entries": entries(2)}))
    assert chunk.text.startswith(f"Report {CODE}, fight 32. Damage done:")
    assert (chunk.fight_id, chunk.encounter_id, chunk.report_code) == (32, None, CODE)


def test_whole_report_table_has_no_fight_id():
    [chunk] = chunk_fetch(table_source({"entries": entries(2)}, fight=None))
    assert chunk.fight_id is None and chunk.label == "all fights Damage done"
    assert needed_fights(table_source({"entries": []}, fight=None)) == (CODE, [])
    assert needed_fights(table_source({"entries": []})) == (CODE, [32])


def test_source_filtered_table_lists_that_players_abilities():
    abilities = [{"name": "Mortal Strike", "total": 40_100_000}, {"name": "Overpower", "total": 20_000_000}]
    [chunk] = chunk_fetch(table_source({"entries": abilities}, source_id=1), CONTEXT)
    assert chunk.chunk_key == "source:1" and chunk.label == "Vagxsu, fight 32 Damage done"
    assert "Damage done by ability, Vagxsu (Arms Warrior): Mortal Strike 40.1M; Overpower 20.0M." in chunk.text
    assert chunk.players[0].key == "vagxsu" and chunk.extra["source_id"] == 1


def test_deaths_summary_and_aura_tables():
    deaths = {"entries": [
        {"name": "Lumi", "type": "Priest", "icon": "Priest-Holy", "deathTime": 151_000, "ability": {"name": "Spray"}},
    ]}
    [d] = chunk_fetch(table_source(deaths, query=TABLE_Q.replace("DamageDone", "Deaths")))
    assert "Deaths: Lumi (Holy Priest) at 2:31 to Spray." in d.text and d.players[0].key == "lumi"
    summary = {"playerDetails": {"tanks": [], "healers": [{"name": "Lumi", "type": "Priest", "specs": [{"spec": "Holy"}]}],
                                 "dps": [{"name": "Vagxsu", "type": "Warrior", "specs": [{"spec": "Arms"}]}]},
               "composition": [], "damageDone": [{"name": "Vagxsu", "total": 9_000_000}], "deathEvents": [{"name": "Lumi"}]}
    [s] = chunk_fetch(table_source(summary, query=TABLE_Q.replace("DamageDone", "Summary")))
    assert "Fight overview: composition 0 tanks, 1 healers, 1 dps. top damage done: Vagxsu 9.0M. 1 deaths: Lumi." in s.text
    assert {p.spec for p in s.players} == {"Holy", "Arms"}
    auras = {"auras": [{"name": "Bloodlust", "totalUptime": 40_000}], "totalTime": 400_000}
    [a] = chunk_fetch(table_source(auras, query=TABLE_Q.replace("DamageDone", "Buffs")))
    assert "Buff uptime: Bloodlust 10%." in a.text


def test_enemy_entries_are_not_players():
    q = TABLE_Q.replace("Friendlies", "Enemies").replace("DamageDone", "DamageTaken")
    [chunk] = chunk_fetch(table_source({"entries": [{"name": "Ula'tek", "type": "Boss", "total": 5}]}, query=q))
    assert chunk.players == () and "Damage taken (enemies)" in chunk.text


def test_unknown_shapes_and_fetches_without_report_codes_give_nothing():
    events = {"data": {"reportData": {"report": {"events": {"data": [{"type": "cast"}]}}}}}
    assert chunk_fetch(FetchSource("k", (CODE,), {"code": CODE}, events)) == []
    rankings = {"data": {"worldData": {"encounter": {"characterRankings": {}}}}}
    assert chunk_fetch(FetchSource("k", (CODE,), {}, rankings)) == []
    summary = {"data": {"reportData": {"report": summary_report()}}}
    assert chunk_fetch(FetchSource("k", (), {}, summary)) == []


def test_stored_tables_infer_the_metric_or_are_skipped():
    assert infer_metric({"playerDetails": {}, "composition": []}) == "Summary"
    assert infer_metric({"entries": [{"name": "x", "deathTime": 1}]}) == "Deaths"
    assert infer_metric({"auras": []}) == "Auras"
    assert infer_metric({"entries": [{"name": "x", "total": 1}]}) is None
    stored = FetchSource("k", (CODE,), {"code": CODE, "fightIDs": [32]},
                         {"data": {"reportData": {"report": {"table": {"data": {"entries": entries(3)}}}}}})
    assert chunk_fetch(stored) == []  # damage, healing or casts: the body doesn't say


def test_summary_query_text_is_not_needed_for_summaries():
    source = source_from_query("k", REPORT_SUMMARY, {"code": CODE}, [CODE],
                               {"data": {"reportData": {"report": summary_report()}}})
    assert source.metric is None and len(chunk_fetch(source)) == 1
