"""Captured-metadata extraction, best-effort capture, and recency queries (feature 007 / US1)."""

from __future__ import annotations

import asyncio

from backend.app.db import repository as repo
from backend.app.services import known_entities as ke
from backend.app.services import raids as raids_service

# --- Pure extractors ----------------------------------------------------------


def test_players_from_ranking_tool_uses_arg_identity():
    rows = ke.players_from_tool(
        "get_character_zone_rankings",
        True,
        {"name": "Thrall", "server": "Stormrage", "region": "us"},
        {"status": "success", "name": "Thrall", "zoneRankings": {}},
    )
    assert rows == [
        {"name": "Thrall", "server": "Stormrage", "region": "US", "source": "ranking"}
    ]


def test_players_skipped_without_full_identity_or_on_failure():
    # Missing server/region ⇒ ambiguous identity ⇒ skipped.
    assert ke.players_from_tool(
        "get_character_zone_rankings", True, {"name": "Thrall"}, {"status": "success"}
    ) == []
    # Non-player tool ⇒ nothing.
    assert ke.players_from_tool("find_encounter", True, {}, {"status": "success"}) == []
    # Failed call ⇒ nothing.
    assert ke.players_from_tool(
        "get_character_zone_rankings", False,
        {"name": "T", "server": "S", "region": "US"}, None,
    ) == []
    # master_data actors are intentionally not captured (no server/region).
    assert ke.players_from_tool(
        "get_report_master_data", True, {}, {"status": "success", "actors": [{"name": "X"}]}
    ) == []


def test_encounters_from_find_keeps_ids_and_skips_name_only():
    rows = ke.encounters_from_find(
        "find_encounter",
        True,
        {
            "status": "success",
            "matches": [
                {"encounter_id": 2902, "encounter": "Ulgrax", "zone": "Nerubar", "zone_id": 38},
                {"encounter": "NameOnly", "zone": "Z"},  # no id ⇒ skipped
                {"encounter_id": 0, "encounter": "Zero"},  # id 0 ⇒ skipped
            ],
        },
    )
    assert rows == [
        {"encounter_id": 2902, "encounter_name": "Ulgrax", "zone_id": 38, "zone_name": "Nerubar"}
    ]


def test_encounters_from_find_ignores_other_tools_and_failures():
    assert ke.encounters_from_find("find_encounter", False, {"status": "success"}) == []
    assert ke.encounters_from_find("get_report_fights", True, {"status": "success"}) == []
    assert ke.encounters_from_find("find_encounter", True, {"status": "error"}) == []


# --- Best-effort capture into the store ---------------------------------------


async def test_capture_players_upserts_and_dedups(session, tenant_id):
    args = {"name": "Thrall", "server": "Stormrage", "region": "US"}
    res = {"status": "success", "name": "Thrall"}
    n1 = await ke.capture_players_from_tool(
        session, tenant_id=tenant_id, name="get_character_zone_rankings",
        ok=True, args=args, result=res, conversation_id=None,
    )
    await asyncio.sleep(0.01)
    n2 = await ke.capture_players_from_tool(
        session, tenant_id=tenant_id, name="get_character_encounter_rankings",
        ok=True, args=args, result=res, conversation_id=None,
    )
    assert n1 == 1 and n2 == 1
    players = await repo.list_recent_known_players(session, tenant_id=tenant_id)
    assert len(players) == 1  # deduped by (name, server, region)
    assert players[0].name == "Thrall"


async def test_capture_encounters_upserts_and_dedups(session, tenant_id):
    res = {"status": "success", "matches": [{"encounter_id": 2902, "encounter": "Ulgrax", "zone": "Nerubar", "zone_id": 38}]}
    n1 = await ke.capture_encounters_from_tool(
        session, tenant_id=tenant_id, name="find_encounter", ok=True,
        args={"query": "ulgrax"}, result=res, conversation_id=None,
    )
    n2 = await ke.capture_encounters_from_tool(
        session, tenant_id=tenant_id, name="find_encounter", ok=True,
        args={"query": "ulgrax"}, result=res, conversation_id=None,
    )
    assert n1 == 1 and n2 == 1
    encounters = await repo.list_recent_known_encounters(session, tenant_id=tenant_id)
    assert len(encounters) == 1
    assert encounters[0].encounter_id == 2902
    assert encounters[0].zone_name == "Nerubar"


async def test_capture_is_best_effort_on_bad_input(session, tenant_id):
    # A nonsense record must neither raise nor write anything.
    n = await ke.capture_players_from_tool(
        session, tenant_id=tenant_id, name="get_character_zone_rankings",
        ok=True, args={}, result={"status": "success"}, conversation_id=None,
    )
    assert n == 0
    assert await repo.list_recent_known_players(session, tenant_id=tenant_id) == []


# --- Per-tenant isolation + recency -------------------------------------------


async def test_recency_queries_are_tenant_isolated(session, tenant_id, other_tenant_id):
    await repo.upsert_known_player(
        session, tenant_id=tenant_id, name="Mine", server="S", region="US"
    )
    await repo.upsert_known_player(
        session, tenant_id=other_tenant_id, name="Theirs", server="S", region="US"
    )
    await repo.upsert_known_encounter(
        session, tenant_id=tenant_id, encounter_id=1, encounter_name="A"
    )
    await session.commit()

    mine = await repo.list_recent_known_players(session, tenant_id=tenant_id)
    theirs = await repo.list_recent_known_players(session, tenant_id=other_tenant_id)
    assert [p.name for p in mine] == ["Mine"]
    assert [p.name for p in theirs] == ["Theirs"]
    assert await repo.list_recent_known_encounters(session, tenant_id=other_tenant_id) == []


async def test_recent_players_ordered_and_capped(session, tenant_id):
    for i in range(20):
        await repo.upsert_known_player(
            session, tenant_id=tenant_id, name=f"P{i}", server="S", region="US"
        )
        await asyncio.sleep(0.001)
    players = await repo.list_recent_known_players(session, tenant_id=tenant_id, limit=15)
    assert len(players) == 15  # bounded
    assert players[0].name == "P19"  # most-recent first


async def test_known_guilds_derived_from_tracked_raids(session, tenant_id):
    await repo.upsert_tracked_raid(
        session, tenant_id=tenant_id, report_code="A", label="A", guild="Alpha"
    )
    await asyncio.sleep(0.01)
    await repo.upsert_tracked_raid(
        session, tenant_id=tenant_id, report_code="B", label="B", guild="Beta"
    )
    await repo.upsert_tracked_raid(
        session, tenant_id=tenant_id, report_code="C", label="C", guild=None
    )
    guilds = await repo.list_recent_known_guilds(session, tenant_id=tenant_id)
    assert set(guilds) == {"Alpha", "Beta"}  # distinct, non-null


# --- SC-002: a repeat known-raid reference issues zero report-metadata lookups --


async def test_repeat_known_raid_does_no_metadata_lookup(monkeypatch, session, tenant_id):
    calls = {"n": 0}

    def fake_meta(code):
        calls["n"] += 1
        return {"status": "success", "guild": "G", "zone": "Z", "start_time_ms": 1_759_000_000_000}

    monkeypatch.setattr(raids_service, "get_report_metadata", fake_meta)

    async def capture():
        return await raids_service.capture_raid_from_tool(
            session, tenant_id=tenant_id, name="get_report_graph", ok=True,
            args={"report_code": "SC2"}, conversation_id=None,
        )

    await capture()
    assert calls["n"] == 1  # cold path resolves the label once
    await capture()
    assert calls["n"] == 1  # repeat reference: ZERO additional report-metadata lookups
