"""Revocation lag and gone-vs-write races (feature 045, sc-296).

1. A store hit visible only through the tenant's own grant never back-fills the shared Redis.
2. A fetch already under way when its report went away isn't written back after the gone.
3. A loader that read a report before its Redis keys were evicted can't write them back.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from backend.app.db.models import RawFetch, RawFetchGrant
from backend.app.services import fetch_persistence, raw_fetch_reads
from backend.app.services.fetch_persistence import PendingWrite, store_batch
from backend.app.services.raw_fetch_reads import read_stored_fetch
from backend.app.tenancy.context import RequestIdentity, current_identity
from backend.tests.wcl_fakes import gql_response, mock_async_client
from wcl_agent.cache import cache as wcl_cache
from wcl_agent.cache.cache import CacheFamily, evict_report, get_many_or_load, get_or_load, keys
from wcl_agent.cache.cache_models import PlayerTable
from wcl_agent.client import wcl_client
from wcl_agent.client.queries import REPORT_SUMMARY
from wcl_agent.client.wcl_client import FetchedResponse, ReportGone, StoredFetch, _flight_key
from wcl_agent.tools.report_tools import load_report_summary

NOW = datetime.now(UTC)
ENDED = int((NOW - timedelta(days=3)).timestamp() * 1000)
TABLE_Q = "query ReportQ($code: String!) { reportData { report(code: $code) { table } } }"


def fetched(query, variables, data, at=NOW, requested_at=None) -> FetchedResponse:
    body = json.dumps({"data": data}).encode()
    return FetchedResponse(_flight_key(query, variables), query, variables, body, at, requested_at)


def summary(code: str, visibility: str, at=NOW, requested_at=None) -> FetchedResponse:
    report = {
        "code": code, "visibility": visibility, "title": "Raid", "startTime": ENDED - 1000, "endTime": ENDED,
        "zone": {"id": 1, "name": "Zone"}, "guild": {"name": "G"}, "masterData": {"actors": []}, "fights": [],
    }
    return fetched(REPORT_SUMMARY, {"code": code}, {"reportData": {"report": report}}, at, requested_at)


def table(code: str, at=NOW, requested_at=None) -> FetchedResponse:
    return fetched(TABLE_Q, {"code": code}, {"reportData": {"report": {"table": code}}}, at, requested_at)


@contextlib.contextmanager
def turn(tenant: uuid.UUID | None):
    token = current_identity.set(RequestIdentity(uuid.uuid4(), tenant, "member", False, uuid.uuid4()))
    try:
        yield
    finally:
        current_identity.reset(token)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    """Process-wide state: a closed breaker and no tombstones, for this test only."""
    monkeypatch.setattr(raw_fetch_reads, "breaker", raw_fetch_reads.Breaker())
    monkeypatch.setattr(fetch_persistence, "_tombstones", type(fetch_persistence._tombstones)())


@pytest.fixture
def wcl(monkeypatch):
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        return gql_response({"data": {"reportData": {"report": None}}})

    client = mock_async_client(handler)
    monkeypatch.setattr(wcl_client, "_fetch_sink", None)
    monkeypatch.setattr(wcl_client, "_fetch_source", read_stored_fetch)
    monkeypatch.setattr(wcl_client, "get_async_client", lambda: client)
    return calls


# --- AC1: a granted-only store hit stays out of the shared cache ---------------------------------


async def test_a_granted_only_store_hit_never_back_fills_redis(patched_db, wcl, fake_redis, tenant_id):
    await store_batch([PendingWrite(summary("Priv1", "unlisted"), tenant_id)])
    with turn(tenant_id):
        loaded = await load_report_summary("Priv1")
    assert loaded is not None and loaded.title == "Raid" and wcl["n"] == 0  # served from the store
    assert await fake_redis.get(keys.report_summary("Priv1")) is None


async def test_a_public_store_hit_still_back_fills_redis(patched_db, wcl, fake_redis, tenant_id):
    await store_batch([PendingWrite(summary("Pub1", "public"), tenant_id)])
    with turn(tenant_id):
        assert await load_report_summary("Pub1") is not None
    assert await fake_redis.get(keys.report_summary("Pub1")) is not None


async def test_a_mark_from_a_sub_task_of_the_loader_keeps_the_value_out(fake_redis, monkeypatch):
    """The loader may fan out (gather): its sub-tasks run in copied contexts."""
    monkeypatch.setitem(wcl_cache.FAMILIES, CacheFamily.REPORT_PLAYER,
                        wcl_cache.FamilyConfig(86400, 0.4, memo_s=60))  # memo too

    async def loader():
        async def part():
            wcl_cache.mark_unshareable()
        await asyncio.gather(part())
        return PlayerTable(data={"x": 1})

    key = keys.report_player("Sub1", 1, "DamageDone", 1, 0, "Friendlies")
    assert await get_or_load(CacheFamily.REPORT_PLAYER, key, PlayerTable, loader) is not None
    assert await fake_redis.get(key) is None and wcl_cache._memo_get(key) is None


async def test_a_batch_load_marked_unshareable_writes_nothing(fake_redis):
    async def batch(missing):
        wcl_cache.mark_unshareable()
        return [PlayerTable(data={"i": i}) for i in missing]

    names = [keys.report_player(f"Bat{i}", 1, "DamageDone", 1, 0, "Friendlies") for i in range(2)]
    assert len(await get_many_or_load(CacheFamily.REPORT_PLAYER, names, PlayerTable, batch)) == 2
    assert await fake_redis.mget(names) == [None, None]


async def test_each_waiter_marks_its_own_load(monkeypatch, fake_redis, tenant_id):
    """Two cache loads join one WCL flight; the private answer keeps both out of Redis."""

    class Private:
        def scope(self):
            return "t"

        async def __call__(self, *args):
            await asyncio.sleep(0.02)
            return StoredFetch(b'{"data": {"reportData": {"report": {"table": 1}}}}', False)

    monkeypatch.setattr(wcl_client, "_fetch_source", Private())
    client = mock_async_client(lambda request: gql_response({}))

    async def load():
        await client.query(TABLE_Q, {"code": "Join1"})
        return PlayerTable(data=1)

    a = keys.report_player("Join1", 1, "DamageDone", 1, 0, "Friendlies")
    b = keys.report_player("Join1", 2, "DamageDone", 1, 0, "Friendlies")
    await asyncio.gather(get_or_load(CacheFamily.REPORT_PLAYER, a, PlayerTable, load),
                         get_or_load(CacheFamily.REPORT_PLAYER, b, PlayerTable, load))
    assert await fake_redis.mget([a, b]) == [None, None]


async def _summaries(*tenants):
    async def as_(tenant):
        with turn(tenant):
            return await load_report_summary("Priv9")

    return await asyncio.gather(*(as_(tenant) for tenant in tenants))


async def test_another_tenant_joining_a_grant_only_load_loads_for_itself(
    patched_db, wcl, fake_redis, tenant_id, other_tenant_id
):
    """QA SEC-001/BUG-007: the cache flight is keyed by the Redis key only, so B joins A's load."""
    await store_batch([PendingWrite(summary("Priv9", "unlisted"), tenant_id)])
    a, b, background = await _summaries(tenant_id, other_tenant_id, None)
    assert a is not None and a.title == "Raid"
    assert b is None and background is None  # what each gets alone: WCL says report null
    assert await fake_redis.get(keys.report_summary("Priv9")) in (None, wcl_cache._MISSING)


async def test_the_same_tenant_joining_a_grant_only_load_still_gets_it(patched_db, wcl, fake_redis, tenant_id):
    await store_batch([PendingWrite(summary("Priv9", "unlisted"), tenant_id)])
    first, second = await _summaries(tenant_id, tenant_id)
    assert first is not None and second is not None and wcl["n"] == 0


async def test_a_public_load_is_still_shared_with_every_joiner(patched_db, wcl, fake_redis, tenant_id, other_tenant_id):
    await store_batch([PendingWrite(summary("Priv9", "public"), tenant_id)])
    loads, reads = [], []
    redis_class = type(fake_redis)  # the cache's own client is another instance of it
    real_query, real_get = wcl_client.AsyncWCLClient.query, redis_class.get

    async def query(self, *args, **kwargs):
        loads.append(1)
        return await real_query(self, *args, **kwargs)

    async def get(self, name):
        reads.append(name)
        return await real_get(self, name)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(wcl_client.AsyncWCLClient, "query", query)
        mp.setattr(redis_class, "get", get)
        results = await _summaries(tenant_id, other_tenant_id, None)
    assert all(r is not None for r in results) and wcl["n"] == 0
    assert len(loads) == 1 and reads.count(keys.report_summary("Priv9")) == 1  # one lookup for all


# --- AC2 race 1: a stale fetch written after a ReportGone ----------------------------------------


async def rows(factory, code: str) -> tuple[int, int]:
    async with factory() as session:
        fetches = await session.scalar(select(func.count()).select_from(RawFetch).where(RawFetch.report_code == code))
        grants = await session.scalar(
            select(func.count()).select_from(RawFetchGrant).where(RawFetchGrant.report_code == code)
        )
    return fetches, grants


async def test_a_fetch_requested_before_the_gone_brings_back_neither_row_nor_grant(patched_db, tenant_id):
    seen = NOW
    await store_batch([PendingWrite(ReportGone(("Race1",), seen))])
    # Sent before WCL said the report was gone, answered (and queued) after it.
    late = table("Race1", at=seen + timedelta(seconds=5), requested_at=seen - timedelta(seconds=10))
    result = await store_batch([PendingWrite(late, tenant_id)])
    assert await rows(patched_db, "Race1") == (0, 0) and result.changed == []


async def test_a_stale_summary_in_the_same_batch_as_the_gone_is_skipped_too(patched_db, tenant_id):
    stale = summary("Race2", "unlisted", at=NOW + timedelta(seconds=1), requested_at=NOW - timedelta(seconds=3))
    await store_batch([PendingWrite(ReportGone(("Race2",), NOW)), PendingWrite(stale, tenant_id)])
    async with patched_db() as session:
        assert await session.scalar(select(func.count()).select_from(RawFetch)) == 0


async def test_a_fetch_requested_after_the_gone_is_written(patched_db, tenant_id):
    await store_batch([PendingWrite(ReportGone(("Back1",), NOW))])
    fresh = table("Back1", at=NOW + timedelta(seconds=3), requested_at=NOW + timedelta(seconds=1))
    await store_batch([PendingWrite(fresh, tenant_id)])
    assert await rows(patched_db, "Back1") == (1, 1)  # the report came back


async def test_tombstones_expire_and_stay_bounded(monkeypatch):
    monkeypatch.setattr(fetch_persistence, "TOMBSTONE_MAX", 3)
    old = NOW - fetch_persistence.TOMBSTONE_TTL - timedelta(seconds=1)
    fetch_persistence._bury(["Old1"], old)
    fetch_persistence._bury(["A", "B", "C", "D"], NOW)
    assert list(fetch_persistence._tombstones) == ["B", "C", "D"]


# --- AC2 race 2: a loader can't refill Redis after the eviction ----------------------------------


async def test_a_loader_writing_after_the_eviction_leaves_no_entry(fake_redis):
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_loader():
        started.set()
        await release.wait()  # read the old data, then stalls past the eviction
        return PlayerTable(data="old")

    key = keys.report_player("Ev1", 1, "DamageDone", 1, 0, "Friendlies")
    load = asyncio.create_task(get_or_load(CacheFamily.REPORT_PLAYER, key, PlayerTable, slow_loader))
    await started.wait()
    await evict_report("Ev1")
    release.set()
    assert (await load) is not None  # the caller still gets its value
    assert await fake_redis.get(key) is None


async def test_writes_for_other_reports_and_families_are_unaffected(fake_redis):
    await evict_report("Ev2")

    async def loader():
        return PlayerTable(data=1)

    other = keys.report_player("Ev3", 1, "DamageDone", 1, 0, "Friendlies")
    assert await get_or_load(CacheFamily.REPORT_PLAYER, other, PlayerTable, loader) is not None
    assert await fake_redis.get(other) is not None
    assert await fake_redis.get(keys.gone("Ev2")) is not None
    assert await fake_redis.pttl(keys.gone("Ev2")) > 0  # a short marker, not a permanent ban
