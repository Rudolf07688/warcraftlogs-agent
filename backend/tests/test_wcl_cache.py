"""Shared WCL cache: ``get_or_load`` outcomes, metrics and key builders (feature 014).

Covers contract guarantees C1–C12 in specs/014-redis-wcl-cache/contracts/cache-client.md
over fakeredis, with a counting stub loader.
"""

from __future__ import annotations

import asyncio

import pytest

from wcl_agent import cache
from wcl_agent.cache import CacheFamily, get_or_load, keys
from wcl_agent.cache_models import CharacterRef

FAM = CacheFamily.CHAR_OVERVIEW  # not memoised, so every lookup reaches the Redis layer
KEY = keys.char_zone(7, 0, "dps", 0)
REF = CharacterRef(id=7, name="Rudolf", realm="area-52", region="eu", class_id=4)


class Loader:
    """Counts calls; returns ``value`` after ``delay`` seconds, or raises ``exc``."""

    def __init__(self, value=REF, delay: float = 0.0, exc: Exception | None = None):
        self.value, self.delay, self.exc, self.calls = value, delay, exc, 0

    async def __call__(self):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc is not None:
            raise self.exc
        return self.value


async def counters(probe, family=FAM) -> dict[str, int]:
    await cache.drain_metrics()
    raw = await probe.hgetall(keys.metrics(family, cache._today()))
    return {k.decode(): int(v) for k, v in raw.items()}


async def test_miss_then_hit(fake_redis):
    load = Loader()
    assert await get_or_load(FAM, KEY, CharacterRef, load) == REF
    assert await get_or_load(FAM, KEY, CharacterRef, load) == REF
    assert load.calls == 1  # C1, C3
    c = await counters(fake_redis)
    assert c["miss"] == 1 and c["hit"] == 1 and c["load_count"] == 1
    assert "load_ms_sum" in c


async def test_ttl_has_jitter_within_bounds(fake_redis, monkeypatch):
    monkeypatch.setenv("WCL_CACHE_TTL_CHAR_OVERVIEW", "1000")
    await get_or_load(FAM, KEY, CharacterRef, Loader())
    ttl = await fake_redis.ttl(KEY)
    assert 1000 - 2 <= ttl <= 1100  # family override × U(1, 1.1)


async def test_explicit_ttl_wins(fake_redis):
    await get_or_load(FAM, KEY, CharacterRef, Loader(), ttl=50)
    assert 0 < await fake_redis.ttl(KEY) <= 55


async def test_not_found_is_negatively_cached(fake_redis):
    load = Loader(value=None)
    assert await get_or_load(FAM, KEY, CharacterRef, load) is None
    assert await get_or_load(FAM, KEY, CharacterRef, load) is None
    assert load.calls == 1  # C2
    assert 0 < await fake_redis.ttl(KEY) <= 60
    c = await counters(fake_redis)
    assert c["miss"] == 1 and c["neg_hit"] == 1


async def test_concurrent_misses_load_once(fake_redis):
    load = Loader(delay=0.15)
    results = await asyncio.gather(*(get_or_load(FAM, KEY, CharacterRef, load) for _ in range(10)))
    assert load.calls == 1  # C4 / SC-003
    assert all(r == REF for r in results)
    c = await counters(fake_redis)
    assert c["miss"] == 1 and c["hit"] == 9


async def test_lock_wait_timeout_loads_without_writing(fake_redis, monkeypatch):
    monkeypatch.setenv("WCL_CACHE_LOCK_WAIT_MS", "200")
    await fake_redis.set(keys.lock(KEY), b"1", px=10000)  # someone else holds the lock
    load = Loader()
    assert await get_or_load(FAM, KEY, CharacterRef, load) == REF
    assert load.calls == 1
    assert await fake_redis.get(KEY) is None  # the loser never writes
    assert (await counters(fake_redis))["lock_timeout"] == 1


async def test_loader_error_releases_lock_and_reraises(fake_redis):
    with pytest.raises(RuntimeError, match="wcl down"):
        await get_or_load(FAM, KEY, CharacterRef, Loader(exc=RuntimeError("wcl down")))
    assert await fake_redis.get(KEY) is None  # C5
    assert await fake_redis.get(keys.lock(KEY)) is None
    assert (await counters(fake_redis))["error"] == 1


async def test_corrupt_value_is_dropped_and_reloaded(fake_redis):
    await fake_redis.set(KEY, b"{not json")
    load = Loader()
    assert await get_or_load(FAM, KEY, CharacterRef, load) == REF
    assert load.calls == 1  # C6
    assert CharacterRef.model_validate_json(await fake_redis.get(KEY)) == REF
    c = await counters(fake_redis)
    assert c["error"] == 1 and c["miss"] == 1


async def test_wrong_shape_counts_as_corrupt(fake_redis):
    await fake_redis.set(KEY, b'{"unexpected": 1}')
    assert await get_or_load(FAM, KEY, CharacterRef, Loader()) == REF


async def test_force_refresh_reloads_and_overwrites(fake_redis):
    await get_or_load(FAM, KEY, CharacterRef, Loader())
    newer = REF.model_copy(update={"class_id": 9})
    load = Loader(value=newer)
    assert await get_or_load(FAM, KEY, CharacterRef, load, force_refresh=True) == newer
    assert load.calls == 1  # C9
    assert await get_or_load(FAM, KEY, CharacterRef, Loader()) == newer


async def test_cancelled_winner_releases_lock(fake_redis):
    task = asyncio.ensure_future(get_or_load(FAM, KEY, CharacterRef, Loader(delay=5)))
    await asyncio.sleep(0.05)
    assert await fake_redis.get(keys.lock(KEY)) is not None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await fake_redis.get(keys.lock(KEY)) is None  # C12


async def test_metrics_hash_expires_after_retention(fake_redis):
    await get_or_load(FAM, KEY, CharacterRef, Loader())
    await cache.drain_metrics()
    ttl = await fake_redis.ttl(keys.metrics(FAM, cache._today()))
    assert 35 * 86400 - 5 <= ttl <= 35 * 86400


# --- Key builders (C11, FR-003) --------------------------------------------------


def test_char_id_key_normalises_name_realm_and_region():
    assert keys.char_id("EU", "Area 52", "Rudolf") == keys.char_id(" eu", "area-52", "rudolf ")
    assert keys.char_id("US", "Kel'Thuzad", "Ab") == "wcl:v1:char_id:us:kelthuzad:ab"


def test_wcl_keys_are_versioned_and_hold_no_user_data():
    built = [
        keys.char_id("eu", "x", "y"),
        keys.char_zone(1, 0, "dps", 0),
        keys.char_enc(1, 2, "hps", 5),
        keys.char_reports(1, 20),
        keys.report_summary("abc"),
        keys.report_player("abc", 3, "DamageDone", 0, 0, "Friendlies"),
        keys.OAUTH_TOKEN,
        keys.WORLD_ZONES,
    ]
    assert all(k.startswith("wcl:v1:") for k in built)
    assert keys.refresh("user-1", 7).startswith("chat:")  # the only user-keyed entry


def test_every_family_has_config():
    assert set(cache.FAMILIES) == set(CacheFamily)


# --- US2: the cache is never a hard dependency (C7, C8) --------------------------


class DeadRedis:
    """Every command fails the way an unreachable Redis does."""

    def __init__(self):
        self.calls = 0

    def pipeline(self, *args, **kwargs):
        dead = self

        class Pipe:
            def __getattr__(self, name):
                return lambda *a, **k: self

            async def execute(self):
                dead.calls += 1
                from redis.exceptions import ConnectionError

                raise ConnectionError("connection refused")

        return Pipe()

    def __getattr__(self, name):
        async def fail(*args, **kwargs):
            self.calls += 1
            from redis.exceptions import ConnectionError

            raise ConnectionError("connection refused")

        return fail


@pytest.fixture
def dead_redis(monkeypatch):
    dead = DeadRedis()
    monkeypatch.setenv("REDIS_URL", "redis://nowhere:6379/0")
    monkeypatch.setattr(cache, "_make_redis", lambda url: dead)
    return dead


async def test_redis_down_falls_back_to_the_loader(dead_redis, caplog):
    load = Loader()
    with caplog.at_level("WARNING", logger="wcl_agent.cache"):
        assert await get_or_load(FAM, KEY, CharacterRef, load) == REF
        assert await get_or_load(FAM, KEY, CharacterRef, load) == REF
    assert load.calls == 2
    assert cache._counts[(FAM, "redis_error")] == 2
    # The circuit is open after the first failure: the second lookup never touched Redis.
    assert dead_redis.calls == 1
    assert sum("Redis unavailable" in r.getMessage() for r in caplog.records) == 1


async def test_circuit_closes_after_its_window(dead_redis, monkeypatch):
    await get_or_load(FAM, KEY, CharacterRef, Loader())
    now = cache.time.monotonic()
    monkeypatch.setattr(cache.time, "monotonic", lambda: now + cache._CIRCUIT_S + 1)
    await get_or_load(FAM, KEY, CharacterRef, Loader())
    assert dead_redis.calls == 2  # retried once the window passed


async def test_redis_errors_are_flushed_once_redis_is_back(fake_redis):
    cache._counts[(CacheFamily.WORLD_ZONES, "redis_error")] += 3
    await get_or_load(FAM, KEY, CharacterRef, Loader())
    assert (await counters(fake_redis, CacheFamily.WORLD_ZONES))["redis_error"] == 3
    assert not cache._counts


async def test_disabled_cache_never_touches_redis(dead_redis, monkeypatch):
    monkeypatch.setenv("WCL_CACHE_ENABLED", "false")
    load = Loader()
    assert await get_or_load(FAM, KEY, CharacterRef, load) == REF
    assert load.calls == 1 and dead_redis.calls == 0
    assert not cache._counts  # C8: no metrics either


async def test_no_redis_url_means_no_cache():
    load = Loader()
    assert await get_or_load(FAM, KEY, CharacterRef, load) == REF
    assert await get_or_load(FAM, KEY, CharacterRef, load) == REF
    assert load.calls == 2
    assert not cache._redis_clients


# --- PERF-003 / PERF-006 / PERF-007 (2026-10-18) -------------------------------------


async def test_memoised_family_skips_redis_and_survives_no_redis():
    """char_id is memoised in-process: no REDIS_URL still means one load (PERF-003)."""
    key = keys.char_id("eu", "Area 52", "Rudolf")
    load = Loader()
    for _ in range(3):
        assert await get_or_load(CacheFamily.CHAR_ID, key, CharacterRef, load) == REF
    assert load.calls == 1


async def test_memo_expires_and_force_refresh_bypasses_it(fake_redis, monkeypatch):
    key = keys.char_id("eu", "Area 52", "Rudolf")
    load = Loader()
    await get_or_load(CacheFamily.CHAR_ID, key, CharacterRef, load)
    await get_or_load(CacheFamily.CHAR_ID, key, CharacterRef, load, force_refresh=True)
    assert load.calls == 2
    now = cache.time.monotonic()
    monkeypatch.setattr(cache.time, "monotonic", lambda: now + 3601)
    await fake_redis.delete(key)  # memo expired and Redis empty: a real load
    await get_or_load(CacheFamily.CHAR_ID, key, CharacterRef, load)
    assert load.calls == 3


async def test_same_process_waiters_join_without_polling(fake_redis):
    """PERF-006: concurrent callers in one process share the load; nobody polls Redis."""
    load = Loader(delay=0.3)
    gets = 0
    real_get = fake_redis.__class__.get

    async def counting_get(self, *a, **k):
        nonlocal gets
        gets += 1
        return await real_get(self, *a, **k)

    import fakeredis

    orig = fakeredis.FakeAsyncRedis.get
    fakeredis.FakeAsyncRedis.get = counting_get
    try:
        await asyncio.gather(*(get_or_load(FAM, KEY, CharacterRef, load) for _ in range(5)))
    finally:
        fakeredis.FakeAsyncRedis.get = orig
    assert load.calls == 1
    assert gets == 1  # one GET for the shared lookup; no 100 ms polling by the others


async def test_hits_cost_no_extra_redis_write_until_the_flush(fake_redis):
    """PERF-007: outcomes are counted in-process and flushed in one pipeline."""
    await get_or_load(FAM, KEY, CharacterRef, Loader())
    await cache.drain_metrics()
    for _ in range(5):
        await get_or_load(FAM, KEY, CharacterRef, Loader())
    assert cache._counts[(FAM, "hit")] == 5  # not written yet
    assert (await counters(fake_redis))["hit"] == 5  # drain flushes them in one go
    assert not cache._counts


async def test_failed_flush_keeps_the_counts(dead_redis):
    cache._counts[(FAM, "hit")] += 4
    await cache.drain_metrics()
    assert cache._counts[(FAM, "hit")] == 4


async def test_large_values_are_decoded_off_the_loop(fake_redis, monkeypatch):
    from wcl_agent.cache_models import PlayerTable

    big = PlayerTable(data=["x" * 100] * 4000)  # ~400 KB
    await get_or_load(FAM, KEY, PlayerTable, lambda: _value(big))
    threads = []
    real = cache.asyncio.to_thread

    async def spy(fn, *args):
        threads.append(fn)
        return await real(fn, *args)

    monkeypatch.setattr(cache.asyncio, "to_thread", spy)
    assert await get_or_load(FAM, KEY, PlayerTable, lambda: _value(None)) == big
    assert threads == [cache._decode]


async def _value(v):
    return v


# --- get_many_or_load (PERF-001) ------------------------------------------------------


class BatchLoader:
    def __init__(self):
        self.batches: list[list[int]] = []

    async def __call__(self, missing):
        self.batches.append(list(missing))
        return [None if i == 2 else REF.model_copy(update={"id": i}) for i in missing]


MANY = [keys.char_zone(i, 0, "dps", 0) for i in range(4)]


async def test_many_loads_only_the_misses_in_one_batch(fake_redis):
    await fake_redis.set(MANY[1], REF.model_copy(update={"id": 1}).model_dump_json())
    await fake_redis.set(MANY[3], b"{corrupt")
    load = BatchLoader()
    got = await cache.get_many_or_load(FAM, MANY, CharacterRef, load)
    assert [g.id if g else None for g in got] == [0, 1, None, 3]
    assert load.batches == [[0, 2, 3]]  # one call for every miss, the corrupt one included
    again = await cache.get_many_or_load(FAM, MANY, CharacterRef, BatchLoader())
    assert [g.id if g else None for g in again] == [0, 1, None, 3]  # incl. the negative entry
    c = await counters(fake_redis)
    assert c["miss"] == 3 and c["load_count"] == 1 and c["error"] == 1
    assert c["hit"] == 1 + 3 and c["neg_hit"] == 1


async def test_many_with_redis_down_or_disabled_loads_everything(dead_redis, monkeypatch):
    load = BatchLoader()
    got = await cache.get_many_or_load(FAM, MANY, CharacterRef, load)
    assert load.batches == [[0, 1, 2, 3]] and got[2] is None
    assert cache._counts[(FAM, "redis_error")] == 1
    monkeypatch.setenv("WCL_CACHE_ENABLED", "false")
    cache._counts.clear()
    await cache.get_many_or_load(FAM, MANY, CharacterRef, load)
    assert len(load.batches) == 2 and not cache._counts


async def test_many_uses_the_memo_for_memoised_families():
    many = [keys.char_id("eu", "r", f"n{i}") for i in range(3)]
    load = BatchLoader()
    await cache.get_many_or_load(CacheFamily.CHAR_ID, many, CharacterRef, load)
    await cache.get_many_or_load(CacheFamily.CHAR_ID, many, CharacterRef, load)
    assert load.batches == [[0, 1, 2], [2]]  # only the not-found one is asked again
