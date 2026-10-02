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

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture
def counting_post(monkeypatch):
    """Count network calls; return a fresh payload each call so hits are detectable."""
    calls = {"n": 0}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["n"] += 1
        return _FakeResp({"data": {"value": calls["n"]}})

    monkeypatch.setattr(wcl_client.requests, "post", fake_post)
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
