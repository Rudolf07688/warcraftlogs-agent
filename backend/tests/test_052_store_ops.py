"""Raw-store probe counters per WCL operation (feature 052, sc-332).

The hit/miss/not-visible/timeout counts are kept per operation name (the query's report family)
as well as in total, and the cache-stats endpoint shows both.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.app.db import session as db_session
from backend.app.services import raw_fetch_reads
from backend.app.services.raw_fetch_reads import OWN_OPERATIONS, Breaker, read_stored_fetch
from backend.tests.test_cache_stats import URL
from wcl_agent.cache import cache
from wcl_agent.cache.cache import keys
from wcl_agent.client.wcl_client import _flight_key


def test_per_operation_counts_are_summed_over_days():
    out = cache.summarize_store_operations([
        {"store_hit@ReportSummary": 3, "store_miss@ReportSummary": 1},
        {"store_timeout@ReportQ": 2, "store_not_visible@ReportSummary": 1},
    ])
    assert out == {
        "ReportQ": {"hits": 0, "misses": 0, "not_visible": 0, "timeouts": 2, "hit_rate": None},
        "ReportSummary": {"hits": 3, "misses": 1, "not_visible": 1, "timeouts": 0, "hit_rate": 0.6},
    }
    assert cache.summarize_store_operations([]) == {}


@pytest.fixture
def no_breaker(monkeypatch):
    monkeypatch.setattr(raw_fetch_reads, "breaker", Breaker())


async def test_a_probe_is_counted_in_total_and_for_its_operation(no_breaker, monkeypatch, fake_redis):
    def bug():
        raise ValueError("a bad row")  # counted as a miss

    monkeypatch.setattr(db_session, "SessionLocal", bug)
    named = "query ReportQ($code: String!) { reportData { report(code: $code) { table } } }"
    model_written = "query " + "Mine" * 50 + ' { reportData { report(code: "Ops1") { table } } }'
    anonymous = '{ reportData { report(code: "Ops1") { table } } }'
    for query in (named, named, model_written, anonymous):
        variables = {"code": "Ops1"}
        await read_stored_fetch(_flight_key(query, variables), query, variables)
    await cache.drain_metrics()
    stats = await cache.read_stats(1)
    assert stats["store"]["misses"] == 4  # the totals are unchanged
    assert set(stats["store_by_operation"]) == {"ReportQ", "custom"}  # P7 SEC-002: a fixed set
    assert stats["store_by_operation"]["ReportQ"]["misses"] == 2
    assert stats["store_by_operation"]["custom"]["misses"] == 2


def test_nothing_is_counted_per_operation_while_the_cache_is_off(monkeypatch):
    monkeypatch.setattr(cache, "_schedule_flush", lambda: None)
    monkeypatch.delenv("REDIS_URL", raising=False)
    cache.record_store("hit", "ReportQ")
    assert (cache.STORE_OPS_METRICS, "store_hit@ReportQ") not in cache._counts
    assert cache._counts[(cache.LOCAL_METRICS, "store_hit")] == 1  # the totals still count


def test_the_allowlist_names_every_query_the_app_sends():
    root = Path(__file__).resolve().parents[2]
    names = {
        match
        for path in [*(root / "wcl_agent").rglob("*.py"), *(root / "backend" / "app").rglob("*.py")]
        for match in re.findall(r"\bquery\s+([A-Z]\w*)\s*[($\{]", path.read_text(encoding="utf-8"))
    }
    assert names and names <= OWN_OPERATIONS, names - OWN_OPERATIONS


async def test_the_endpoint_shows_both(as_admin, fake_redis):
    today = cache._window(1)[0]
    await fake_redis.hset(keys.metrics(cache.LOCAL_METRICS, today), mapping={"store_hit": 2, "store_miss": 1})
    await fake_redis.hset(keys.metrics(cache.STORE_OPS_METRICS, today),
                          mapping={"store_hit@ReportSummary": 2, "store_miss@ReportQ": 1})
    body = (await as_admin.client.get(URL, params={"days": 7})).json()
    assert body["store"]["hits"] == 2 and body["store"]["misses"] == 1
    assert body["store_by_operation"] == {
        "ReportQ": {"hits": 0, "misses": 1, "not_visible": 0, "timeouts": 0, "hit_rate": 0.0},
        "ReportSummary": {"hits": 2, "misses": 0, "not_visible": 0, "timeouts": 0, "hit_rate": 1.0},
    }


async def test_degraded_stats_have_an_empty_split(as_admin):
    assert (await as_admin.client.get(URL)).json()["store_by_operation"] == {}
