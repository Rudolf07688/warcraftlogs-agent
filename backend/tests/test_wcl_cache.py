"""WCL query cache: hits/misses/tiers/bypass/isolation (feature 005 / US4)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.tests.wcl_fakes import gql_response, mock_async_client
from wcl_agent.cache import (
    cache_key,
    get_cache,
    is_rate_limit,
    is_report_scoped,
    leaderboard_ttl,
    report_ttl,
    ttl_for,
)


@pytest.fixture
def counting_client():
    """A client over a mock transport that counts GraphQL posts and returns a fresh payload
    each call, so hits are detectable (feature 013: httpx replaces requests)."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return gql_response({"data": {"value": calls["n"]}})

    get_cache().clear()
    return mock_async_client(handler), calls


async def test_identical_query_hits_cache(counting_client):
    c, calls = counting_client
    q = "query { reportData { report(code: $code) { title } } }"
    first = await c.query(q, {"code": "ABC"})
    second = await c.query(q, {"code": "ABC"})
    assert calls["n"] == 1  # one network call
    assert first == second  # same payload on the hit


async def test_different_variables_miss(counting_client):
    c, calls = counting_client
    q = "query { reportData { report(code: $code) { title } } }"
    await c.query(q, {"code": "ABC"})
    await c.query(q, {"code": "XYZ"})
    assert calls["n"] == 2  # distinct keys → two calls


async def test_rate_limit_always_bypasses(counting_client):
    c, calls = counting_client
    q = "{ rateLimitData { pointsSpentThisHour } }"
    await c.query(q)
    await c.query(q)
    assert calls["n"] == 2  # never cached


def test_tier_classification():
    assert is_report_scoped("query { reportData { report(code:$c){x} } }", {}) is True
    assert is_report_scoped("q", {"code": "ABC"}) is True
    assert is_report_scoped("query { characterData { ... } }", {"name": "x"}) is False
    assert is_rate_limit("{ rateLimitData { x } }") is True
    assert ttl_for("reportData", {}) == report_ttl()
    assert ttl_for("characterRankings", {}) == leaderboard_ttl()


def test_report_ttl_is_longer_than_leaderboard():
    assert report_ttl() > leaderboard_ttl()


async def test_hits_are_isolated_copies(counting_client):
    c, calls = counting_client
    q = "query { reportData { report(code:$code){x} } }"
    first = await c.query(q, {"code": "ABC"})
    first["data"]["value"] = "MUTATED"  # caller mutates the returned dict
    second = await c.query(q, {"code": "ABC"})
    assert calls["n"] == 1  # still a hit
    assert second["data"]["value"] != "MUTATED"  # stored bytes uncorrupted


def test_cache_key_stable_and_order_independent():
    a = cache_key("q", {"b": 1, "a": 2})
    b = cache_key("q", {"a": 2, "b": 1})
    assert a == b
    assert cache_key("q", {"a": 1}) != cache_key("q", {"a": 2})


# --- PERF-009: byte bound and single-flight ------------------------------------------------


def test_cache_evicts_by_bytes():
    from wcl_agent.cache import TTLCache

    cache = TTLCache(maxsize=100, maxbytes=1000)
    cache.set("a", {"v": 1}, ttl=60, size=400)
    cache.set("b", {"v": 2}, ttl=60, size=400)
    cache.get("a")  # a is now most recently used
    cache.set("c", {"v": 3}, ttl=60, size=400)  # 1200 > 1000: evicts b (LRU)
    assert cache.get("b") is None and cache.get("a") == {"v": 1} and cache.get("c") == {"v": 3}
    assert cache.bytes == 800
    cache.set("huge", {"v": 4}, ttl=60, size=5000)  # bigger than the bound on its own
    assert cache.get("huge") is None and cache.bytes <= 1000
    cache.set("a", {"v": 5}, ttl=60, size=100)  # replacing an entry updates the byte count
    assert cache.bytes <= 1000 and cache.get("a") == {"v": 5}


async def test_concurrent_identical_queries_fetch_once():
    calls = {"n": 0}

    async def slow(request):
        calls["n"] += 1
        await asyncio.sleep(0.2)
        return gql_response({"data": {"value": 1}})

    get_cache().clear()
    c = mock_async_client(slow)
    q = "query { reportData { report(code: $code) { title } } }"
    results = await asyncio.gather(*(c.query(q, {"code": "SF"}) for _ in range(8)))
    assert calls["n"] == 1
    assert all(r == {"data": {"value": 1}} for r in results)


async def test_a_failed_fetch_fails_its_waiters_and_is_not_cached():
    calls = {"n": 0}

    async def flaky(request):
        calls["n"] += 1
        await asyncio.sleep(0.1)
        if calls["n"] == 1:
            return httpx.Response(503, content=b"down")
        return gql_response({"data": {"value": calls["n"]}})

    get_cache().clear()
    c = mock_async_client(flaky)
    q = "query { reportData { report(code: $code) { title } } }"
    results = await asyncio.gather(*(c.query(q, {"code": "FL"}) for _ in range(3)), return_exceptions=True)
    assert calls["n"] == 1 and all(isinstance(r, httpx.HTTPStatusError) for r in results)
    assert get_cache().get(cache_key(q, {"code": "FL"})) is None  # errors are never cached
    assert await c.query(q, {"code": "FL"}) == {"data": {"value": 2}}  # the next call refetches
