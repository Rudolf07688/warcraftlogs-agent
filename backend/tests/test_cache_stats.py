"""Admin cache statistics: aggregation, status rules, auth and degraded modes (feature 014, US3)."""

from __future__ import annotations

import pytest

from wcl_agent import cache
from wcl_agent.cache import CacheFamily, keys, summarize

URL = "/api/admin/cache-stats"


def test_summarize_sums_days_and_derives_rates():
    out = summarize(
        {
            CacheFamily.CHAR_OVERVIEW: [
                {"hit": 50, "miss": 10, "neg_hit": 0, "load_ms_sum": 6000, "load_count": 10},
                {"hit": 30, "miss": 10, "error": 2, "lock_timeout": 1, "load_ms_sum": 4000, "load_count": 10},
            ],
            CacheFamily.CHAR_ID: [{"hit": 80, "neg_hit": 5, "miss": 15}],  # 85% < 90%
        }
    )
    overview = out["char_overview"]
    assert (overview["hits"], overview["misses"], overview["errors"], overview["lock_timeouts"]) == (80, 20, 2, 1)
    assert overview["hit_rate"] == 0.8 and overview["avg_load_ms"] == 500.0
    assert overview["status"] == "ok"  # threshold 0.60
    assert out["char_id"]["hit_rate"] == 0.85 and out["char_id"]["status"] == "review"
    assert set(out) == {f.value for f in CacheFamily}  # all seven, always
    assert out["world_zones"] == {
        "hits": 0, "misses": 0, "neg_hits": 0, "lock_timeouts": 0, "errors": 0,
        "redis_errors": 0, "hit_rate": None, "avg_load_ms": None, "status": "no_data",
    }


@pytest.mark.parametrize(
    ("family", "rate", "status"),
    [
        (CacheFamily.REPORT_PLAYER, 0.39, "review"),
        (CacheFamily.REPORT_PLAYER, 0.40, "ok"),
        (CacheFamily.CHAR_REPORTS, 0.59, "review"),
        (CacheFamily.OAUTH_TOKEN, 0.91, "ok"),
    ],
)
def test_review_thresholds_per_family(family, rate, status):
    hits = int(rate * 100)
    assert summarize({family: [{"hit": hits, "miss": 100 - hits}]})[family.value]["status"] == status


async def test_window_only_counts_recent_days(fake_redis):
    today, old = cache._window(1)[0], cache._window(10)[-1]
    await fake_redis.hset(keys.metrics(CacheFamily.CHAR_ID, today), mapping={"hit": 9, "miss": 1})
    await fake_redis.hset(keys.metrics(CacheFamily.CHAR_ID, old), mapping={"hit": 0, "miss": 50})
    stats = await cache.read_stats(7)
    assert stats["available"] is True
    assert stats["families"]["char_id"]["hits"] == 9 and stats["families"]["char_id"]["misses"] == 1
    assert (await cache.read_stats(10))["families"]["char_id"]["misses"] == 51


async def test_admin_gets_stats(as_admin, fake_redis, monkeypatch):
    import fakeredis

    async def info(self, section=None):  # fakeredis has no INFO
        return {"keyspace_hits": 91, "keyspace_misses": 9, "evicted_keys": 0, "used_memory": 40 * 1024 * 1024}

    monkeypatch.setattr(fakeredis.FakeAsyncRedis, "info", info, raising=False)
    await fake_redis.hset(keys.metrics(CacheFamily.REPORT_PLAYER, cache._window(1)[0]),
                          mapping={"hit": 95, "miss": 310, "load_ms_sum": 589000, "load_count": 310})
    resp = await as_admin.client.get(URL, params={"days": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert body["window_days"] == 7 and body["enabled"] is True and body["available"] is True
    assert body["families"]["report_player"]["status"] == "review"
    assert body["families"]["report_player"]["avg_load_ms"] == 1900.0
    assert body["redis"] == {"keyspace_hit_rate": 0.91, "evicted_keys": 0, "used_memory_mb": 40.0}


async def test_families_still_show_when_info_is_unavailable(fake_redis):
    await fake_redis.hset(keys.metrics(CacheFamily.CHAR_ID, cache._window(1)[0]), mapping={"hit": 1})
    stats = await cache.read_stats(7)  # fakeredis rejects INFO, like a locked-down managed Redis
    assert stats["available"] is True and stats["redis"] is None
    assert stats["families"]["char_id"]["hits"] == 1


async def test_non_admin_is_forbidden(as_user):
    assert (await as_user.client.get(URL)).status_code == 403


async def test_signed_out_is_unauthorized(client):
    assert (await client.get(URL)).status_code == 401


@pytest.mark.parametrize("days", [0, 36])
async def test_window_is_bounded(as_admin, days):
    assert (await as_admin.client.get(URL, params={"days": days})).status_code == 422


async def test_disabled_cache_reports_so(as_admin):
    body = (await as_admin.client.get(URL)).json()  # no REDIS_URL in tests by default
    assert body["enabled"] is False and body["available"] is False and body["redis"] is None
    assert all(f["status"] == "no_data" for f in body["families"].values())


async def test_unreachable_redis_still_answers(as_admin, monkeypatch):
    from backend.tests.test_wcl_cache import DeadRedis

    monkeypatch.setenv("REDIS_URL", "redis://nowhere:6379/0")
    monkeypatch.setattr(cache, "_make_redis", lambda url: DeadRedis())
    resp = await as_admin.client.get(URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True and body["available"] is False and body["redis"] is None
