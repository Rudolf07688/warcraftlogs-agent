"""Shared Redis cache for Warcraft Logs data (feature 014).

Cache-aside with TTLs, per key family. :func:`get_or_load` is the only way code reads or
writes cached WCL data, so no lookup can bypass the per-family hit/miss counters behind the
admin stats endpoint. Values are the app's own typed models (``cache_models``), never raw
GraphQL responses; keys come from :class:`keys` and never hold a user, tenant or
conversation id — the data is public, so every user shares one entry.

The cache is never a hard dependency: without ``REDIS_URL`` (or with
``WCL_CACHE_ENABLED=false``) lookups go straight to their loader, and when Redis fails they
do the same while a short per-loop circuit keeps the failed server out of the hot path.

Deliberately dependency-light and standalone (no backend/DB imports), so the ``wcl_agent``
package keeps running on its own. See specs/014-redis-wcl-cache/contracts/cache-client.md
and documentation/redis_cache_spec.md.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
import random
import threading
import time
import weakref
from collections import Counter, OrderedDict
from collections.abc import Awaitable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Callable, TypeVar

from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from .normalize import server_slug

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


M = TypeVar("M", bound=BaseModel)


class CacheFamily(StrEnum):
    CHAR_ID = "char_id"
    CHAR_OVERVIEW = "char_overview"
    CHAR_REPORTS = "char_reports"
    REPORT_SUMMARY = "report_summary"
    REPORT_PLAYER = "report_player"
    OAUTH_TOKEN = "oauth_token"
    WORLD_ZONES = "world_zones"
    # feature 015: guide-pipeline sources (not WCL data, but cached the same way)
    GAME_CLASSES = "game_classes"
    SPEC_DATASHEET = "spec_datasheet"
    GUIDE_RESEARCH = "guide_research"
    TALENT_NAMES = "talent_names"
    LIVE_VERSION = "live_version"
    HOTFIX_FEED = "hotfix_feed"
    # feature 016: the startup model discovery result
    MODEL_CATALOG = "model_catalog"


class Outcome(StrEnum):
    HIT = "hit"
    MISS = "miss"
    NEG_HIT = "neg_hit"
    LOCK_TIMEOUT = "lock_timeout"
    ERROR = "error"
    REDIS_ERROR = "redis_error"


@dataclass(frozen=True)
class FamilyConfig:
    default_ttl_s: int  # overridable by WCL_CACHE_TTL_{FAMILY}
    review_below: float  # hit rate under which the stats endpoint says "review"
    # Seconds a value is also kept in this process, in front of Redis (0 = not memoised).
    # Only for small, slow-changing values read on hot paths: it spares the Redis round trip
    # and decode, and keeps them cheap when Redis is down or absent (PERF-003, 2026-10-18).
    memo_s: int = 0


FAMILIES: dict[CacheFamily, FamilyConfig] = {
    CacheFamily.CHAR_ID: FamilyConfig(86400, 0.90, memo_s=3600),
    CacheFamily.OAUTH_TOKEN: FamilyConfig(0, 0.90),  # TTL always comes from the token expiry
    CacheFamily.WORLD_ZONES: FamilyConfig(3600, 0.90, memo_s=300),  # read every chat turn
    CacheFamily.CHAR_OVERVIEW: FamilyConfig(600, 0.60),
    CacheFamily.CHAR_REPORTS: FamilyConfig(300, 0.60),
    CacheFamily.REPORT_SUMMARY: FamilyConfig(86400, 0.40),
    CacheFamily.REPORT_PLAYER: FamilyConfig(86400, 0.40),
    CacheFamily.GAME_CLASSES: FamilyConfig(86400, 0.90, memo_s=3600),  # live class/spec roster
    CacheFamily.SPEC_DATASHEET: FamilyConfig(43200, 0.50),  # guide data sheets (research R6)
    CacheFamily.GUIDE_RESEARCH: FamilyConfig(21600, 0.50),  # filtered guide fact sheets
    CacheFamily.TALENT_NAMES: FamilyConfig(604800, 0.50),  # optional talent id → name map
    CacheFamily.LIVE_VERSION: FamilyConfig(900, 0.50),  # Blizzard's live build (research R1)
    CacheFamily.HOTFIX_FEED: FamilyConfig(1800, 0.50),  # newest "Hotfixes:" article (R2)
    CacheFamily.MODEL_CATALOG: FamilyConfig(21600, 0.50),  # discovered chat models (016 R6)
}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class CacheSettings:
    redis_url: str
    enabled: bool
    jitter: float
    lock_ms: int
    lock_wait_ms: int
    neg_ttl_s: int
    retention_days: int
    unfinished_ttl_s: int

    @property
    def active(self) -> bool:
        return self.enabled and bool(self.redis_url)


def cache_settings() -> CacheSettings:
    """Cache settings from the environment (read per call: cheap, and tests can patch env)."""
    return CacheSettings(
        redis_url=os.getenv("REDIS_URL", ""),
        enabled=os.getenv("WCL_CACHE_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"},
        jitter=_env_float("WCL_CACHE_JITTER", 0.10),
        # Longer than the WCL query timeout (75 s), so a slow load never loses its lock.
        lock_ms=_env_int("WCL_CACHE_LOCK_MS", 90000),
        lock_wait_ms=_env_int("WCL_CACHE_LOCK_WAIT_MS", 2000),
        neg_ttl_s=_env_int("WCL_NEG_CACHE_TTL", 60),
        retention_days=_env_int("WCL_METRICS_RETENTION_DAYS", 35),
        unfinished_ttl_s=_env_int("WCL_CACHE_UNFINISHED_TTL", 120),
    )


def family_ttl(family: CacheFamily) -> int:
    return _env_int(f"WCL_CACHE_TTL_{family.value.upper()}", FAMILIES[family].default_ttl_s)


def unfinished_ttl() -> int:
    return cache_settings().unfinished_ttl_s


class keys:  # noqa: N801 - a namespace: every cache key is built here, nowhere else
    """Key builders. No ``wcl:`` key may contain a user, tenant or conversation id (FR-008)."""

    OAUTH_TOKEN = "wcl:v1:oauth:token"
    WORLD_ZONES = "wcl:v1:world:zones"
    GAME_CLASSES = "wcl:v1:game:classes"

    @staticmethod
    def char_id(region: str, realm: str, name: str) -> str:
        return f"wcl:v1:char_id:{region.strip().lower()}:{server_slug(realm)}:{name.strip().lower()}"

    @staticmethod
    def char_zone(char_id: int, zone_id: int, metric: str, difficulty: int) -> str:
        return f"wcl:v1:char:{char_id}:overview:zone:{zone_id or 0}:{metric}:{difficulty or 0}"

    @staticmethod
    def char_enc(char_id: int, encounter_id: int, metric: str, difficulty: int) -> str:
        return f"wcl:v1:char:{char_id}:overview:enc:{encounter_id}:{metric}:{difficulty or 0}"

    @staticmethod
    def char_reports(char_id: int, limit: int) -> str:
        return f"wcl:v1:char:{char_id}:reports:{limit}"

    @staticmethod
    def report_summary(code: str) -> str:
        # ":keystone" retires summaries cached before the keystone fields existed (feature 022).
        return f"wcl:v1:report:{code.strip()}:summary:keystone"

    @staticmethod
    def report_player(
        code: str, source_id: int, data_type: str, fight_id: int, ability_id: int, hostility: str
    ) -> str:
        return (
            f"wcl:v1:report:{code.strip()}:player:{source_id}:table:"
            f"{data_type}:{fight_id or 0}:{ability_id or 0}:{hostility}"
        )

    @staticmethod
    def spec_datasheet(content_type: str, class_name: str, spec: str, patch_or_season: str) -> str:
        scope = "".join(patch_or_season.split()).lower()
        return f"wcl:v1:datasheet:{content_type}:{class_name}:{spec}:{scope}"

    @staticmethod
    def guide_research(content_type: str, class_name: str, spec: str, patch: str, hotfix: str) -> str:
        return f"guide:research:v1:{content_type}:{class_name}:{spec}:{patch}:{hotfix}"

    @staticmethod
    def talent_names(source: str) -> str:
        return f"ext:talents:v1:{source}"

    @staticmethod
    def live_version(region: str) -> str:
        return f"ext:wow_version:v1:{region.strip().lower()}"

    @staticmethod
    def hotfix_feed() -> str:
        return "ext:hotfix:v1"

    @staticmethod
    def model_catalog(project: str, location: str, sig: str) -> str:
        return f"ext:models:v1:{project}:{location}:{sig}"

    @staticmethod
    def lock(key: str) -> str:
        return f"lock:{key}"

    @staticmethod
    def metrics(family: CacheFamily, day: str) -> str:
        return f"wcl:metrics:v1:{family.value}:{day}"

    @staticmethod
    def refresh(user_id: str, char_id: int) -> str:
        # The only key holding a user id, deliberately outside the shared ``wcl:`` space.
        return f"chat:refresh:{user_id}:{char_id}"


# --- Redis client: one per event loop (redis.asyncio connections are loop-bound) ---------

_REDIS_TIMEOUT_S = 0.25  # a dead Redis costs at most this before the lookup falls back
_CIRCUIT_S = 5.0  # after a failure, leave Redis alone this long on that loop

_redis_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Redis] = weakref.WeakKeyDictionary()
_down_until: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, float] = weakref.WeakKeyDictionary()


def _make_redis(url: str) -> Redis:
    return Redis.from_url(url, socket_timeout=_REDIS_TIMEOUT_S, socket_connect_timeout=_REDIS_TIMEOUT_S)


def _client() -> Redis | None:
    """This loop's Redis client, or None while the circuit is open after a failure."""
    loop = asyncio.get_running_loop()
    until = _down_until.get(loop)
    if until is not None:
        if time.monotonic() < until:
            return None
        del _down_until[loop]
        logger.info("wcl cache: retrying Redis")
    client = _redis_clients.get(loop)
    if client is None:
        try:
            client = _make_redis(cache_settings().redis_url)
        except Exception as exc:  # noqa: BLE001 - e.g. a URL without a scheme: fail open (C7)
            if loop not in _down_until:
                logger.warning("wcl cache: cannot use REDIS_URL, bypassing the cache for %.0fs: %s", _CIRCUIT_S, exc)
            _down_until[loop] = time.monotonic() + _CIRCUIT_S
            return None
        _redis_clients[loop] = client
    return client


def _redis_failed(family: CacheFamily, exc: BaseException) -> None:
    """Count a redis_error and open the circuit on this loop (C7). Logs once per opening."""
    _record(family, Outcome.REDIS_ERROR)
    loop = asyncio.get_running_loop()
    if loop not in _down_until:
        logger.warning("wcl cache: Redis unavailable, bypassing the cache for %.0fs: %s", _CIRCUIT_S, exc)
    _down_until[loop] = time.monotonic() + _CIRCUIT_S


async def aclose_redis() -> None:
    """Flush pending metrics, then close every loop's Redis client (``aclose_clients``)."""
    await drain_metrics()
    clients = list(_redis_clients.values())
    _redis_clients.clear()
    for client in clients:
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001 - shutdown is best effort
            pass


# --- Process memo (PERF-003): small hot values kept in front of Redis --------------------

_MEMO_MAX = 1024
_memo: OrderedDict[str, tuple[float, BaseModel]] = OrderedDict()
_memo_lock = threading.Lock()  # loops on other threads (CLI, tests) share the memo


def _memo_get(key: str) -> BaseModel | None:
    with _memo_lock:
        item = _memo.get(key)
        if item is None:
            return None
        expires_at, value = item
        if time.monotonic() >= expires_at:
            del _memo[key]
            return None
        _memo.move_to_end(key)
        return value


def _memo_put(key: str, value: BaseModel, ttl_s: int) -> None:
    with _memo_lock:
        _memo[key] = (time.monotonic() + ttl_s, value)
        _memo.move_to_end(key)
        while len(_memo) > _MEMO_MAX:
            _memo.popitem(last=False)


# --- Metrics (C10): per family per UTC day, never block or fail a request ----------------
# Outcomes are counted in this process and flushed in one pipeline every few seconds
# (PERF-007): a hit costs no extra Redis round trip, and counts survive a failed flush.

_FLUSH_S = 2.0
_counts: Counter[tuple[CacheFamily, str]] = Counter()
_flush_tasks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Task[None]] = (
    weakref.WeakKeyDictionary()
)
_expiring: set[str] = set()  # metric hashes already given their TTL by this process


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _record(family: CacheFamily, outcome: Outcome, load_ms: int | None = None) -> None:
    _counts[(family, outcome.value)] += 1
    if load_ms is not None:
        _counts[(family, "load_ms_sum")] += load_ms
        _counts[(family, "load_count")] += 1
    loop = asyncio.get_running_loop()
    task = _flush_tasks.get(loop)
    if task is None or task.done():
        _flush_tasks[loop] = loop.create_task(_flush_later())


async def _flush_later() -> None:
    await asyncio.sleep(_FLUSH_S)
    await _flush()


async def _flush() -> None:
    """Write the counted outcomes to today's hashes; on failure keep them for next time."""
    if not _counts or not cache_settings().active:
        return
    try:
        client = _client()
    except Exception as exc:  # noqa: BLE001 - metrics are best effort
        logger.debug("wcl cache: metrics flush skipped: %s", exc)
        return
    if client is None:  # circuit open: keep counting
        return
    batch = Counter(_counts)
    _counts.clear()
    day = _today()
    retention_s = cache_settings().retention_days * 86400
    new_keys = set()
    try:
        pipe = client.pipeline(transaction=False)
        for (family, field), amount in batch.items():
            key = keys.metrics(family, day)
            pipe.hincrby(key, field, amount)
            if key not in _expiring and key not in new_keys:
                pipe.expire(key, retention_s)
                new_keys.add(key)
        await pipe.execute()
        _expiring.update(new_keys)
    except Exception as exc:  # noqa: BLE001 - metrics are best effort
        _counts.update(batch)
        logger.debug("wcl cache: metrics flush failed: %s", exc)


async def drain_metrics() -> None:
    """Flush counted outcomes now instead of on the timer (tests, shutdown)."""
    task = _flush_tasks.pop(asyncio.get_running_loop(), None)
    if task is not None and not task.done():
        task.cancel()
    await _flush()


# --- get_or_load: the only way code reads or writes cached WCL data --------------------

_MISSING = b'{"_missing":true}'
_POLL_S = 0.1
_DECODE_OFF_LOOP_BYTES = 256_000  # like the WCL client: big values are parsed off the loop

# Same-process single-flight (PERF-006): key -> [shared load task, waiter count], per loop.
_flights: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, list[Any]]] = (
    weakref.WeakKeyDictionary()
)


def _drop_flight(flights: dict[str, list[Any]], key: str, task: asyncio.Future[Any]) -> None:
    flight = flights.get(key)
    if flight is not None and flight[0] is task:
        del flights[key]


def _decode(raw: bytes, model: type[M]) -> tuple[bool, M | None]:
    """(valid, value): the ``_missing`` marker is (True, None); corrupt data is (False, None)."""
    if raw == _MISSING:
        return True, None
    try:
        return True, model.model_validate_json(raw)
    except ValueError:  # pydantic.ValidationError, bad JSON
        return False, None


async def _adecode(raw: bytes, model: type[M]) -> tuple[bool, M | None]:
    if len(raw) > _DECODE_OFF_LOOP_BYTES:
        return await asyncio.to_thread(_decode, raw, model)
    return _decode(raw, model)


async def get_or_load(
    family: CacheFamily,
    key: str,
    model: type[M],
    loader: Callable[[], Awaitable[M | None]],
    *,
    ttl: int | Callable[[M], int] | None = None,
    force_refresh: bool = False,
) -> M | None:
    """Return the cached value for ``key``, loading and storing it on a miss.

    ``loader`` returning None means "not found": a short-lived marker is cached and None is
    returned. ``ttl`` is seconds, a function of the loaded value (token expiry, finished vs
    live report), or None for the family default. Redis problems never reach the caller —
    the loader is called directly instead. Memoised families (``FamilyConfig.memo_s``)
    return a shared instance: treat it as read-only.
    """
    memo_s = FAMILIES[family].memo_s
    if memo_s and not force_refresh:
        memoised = _memo_get(key)
        if memoised is not None:
            return memoised  # type: ignore[return-value]
    value = await _shared(family, key, model, loader, ttl, force_refresh)
    if memo_s and value is not None:
        _memo_put(key, value, memo_s)
    return value


async def _shared(
    family: CacheFamily,
    key: str,
    model: type[M],
    loader: Callable[[], Awaitable[M | None]],
    ttl: int | Callable[[M], int] | None,
    force_refresh: bool,
) -> M | None:
    """The Redis layer, with concurrent same-process lookups of one key sharing one call."""
    settings = cache_settings()
    if not settings.active:
        return await loader()
    if force_refresh:  # must reload, so it never joins a lookup that may read the old value
        return await _lookup(settings, family, key, model, loader, ttl, force_refresh)
    flights = _flights.setdefault(asyncio.get_running_loop(), {})
    flight = flights.get(key)
    joined = flight is not None
    if flight is None:
        task = asyncio.ensure_future(_lookup(settings, family, key, model, loader, ttl, False))
        flight = flights[key] = [task, 0]
        task.add_done_callback(functools.partial(_drop_flight, flights, key))
    task = flight[0]
    flight[1] += 1
    try:
        value = await asyncio.shield(task)
    finally:
        flight[1] -= 1
        if flight[1] == 0 and not task.done():
            _drop_flight(flights, key, task)  # a new caller starts afresh, never joins this
            task.cancel()  # every caller left: stop the load (and release its lock)
    if joined:
        _record(family, Outcome.NEG_HIT if value is None else Outcome.HIT)
    return value


async def _lookup(
    settings: CacheSettings,
    family: CacheFamily,
    key: str,
    model: type[M],
    loader: Callable[[], Awaitable[M | None]],
    ttl: int | Callable[[M], int] | None,
    force_refresh: bool,
) -> M | None:
    client = _client()
    if client is None:  # circuit open
        _record(family, Outcome.REDIS_ERROR)
        return await loader()
    try:
        if not force_refresh:
            raw = await client.get(key)
            if raw is not None:
                valid, value = await _adecode(raw, model)
                if valid:
                    _record(family, Outcome.NEG_HIT if value is None else Outcome.HIT)
                    return value
                await client.delete(key)  # corrupt: drop it and load again (C6)
                _record(family, Outcome.ERROR)
        won = await client.set(keys.lock(key), b"1", nx=True, px=settings.lock_ms)
    except RedisError as exc:
        _redis_failed(family, exc)
        return await loader()
    if won:
        return await _load_and_store(client, settings, family, key, loader, ttl)
    return await _wait_for_winner(client, settings, family, key, model, loader)


def _encode(
    settings: CacheSettings, family: CacheFamily, value: M | None, ttl: int | Callable[[M], int] | None
) -> tuple[bytes, int]:
    """The stored bytes and their expiry in seconds (0 = don't store)."""
    if value is None:
        return _MISSING, settings.neg_ttl_s
    base = family_ttl(family) if ttl is None else ttl(value) if callable(ttl) else ttl
    # No jitter on the token: stretching its TTL would outlive the token itself.
    spread = 1.0 if family is CacheFamily.OAUTH_TOKEN else random.uniform(1.0, 1.0 + settings.jitter)
    return value.model_dump_json().encode(), int(base * spread)


async def _load_and_store(
    client: Redis,
    settings: CacheSettings,
    family: CacheFamily,
    key: str,
    loader: Callable[[], Awaitable[M | None]],
    ttl: int | Callable[[M], int] | None,
) -> M | None:
    try:
        started = time.perf_counter()
        try:
            value = await loader()
        except Exception:
            _record(family, Outcome.ERROR)
            raise
        _record(family, Outcome.MISS, int((time.perf_counter() - started) * 1000))
        payload, expiry = _encode(settings, family, value, ttl)
        if expiry > 0:
            try:
                await client.set(key, payload, ex=expiry)
            except RedisError as exc:
                _redis_failed(family, exc)
        return value
    finally:
        try:  # release the lock on success, error and cancellation alike (C5, C12)
            await client.delete(keys.lock(key))
        except RedisError:
            pass


async def _wait_for_winner(
    client: Redis,
    settings: CacheSettings,
    family: CacheFamily,
    key: str,
    model: type[M],
    loader: Callable[[], Awaitable[M | None]],
) -> M | None:
    """Lock loser (another process loads it): poll for its value, then load without writing (C4)."""
    deadline = time.monotonic() + settings.lock_wait_ms / 1000
    try:
        while (remaining := deadline - time.monotonic()) > 0:
            await asyncio.sleep(min(_POLL_S, remaining))
            raw = await client.get(key)
            if raw is not None:
                valid, value = await _adecode(raw, model)
                if valid:
                    _record(family, Outcome.NEG_HIT if value is None else Outcome.HIT)
                    return value
                break
    except RedisError as exc:
        _redis_failed(family, exc)
        return await loader()
    _record(family, Outcome.LOCK_TIMEOUT)
    return await loader()


async def get_many_or_load(
    family: CacheFamily,
    keys_: Sequence[str],
    model: type[M],
    batch_loader: Callable[[list[int]], Awaitable[list[M | None]]],
    *,
    ttl: int | Callable[[M], int] | None = None,
) -> list[M | None]:
    """Batched :func:`get_or_load` for background batch work (PERF-001, 2026-10-18).

    One ``MGET`` for every key, then ``batch_loader(missing_indexes)`` — one WCL request for
    all misses, returning their values in that order — then one pipelined write. There is
    no stampede lock: batch callers are background refreshes, and the WCL client's
    single-flight already joins identical in-flight requests. Same outcomes, metrics,
    memo and fail-open behaviour as ``get_or_load``.
    """
    results: list[M | None] = [None] * len(keys_)
    missing = list(range(len(keys_)))
    memo_s = FAMILIES[family].memo_s
    if memo_s:
        for i in list(missing):
            memoised = _memo_get(keys_[i])
            if memoised is not None:
                results[i] = memoised  # type: ignore[assignment]
                missing.remove(i)
    if not missing:
        return results
    settings = cache_settings()
    client = _client() if settings.active else None
    if settings.active and client is None:  # circuit open
        _record(family, Outcome.REDIS_ERROR)
    if client is not None:
        try:
            raws = await client.mget([keys_[i] for i in missing])
            still: list[int] = []
            corrupt: list[str] = []
            for i, raw in zip(missing, raws):
                valid, value = (False, None) if raw is None else await _adecode(raw, model)
                if valid:
                    results[i] = value
                    _record(family, Outcome.NEG_HIT if value is None else Outcome.HIT)
                    continue
                if raw is not None:
                    corrupt.append(keys_[i])
                    _record(family, Outcome.ERROR)
                still.append(i)
            if corrupt:
                await client.delete(*corrupt)
            missing = still
        except RedisError as exc:
            _redis_failed(family, exc)
            client = None
    if missing:
        started = time.perf_counter()
        try:
            loaded = await batch_loader(missing)
        except Exception:
            if settings.active:
                _record(family, Outcome.ERROR)
            raise
        if settings.active:
            # One load event for the batch; one miss per key it filled.
            _record(family, Outcome.MISS, int((time.perf_counter() - started) * 1000))
            for _ in missing[1:]:
                _record(family, Outcome.MISS)
        pipe = client.pipeline(transaction=False) if client is not None else None
        for i, value in zip(missing, loaded):
            results[i] = value
            if pipe is not None:
                payload, expiry = _encode(settings, family, value, ttl)
                if expiry > 0:
                    pipe.set(keys_[i], payload, ex=expiry)
        if pipe is not None:
            try:
                await pipe.execute()
            except RedisError as exc:
                _redis_failed(family, exc)
    if memo_s:
        for i in range(len(keys_)):
            if results[i] is not None:
                _memo_put(keys_[i], results[i], memo_s)  # type: ignore[arg-type]
    return results


# --- Statistics (US3): per-family hit rates over a window of UTC days -------------------

_COUNTERS = ("hit", "miss", "neg_hit", "lock_timeout", "error", "redis_error", "load_ms_sum", "load_count")


def _window(days: int, today: datetime | None = None) -> list[str]:
    today = today or datetime.now(timezone.utc)
    return [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(days)]


def summarize(per_day: dict[CacheFamily, list[dict[str, int]]]) -> dict[str, dict[str, Any]]:
    """Sum each family's daily counters and derive hit rate, average load time and status.

    Pure, so it is testable without Redis. Every family is present, even with no data.
    """
    out: dict[str, dict[str, Any]] = {}
    for family in CacheFamily:
        total = Counter[str]()
        for day in per_day.get(family, []):
            total.update({k: int(v) for k, v in day.items() if k in _COUNTERS})
        lookups = total["hit"] + total["neg_hit"] + total["miss"]
        hit_rate = (total["hit"] + total["neg_hit"]) / lookups if lookups else None
        if hit_rate is None:
            status = "no_data"
        elif hit_rate < FAMILIES[family].review_below:
            status = "review"
        else:
            status = "ok"
        out[family.value] = {
            "hits": total["hit"],
            "misses": total["miss"],
            "neg_hits": total["neg_hit"],
            "lock_timeouts": total["lock_timeout"],
            "errors": total["error"],
            "redis_errors": total["redis_error"],
            "hit_rate": round(hit_rate, 3) if hit_rate is not None else None,
            "avg_load_ms": round(total["load_ms_sum"] / total["load_count"], 1) if total["load_count"] else None,
            "status": status,
        }
    return out


async def read_stats(days: int) -> dict[str, Any]:
    """Per-family stats for the last ``days`` UTC days plus Redis health (``CacheStats`` shape).

    Never raises for Redis trouble: an unreachable or disabled cache gives the degraded shape.
    """
    settings = cache_settings()
    result: dict[str, Any] = {
        "window_days": days,
        "enabled": settings.active,
        "available": False,
        "families": summarize({}),
        "redis": None,
    }
    client = _client() if settings.active else None
    if client is None:
        return result
    slots = [(family, keys.metrics(family, day)) for family in CacheFamily for day in _window(days)]
    try:
        pipe = client.pipeline(transaction=False)
        for _, key in slots:
            pipe.hgetall(key)
        hashes = await pipe.execute()
    except RedisError as exc:
        logger.warning("wcl cache: stats unavailable: %s", exc)
        return result
    per_day: dict[CacheFamily, list[dict[str, int]]] = {}
    for (family, _), raw in zip(slots, hashes):
        per_day.setdefault(family, []).append(
            {(k.decode() if isinstance(k, bytes) else k): int(v) for k, v in raw.items()}
        )
    result.update(available=True, families=summarize(per_day), redis=await _redis_health(client))
    return result


async def _redis_health(client: Redis) -> dict[str, Any] | None:
    """Server-wide numbers from INFO; None where INFO is unavailable (some managed Redis)."""
    try:
        info = {**await client.info("stats"), **await client.info("memory")}
    except RedisError as exc:
        logger.debug("wcl cache: INFO unavailable: %s", exc)
        return None
    hits, misses = int(info.get("keyspace_hits", 0)), int(info.get("keyspace_misses", 0))
    return {
        "keyspace_hit_rate": round(hits / (hits + misses), 3) if hits + misses else None,
        "evicted_keys": int(info.get("evicted_keys", 0)),
        "used_memory_mb": round(int(info.get("used_memory", 0)) / (1024 * 1024), 1),
    }


# --- Forced refresh (US4): at most once per user per character per minute ---------------

# The signed-in user of the current chat turn, set by the backend (feature 014). Only the
# refresh limit reads it, and only into ``chat:`` keys — never into shared ``wcl:`` entries.
_refresh_actor: ContextVar[str | None] = ContextVar("wcl_refresh_actor", default=None)
REFRESH_WINDOW_S = 60


def set_refresh_actor(user_id: str | None) -> None:
    _refresh_actor.set(user_id or None)


def get_refresh_actor() -> str | None:
    return _refresh_actor.get()


async def try_claim_refresh(user_id: str | None, char_id: int) -> bool:
    """True when ``user_id`` may force a refresh of ``char_id`` now (and records that it did).

    Without a user or a working cache there is nothing shared to protect, so it is allowed.
    """
    if not user_id or not cache_settings().active:
        return True
    client = _client()
    if client is None:
        return True
    try:
        return bool(await client.set(keys.refresh(user_id, char_id), b"1", nx=True, ex=REFRESH_WINDOW_S))
    except RedisError:
        return True
