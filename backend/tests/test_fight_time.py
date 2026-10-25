"""Shared fight-time helpers (feature 009, US2/US4 — wcl_agent/tools/fight_time.py)."""

from __future__ import annotations

import pytest

from backend.tests.wcl_fakes import install
from wcl_agent.tools.fight_time import (
    PlayerResolutionError,
    dead_windows,
    eligible_seconds,
    fetch_dead_windows,
    intermission_windows,
    merge_intervals,
    resolve_player,
)

ACTORS = [
    {"id": 7, "name": "Hrslkks", "server": "Azshara", "subType": "Mage"},
    {"id": 8, "name": "Other", "server": "Azshara", "subType": "Warrior"},
    {"id": 9, "name": "Hrslkks", "server": "Elsewhere", "subType": "Mage"},
    {"id": 10, "name": "Absent", "server": "Azshara", "subType": "Druid"},
]


def test_merge_intervals_overlap_and_adjacency():
    assert merge_intervals([(0, 10), (5, 15), (15, 20), (30, 40), (35, 36), (50, 50)]) == [
        (0.0, 20.0),
        (30.0, 40.0),
    ]
    assert merge_intervals([]) == []


def test_dead_windows_until_next_cast_or_fight_end():
    assert dead_windows([100.0, 500.0], [200.0, None], 900.0) == [(100.0, 200.0), (500.0, 900.0)]
    # next cast after the fight end is clipped
    assert dead_windows([100.0], [5000.0], 900.0) == [(100.0, 900.0)]


def test_eligible_seconds_merges_and_clips():
    # 300 s fight; dead 60–120 s and 100–150 s (overlap) + intermission 140–200 s ⇒ 140 s excluded
    dead = [(60_000, 120_000), (100_000, 150_000)]
    inter = [(140_000, 200_000)]
    assert eligible_seconds(0, 300_000, dead, inter) == 160.0
    # windows outside the fight are clipped away
    assert eligible_seconds(1000, 301_000, [(0, 1000), (301_000, 400_000)]) == 300.0
    assert eligible_seconds(0, 10_000, [(0, 50_000)]) == 0.0


def test_intermission_windows_from_transitions():
    transitions = [
        {"id": 1, "startTime": 0},
        {"id": 2, "startTime": 100_000},  # intermission
        {"id": 3, "startTime": 160_000},
        {"id": 2, "startTime": 250_000},  # intermission until fight end
    ]
    assert intermission_windows(0, 300_000, transitions, {2}) == [
        (100_000.0, 160_000.0),
        (250_000.0, 300_000.0),
    ]
    assert intermission_windows(0, 300_000, transitions, set()) == []
    assert intermission_windows(0, 300_000, None, {2}) == []


# --- resolve_player -----------------------------------------------------------------


def test_resolve_player_by_unique_name():
    r = resolve_player(ACTORS, [7, 8], "hrslkks")
    assert (r.source_id, r.name, r.server, r.class_name) == (7, "Hrslkks", "Azshara", "Mage")


def test_resolve_player_source_id_wins():
    r = resolve_player(ACTORS, [7, 8, 9], "Hrslkks", source_id=9)
    assert r.source_id == 9 and r.server == "Elsewhere"


def test_resolve_player_unknown_name_lists_players_present():
    with pytest.raises(PlayerResolutionError) as exc:
        resolve_player(ACTORS, [7, 8], "Absent")  # in the report, not this fight
    res = exc.value.result
    assert res["status"] == "error"
    assert res["players_present"] == ["Hrslkks", "Other"]


def test_resolve_player_ambiguous_name_returns_candidates():
    with pytest.raises(PlayerResolutionError) as exc:
        resolve_player(ACTORS, [7, 8, 9], "Hrslkks")
    res = exc.value.result
    assert res["status"] == "error"
    assert "source_id" in res["error_message"]
    assert res["candidates"] == [
        {"source_id": 7, "name": "Hrslkks", "server": "Azshara", "class": "Mage"},
        {"source_id": 9, "name": "Hrslkks", "server": "Elsewhere", "class": "Mage"},
    ]


def test_resolve_player_bad_source_id():
    with pytest.raises(PlayerResolutionError) as exc:
        resolve_player(ACTORS, [7, 8], "Hrslkks", source_id=10)
    assert "source_id 10" in exc.value.result["error_message"]


# --- fetch_dead_windows (faked WCL) ---------------------------------------------------


async def test_fetch_dead_windows_uses_first_cast_after_each_death(monkeypatch):
    def responder(query, variables):
        if "dataType: Deaths" in query:
            return {"data": {"reportData": {"report": {"table": {"data": {"entries": [
                {"name": "Hrslkks", "id": 7, "timestamp": 100_000},
                {"name": "Hrslkks", "id": 7, "timestamp": 100_400},  # duplicate event
                {"name": "Hrslkks", "id": 7, "timestamp": 250_000},
            ]}}}}}}
        if "dataType: Casts" in query:
            start = variables["startTime"]
            data = [{"timestamp": 130_000}] if start < 200_000 else []
            return {"data": {"reportData": {"report": {"events": {"data": data, "nextPageTimestamp": None}}}}}
        raise AssertionError(query)

    fake = install(monkeypatch, responder)
    windows = await fetch_dead_windows("ABC", 9, 7, 300_000)
    assert windows == [(100_000.0, 130_000.0), (250_000.0, 300_000.0)]
    assert fake.count("dataType: Deaths") == 1
    assert fake.count("dataType: Casts") == 2  # one per (deduplicated) death
