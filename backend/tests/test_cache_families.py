"""The seven shared-cache families at their call sites (feature 014, US1).

A fake WCL client (``wcl_fakes.install``) counts requests while fakeredis holds the cache, so
each test shows which repeat lookups reach WCL. The token family is covered in
``test_wcl_async.py`` (it lives inside the real client).
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from backend.tests.wcl_fakes import install
from wcl_agent.game import patch
from wcl_agent.tools import report_tools
from wcl_agent.cache.cache import keys, set_refresh_actor

HOUR_MS = 3_600_000
NOW_MS = int(time.time() * 1000)
ZONES = {
    "data": {
        "worldData": {
            "zones": [
                {
                    "id": 53, "name": "Raid", "frozen": False,
                    "difficulties": [{"id": 4, "name": "Heroic"}],
                    "partitions": [{"id": 1, "name": "12.1", "default": True}],
                    "encounters": [{"id": 9, "name": "Boss"}],
                }
            ]
        }
    }
}


def summary(code: str, *, ended_hours_ago: float = 20) -> dict[str, Any]:
    end = NOW_MS - int(ended_hours_ago * HOUR_MS)
    return {
        "data": {
            "reportData": {
                "report": {
                    "title": f"T {code}", "startTime": end - 3 * HOUR_MS, "endTime": end,
                    "zone": {"id": 53, "name": "Raid"}, "guild": {"name": "G"},
                    "masterData": {"actors": [{"id": 1, "name": "Rudolf", "subType": "Mage"}]},
                    "fights": [{"id": 1, "name": "Boss", "encounterID": 9, "difficulty": 4,
                                "kill": True, "friendlyPlayers": [1]}],
                }
            }
        }
    }


def responder(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    if "worldData" in query:
        return ZONES
    if "query CharRef" in query:
        if variables["name"].lower() != "rudolf":
            return {"data": {"characterData": {"character": None}}}
        server = {"slug": variables["server"], "region": {"slug": "eu"}}
        return {"data": {"characterData": {"character": {"id": 7, "name": "Rudolf", "classID": 8, "server": server}}}}
    if "zoneRankings" in query or "encounterRankings" in query:
        field = "zoneRankings" if "zoneRankings" in query else "encounterRankings"
        return {"data": {"characterData": {"character": {"name": "Rudolf", field: {"bestPerformanceAverage": 90}}}}}
    if "query ReportSummary" in query:
        return summary(variables["code"], ended_hours_ago=0.5 if variables["code"] == "LIVE" else 20)
    if "table(" in query:
        return {"data": {"reportData": {"report": {"endTime": NOW_MS - 20 * HOUR_MS, "table": {"data": [1]}}}}}
    raise AssertionError(f"unexpected query: {query[:60]}")


@pytest.fixture
def wcl(monkeypatch, fake_redis):
    return install(monkeypatch, responder)


async def test_zone_list_is_fetched_once_for_patch_and_raid_zones(wcl):
    assert await patch.current_patch() == "12.1"
    assert await patch.raid_zone_ids() == {53}
    assert wcl.count("worldData") == 1


async def test_character_rankings_resolve_once_then_hit(wcl):
    for _ in range(2):
        res = await report_tools.get_character_zone_rankings("Rudolf ", "Area 52", "eu")
        assert res["status"] == "success" and res["zoneRankings"] == {"bestPerformanceAverage": 90}
    assert wcl.count("query CharRef") == 1
    assert wcl.count("zoneRankings") == 1
    # same character, different question: identity is reused, rankings are a new entry
    await report_tools.get_character_encounter_rankings("rudolf", "area-52", "EU", encounter_id=9)
    assert wcl.count("query CharRef") == 1 and wcl.count("encounterRankings") == 1


async def test_unknown_character_is_negatively_cached(wcl, fake_redis):
    for _ in range(2):
        res = await report_tools.get_character_zone_rankings("Rudolff", "Area 52", "EU")
        assert res["status"] == "error" and "not found" in res["error_message"]
    assert wcl.count("query CharRef") == 1
    assert wcl.count("zoneRankings") == 0
    assert 0 < await fake_redis.ttl(keys.char_id("eu", "Area 52", "Rudolff")) <= 60


async def test_fights_and_metadata_share_one_report_summary(wcl):
    fights = await report_tools.get_report_fights("ABC")
    meta = await report_tools.get_report_metadata("ABC")
    assert fights["status"] == "success" and fights["zone"] == {"id": 53, "name": "Raid"}
    assert fights["fights"][0]["players"] == ["Rudolf"] and fights["players"] == {1: {"name": "Rudolf", "class": "Mage"}}
    assert meta == {"status": "success", "title": "T ABC", "zone": "Raid", "guild": "G",
                    "start_time_ms": fights["start_time_ms"]}
    assert wcl.count("query ReportSummary") == 1


async def test_report_ttl_depends_on_whether_it_is_finished(wcl, fake_redis):
    await report_tools.get_report_fights("DONE")
    await report_tools.get_report_fights("LIVE")
    assert await fake_redis.ttl(keys.report_summary("DONE")) > 86400 - 5
    assert 0 < await fake_redis.ttl(keys.report_summary("LIVE")) <= 132  # 120 s × ≤ 1.1


async def test_only_per_player_tables_are_cached(wcl):
    for _ in range(2):
        assert (await report_tools.get_report_table("ABC", "DamageDone", source_id=3))["status"] == "success"
    assert wcl.count("table(") == 1
    for _ in range(2):
        await report_tools.get_report_table("ABC", "DamageDone")
    assert wcl.count("table(") == 3  # whole-raid tables always reach WCL


async def test_shared_entries_hold_no_user_id(wcl, fake_redis):
    set_refresh_actor("user-1234")  # the per-turn user must not leak into wcl: keys
    try:
        await report_tools.get_character_zone_rankings("Rudolf", "Area 52", "EU", force_refresh=True)
        await report_tools.get_report_fights("ABC")
    finally:
        set_refresh_actor(None)
    stored = [k.decode() async for k in fake_redis.scan_iter("wcl:*")]
    assert stored and not any("user-1234" in k for k in stored)


# --- US2 -------------------------------------------------------------------------------


async def test_redis_down_costs_at_most_one_token_request(monkeypatch):
    """The process memo keeps the token off Redis's critical path (research R5)."""
    import httpx

    from backend.tests.test_wcl_cache import DeadRedis
    from wcl_agent.cache import cache
    from wcl_agent.client import wcl_client

    monkeypatch.setenv("REDIS_URL", "redis://nowhere:6379/0")
    monkeypatch.setattr(cache, "_make_redis", lambda url: DeadRedis())
    token_posts = {"n": 0}

    async def route(request):
        if str(request.url) == wcl_client.TOKEN_URL:
            token_posts["n"] += 1
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(200, json={"data": {}})

    wcl_client._tokens.pop("down", None)
    client = wcl_client.AsyncWCLClient("down", "s", transport=httpx.MockTransport(route))
    for i in range(5):
        await client.query("query A($i: Int) { x }", {"i": i})
    assert token_posts["n"] == 1


async def test_wcl_down_returns_the_tool_error_and_caches_nothing(monkeypatch, fake_redis):
    def down(query, variables):
        raise RuntimeError("WCL unavailable")

    install(monkeypatch, down)
    res = await report_tools.get_report_fights("ABC")
    assert res["status"] == "error" and "WCL unavailable" in res["error_message"]
    assert [k async for k in fake_redis.scan_iter("wcl:v1:*")] == []


# --- US4: forced refresh ------------------------------------------------------------------


@pytest.fixture
def actor():
    from wcl_agent.cache.cache import set_refresh_actor

    def use(user_id):
        set_refresh_actor(user_id)

    yield use
    set_refresh_actor(None)


async def test_force_refresh_reloads_once_a_minute_per_user(wcl, fake_redis, actor):
    actor("user-a")
    await report_tools.get_character_zone_rankings("Rudolf", "Area 52", "EU")
    res = await report_tools.get_character_zone_rankings("Rudolf", "Area 52", "EU", force_refresh=True)
    assert res["refresh"] == "done" and wcl.count("zoneRankings") == 2
    res = await report_tools.get_character_zone_rankings("Rudolf", "Area 52", "EU", force_refresh=True)
    assert res["refresh"] == "skipped_recent" and wcl.count("zoneRankings") == 2  # served cached
    assert res["zoneRankings"] == {"bestPerformanceAverage": 90}

    actor("user-b")  # another user may refresh straight away
    res = await report_tools.get_character_zone_rankings("Rudolf", "Area 52", "EU", force_refresh=True)
    assert res["refresh"] == "done" and wcl.count("zoneRankings") == 3

    refresh_keys = [k.decode() async for k in fake_redis.scan_iter("chat:refresh:*")]
    assert sorted(refresh_keys) == ["chat:refresh:user-a:7", "chat:refresh:user-b:7"]
    assert not [k async for k in fake_redis.scan_iter("wcl:*user-*")]


async def test_plain_calls_carry_no_refresh_field(wcl):
    res = await report_tools.get_character_encounter_rankings("Rudolf", "Area 52", "EU", encounter_id=9)
    assert "refresh" not in res


async def test_refresh_is_allowed_when_redis_is_down(monkeypatch):
    from backend.tests.test_wcl_cache import DeadRedis
    from wcl_agent.cache import cache

    monkeypatch.setenv("REDIS_URL", "redis://nowhere:6379/0")
    monkeypatch.setattr(cache, "_make_redis", lambda url: DeadRedis())
    assert await cache.try_claim_refresh("user-a", 7) is True
