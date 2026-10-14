"""WCL query cache: hits/misses/tiers/bypass/isolation (feature 005 / US4)."""

from __future__ import annotations

import pytest

from wcl_agent import wcl_client
from wcl_agent.cache import (
    cache_key,
    get_cache,
    is_rate_limit,
    is_report_scoped,
    leaderboard_ttl,
    report_ttl,
    ttl_for,
)


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.content = b"{}"

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture
def counting_post(monkeypatch):
    """Count network calls; return a fresh payload each call so hits are detectable."""
    calls = {"n": 0}

    def fake_post(self, url, json=None, headers=None, timeout=None):
        calls["n"] += 1
        return _FakeResp({"data": {"value": calls["n"]}})

    # PERF-003: the client posts through its pooled requests.Session.
    monkeypatch.setattr(wcl_client.requests.Session, "post", fake_post)
    get_cache().clear()
    return calls


def _client() -> wcl_client.WCLClient:
    return wcl_client.WCLClient("id", "secret", access_token="tok")


def test_identical_query_hits_cache(counting_post):
    c = _client()
    q = "query { reportData { report(code: $code) { title } } }"
    first = c.query(q, {"code": "ABC"})
    second = c.query(q, {"code": "ABC"})
    assert counting_post["n"] == 1  # one network call
    assert first == second  # same payload on the hit


def test_different_variables_miss(counting_post):
    c = _client()
    q = "query { reportData { report(code: $code) { title } } }"
    c.query(q, {"code": "ABC"})
    c.query(q, {"code": "XYZ"})
    assert counting_post["n"] == 2  # distinct keys → two calls


def test_rate_limit_always_bypasses(counting_post):
    c = _client()
    q = "{ rateLimitData { pointsSpentThisHour } }"
    c.query(q)
    c.query(q)
    assert counting_post["n"] == 2  # never cached


def test_tier_classification():
    assert is_report_scoped("query { reportData { report(code:$c){x} } }", {}) is True
    assert is_report_scoped("q", {"code": "ABC"}) is True
    assert is_report_scoped("query { characterData { ... } }", {"name": "x"}) is False
    assert is_rate_limit("{ rateLimitData { x } }") is True
    assert ttl_for("reportData", {}) == report_ttl()
    assert ttl_for("characterRankings", {}) == leaderboard_ttl()


def test_report_ttl_is_longer_than_leaderboard():
    assert report_ttl() > leaderboard_ttl()


def test_deep_copy_isolation(counting_post):
    c = _client()
    q = "query { reportData { report(code:$code){x} } }"
    first = c.query(q, {"code": "ABC"})
    first["data"]["value"] = "MUTATED"  # caller mutates the returned dict
    second = c.query(q, {"code": "ABC"})
    assert counting_post["n"] == 1  # still a hit
    assert second["data"]["value"] != "MUTATED"  # stored entry uncorrupted


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


def test_concurrent_identical_queries_fetch_once(monkeypatch):
    import threading
    import time

    from wcl_agent.threading_utils import gather_threads

    calls = {"n": 0}
    lock = threading.Lock()

    def slow_post(self, url, json=None, headers=None, timeout=None):
        with lock:
            calls["n"] += 1
        time.sleep(0.2)
        return _FakeResp({"data": {"value": 1}})

    monkeypatch.setattr(wcl_client.requests.Session, "post", slow_post)
    get_cache().clear()
    c = _client()
    q = "query { reportData { report(code: $code) { title } } }"
    results = gather_threads([lambda: c.query(q, {"code": "SF"})] * 8, max_workers=8)
    assert calls["n"] == 1
    assert all(r == {"data": {"value": 1}} for r in results)


def test_waiters_fetch_themselves_when_the_leader_fails(monkeypatch):
    import threading
    import time

    from wcl_agent.threading_utils import gather_threads

    calls = {"n": 0}
    lock = threading.Lock()

    def flaky_post(self, url, json=None, headers=None, timeout=None):
        with lock:
            calls["n"] += 1
            n = calls["n"]
        time.sleep(0.1)
        if n == 1:
            raise RuntimeError("leader failed")
        return _FakeResp({"data": {"value": n}})

    monkeypatch.setattr(wcl_client.requests.Session, "post", flaky_post)
    get_cache().clear()
    c = _client()
    q = "query { reportData { report(code: $code) { title } } }"
    results = gather_threads([lambda: c.query(q, {"code": "FL"})] * 3, max_workers=3)
    assert sum(isinstance(r, RuntimeError) for r in results) == 1  # only the leader's call failed
    assert all(not isinstance(r, Exception) for r in results if not isinstance(r, RuntimeError))
    assert get_cache().get(cache_key(q, {"code": "FL"})) is not None  # a waiter filled the cache
