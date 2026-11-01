"""DB-first reads (feature 039, sc-129; contracts/raw-store.md S7/S8, V2).

A real ``AsyncWCLClient`` over a mock transport counts the Warcraft Logs calls; the store is
the SQLite test DB, filled through the real writer path (``store_batch``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from backend.app.db import session as db_session
from backend.app.services import raw_fetch_reads
from backend.app.services.fetch_persistence import PendingWrite, store_batch
from backend.app.services.raw_fetch_reads import is_fresh, read_stored_fetch
from backend.app.repositories.raw_fetches import ReportStatus
from backend.app.tenancy.context import RequestIdentity, current_identity
from backend.tests.wcl_fakes import gql_response, mock_async_client
from wcl_agent.cache.cache import keys
from wcl_agent.client import wcl_client
from wcl_agent.client.queries import REPORT_SUMMARY
from wcl_agent.client.wcl_client import FetchedResponse, _flight_key
from wcl_agent.tools.report_tools import load_report_summary

NOW = datetime.now(UTC)
ENDED = int((NOW - timedelta(days=3)).timestamp() * 1000)  # finished long ago
LIVE = int(NOW.timestamp() * 1000)  # still being logged
TABLE_Q = "query ReportQ($code: String!) { reportData { report(code: $code) { table } } }"
STORED = {"reportData": {"report": {"table": "stored"}}}
NETWORK = {"data": {"reportData": {"report": {"table": "network"}}}}


def fetched(query: str, variables: dict, data: dict, at: datetime = NOW) -> FetchedResponse:
    body = json.dumps({"data": {"_cost": {"pointsSpentThisHour": 1}, **data}}).encode()
    return FetchedResponse(_flight_key(query, variables), query, variables, body, at)


def summary(code: str, end: int, at: datetime = NOW, visibility: str = "unlisted") -> FetchedResponse:
    report = {
        "code": code, "visibility": visibility, "title": "Raid", "startTime": end - 1000, "endTime": end,
        "zone": {"id": 1, "name": "Zone"}, "guild": {"name": "G"}, "masterData": {"actors": []}, "fights": [],
    }
    return fetched(REPORT_SUMMARY, {"code": code}, {"reportData": {"report": report}}, at)


@contextlib.contextmanager
def turn(tenant: uuid.UUID | None):
    token = current_identity.set(
        RequestIdentity(uuid.uuid4(), tenant, "member", False, uuid.uuid4()) if tenant else None
    )
    try:
        yield
    finally:
        current_identity.reset(token)


@pytest.fixture(autouse=True)
def closed_breaker(monkeypatch):
    """The breaker is process-wide: every test starts (and leaves others) with it closed."""
    monkeypatch.setattr(raw_fetch_reads, "breaker", raw_fetch_reads.Breaker())


@pytest.fixture
def wcl(monkeypatch):
    """The store installed as the client's source, and a network that counts its calls."""
    monkeypatch.setattr(wcl_client, "_fetch_sink", None)
    monkeypatch.setattr(wcl_client, "_fetch_source", read_stored_fetch)
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        await asyncio.sleep(0.02)
        return gql_response(NETWORK)

    client = mock_async_client(handler)
    monkeypatch.setattr(wcl_client, "get_async_client", lambda: client)
    yield client, calls


async def seed(code: str, tenant: uuid.UUID, *, end: int = ENDED, row_at: datetime = NOW) -> FetchedResponse:
    row = fetched(TABLE_Q, {"code": code}, STORED, row_at)
    await store_batch([PendingWrite(summary(code, end)), PendingWrite(row, tenant)])
    return row


# --- AC1: finished data from the store, live data refetched ------------------------------


async def test_a_finished_reports_data_is_served_with_no_wcl_call(patched_db, wcl, tenant_id):
    client, calls = wcl
    await seed("Fin1", tenant_id)
    with turn(tenant_id):
        assert await client.query(TABLE_Q, {"code": "Fin1"}) == {"data": STORED}
    assert calls["n"] == 0


async def test_live_data_is_served_only_inside_the_live_window(patched_db, wcl, tenant_id):
    client, calls = wcl
    await seed("Live1", tenant_id, end=LIVE, row_at=NOW - timedelta(minutes=5))
    await seed("Live2", tenant_id, end=LIVE, row_at=NOW - timedelta(seconds=30))
    with turn(tenant_id):
        assert await client.query(TABLE_Q, {"code": "Live1"}) == NETWORK  # stale: refetched
        assert await client.query(TABLE_Q, {"code": "Live2"}) == {"data": STORED}
    assert calls["n"] == 1


async def test_a_row_fetched_before_the_report_finished_is_not_final(patched_db, wcl, tenant_id):
    client, calls = wcl
    end = int((NOW - timedelta(hours=3)).timestamp() * 1000)  # finished an hour ago...
    await seed("Early1", tenant_id, end=end, row_at=NOW - timedelta(hours=2, minutes=30))  # ...row before
    with turn(tenant_id):
        assert await client.query(TABLE_Q, {"code": "Early1"}) == NETWORK
    assert calls["n"] == 1


def test_freshness_rules():
    old = NOW - timedelta(days=1)
    final = ReportStatus("A", "public", ENDED, NOW)
    seen_live = ReportStatus("A", "public", ENDED, datetime.fromtimestamp(ENDED / 1000, UTC))
    assert is_fresh(old, [final], now=NOW)
    assert not is_fresh(old, [seen_live], now=NOW)  # last seen while it was still live
    assert not is_fresh(old, [final, None], now=NOW)  # a report WCL never described
    assert not is_fresh(NOW, [], now=NOW)  # non-report data is never served


# --- AC2: a hidden row is a miss -----------------------------------------------------------


async def test_a_row_the_tenant_may_not_see_is_a_miss(patched_db, wcl, tenant_id, other_tenant_id):
    client, calls = wcl
    await seed("Hid1", tenant_id)
    with turn(other_tenant_id):
        assert await client.query(TABLE_Q, {"code": "Hid1"}) == NETWORK
    with turn(None):  # no signed-in turn: public reports only
        assert await client.query(TABLE_Q, {"code": "Hid1"}) == NETWORK
    assert calls["n"] == 2


async def test_a_joined_caller_of_another_tenant_never_rides_the_first_callers_store_hit(
    patched_db, wcl, tenant_id, other_tenant_id
):
    client, calls = wcl
    await seed("Share1", tenant_id)

    async def as_tenant(tenant):
        with turn(tenant):
            return await client.query(TABLE_Q, {"code": "Share1"})

    mine, theirs = await asyncio.gather(as_tenant(tenant_id), as_tenant(other_tenant_id))
    assert mine == {"data": STORED} and theirs == NETWORK and calls["n"] == 1


# --- AC3: a store hit of a public report back-fills Redis (045 sc-296: only a public one) ---


async def test_a_store_hit_back_fills_redis(patched_db, wcl, fake_redis, monkeypatch, tenant_id):
    _, calls = wcl
    await store_batch([PendingWrite(summary("Redis1", ENDED, visibility="public"), tenant_id)])
    reads = {"n": 0}

    class Counting(raw_fetch_reads.StoreSource):
        async def __call__(self, *args):
            reads["n"] += 1
            return await read_stored_fetch(*args)

    monkeypatch.setattr(wcl_client, "_fetch_source", Counting())
    with turn(tenant_id):
        first = await load_report_summary("Redis1")
        second = await load_report_summary("Redis1")
    assert first is not None and first.title == "Raid" and second == first
    assert calls["n"] == 0 and reads["n"] == 1  # the second read was a Redis hit
    assert await fake_redis.get(keys.report_summary("Redis1")) is not None


# --- AC4: a store failure falls back to WCL ------------------------------------------------


async def test_a_store_error_falls_back_to_wcl(patched_db, wcl, monkeypatch, tenant_id):
    client, calls = wcl
    await seed("Err1", tenant_id)

    def broken():
        raise OSError("database down")

    monkeypatch.setattr(db_session, "SessionLocal", broken)
    with turn(tenant_id):
        assert await client.query(TABLE_Q, {"code": "Err1"}) == NETWORK
    assert calls["n"] == 1


async def test_a_slow_store_falls_back_to_wcl_within_the_timeout(patched_db, wcl, monkeypatch, tenant_id):
    client, calls = wcl
    monkeypatch.setattr(raw_fetch_reads.settings, "raw_store_probe_timeout_ms", 50)

    @contextlib.asynccontextmanager
    async def hung():
        await asyncio.Event().wait()
        yield

    monkeypatch.setattr(db_session, "SessionLocal", hung)
    with turn(tenant_id):
        assert await asyncio.wait_for(client.query(TABLE_Q, {"code": "Slow1"}), 1.0) == NETWORK
    assert calls["n"] == 1


# --- AC5: no source (CLI, evals) and non-report queries --------------------------------------


async def test_without_a_source_the_client_is_unchanged(patched_db, wcl, monkeypatch, tenant_id):
    client, calls = wcl
    await seed("Cli1", tenant_id)
    monkeypatch.setattr(wcl_client, "_fetch_source", None)  # the CLI / eval path
    with turn(tenant_id):
        assert await client.query(TABLE_Q, {"code": "Cli1"}) == NETWORK
    assert calls["n"] == 1


async def test_a_non_report_query_never_touches_the_store(wcl, monkeypatch, tenant_id):
    client, calls = wcl

    def must_not_open():
        raise AssertionError("the store was read")

    monkeypatch.setattr(db_session, "SessionLocal", must_not_open)
    with turn(tenant_id):
        await client.query("{ worldData { zones { id } } }")
    assert calls["n"] == 1


async def test_a_store_hit_is_never_offered_again(patched_db, wcl, monkeypatch, tenant_id):
    client, _ = wcl
    await seed("Once1", tenant_id)
    offered: list = []
    monkeypatch.setattr(wcl_client, "_fetch_sink", offered.append)
    with turn(tenant_id):
        await client.query(TABLE_Q, {"code": "Once1"})
    assert offered == []
