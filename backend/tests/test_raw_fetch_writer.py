"""The background fetch writer (feature 020, contracts/fetch-sink.md W1-W5).

Write-through end to end (a real client over a mock transport, the SQLite test DB), error
isolation (DB down), a full queue that drops without blocking the fetch, and the shutdown
drain and timeout.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db import session as db_session
from backend.app.db.models import RawFetch
from backend.app.services.fetch_persistence import FetchWriter, PendingWrite, store_batch
from backend.tests.wcl_fakes import gql_response, mock_async_client
from wcl_agent.client import wcl_client
from wcl_agent.client.wcl_client import FetchedResponse
from wcl_agent.tools.report_tools import load_report_summary

LOGGER = "backend.app.services.fetch_persistence"
REPORT_Q = "query ReportQ($code: String!) { reportData { report(code: $code) { title } } }"
SUMMARY = {
    "title": "Raid",
    "startTime": 1,
    "endTime": 2,
    "zone": {"id": 1, "name": "Zone"},
    "guild": {"name": "G"},
    "masterData": {"actors": []},
    "fights": [],
}


@pytest.fixture(autouse=True)
def _restore_sink(monkeypatch):
    monkeypatch.setattr(wcl_client, "_fetch_sink", None)


def item(code: str = "X", size: int = 0) -> FetchedResponse:
    body = json.dumps({"data": {"pad": "x" * size}}).encode()
    return FetchedResponse(f"key-{code}", REPORT_Q, {"code": code}, body, datetime.now(UTC))


def report_client(monkeypatch):
    """A real client answering every report query; installed as the process's client."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return gql_response({"data": {"reportData": {"report": SUMMARY}}})

    client = mock_async_client(handler)
    monkeypatch.setattr(wcl_client, "get_async_client", lambda: client)
    return client, calls


def warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelno == logging.WARNING]


# --- write-through (US1, AC 2) ----------------------------------------------------


async def test_a_tool_fetch_is_written_through_to_the_table(patched_db, monkeypatch):
    client, _ = report_client(monkeypatch)
    writer = FetchWriter(max_items=10, max_bytes=1 << 20)
    writer.start()

    summary = await load_report_summary("aBcD1234")
    await writer.stop()
    await client.aclose()

    assert summary is not None and summary.title == "Raid"
    async with patched_db() as session:
        [row] = (await session.scalars(select(RawFetch))).all()
    assert row.operation_name == "ReportSummary" and row.report_codes == ["aBcD1234"]
    assert row.payload == {"data": {"reportData": {"report": SUMMARY}}}
    assert writer.dropped == 0


async def test_cache_hits_are_not_stored_again(patched_db, fake_redis, monkeypatch):
    client, calls = report_client(monkeypatch)
    stored: list[PendingWrite] = []

    async def recording(batch):
        stored.extend(batch)
        await store_batch(batch)

    writer = FetchWriter(recording, max_items=10, max_bytes=1 << 20)
    writer.start()
    await load_report_summary("CaCh3d")
    await load_report_summary("CaCh3d")  # served by the shared cache: never reaches WCL
    await writer.stop()
    await client.aclose()

    assert calls["n"] == 1 and len(stored) == 1


# --- error isolation (US2, AC 3) --------------------------------------------------


async def test_db_down_the_fetch_still_succeeds_and_failures_are_logged_once(monkeypatch, caplog):
    dead = create_async_engine("postgresql+asyncpg://wcl:wcl@127.0.0.1:1/wcl")
    monkeypatch.setattr(db_session, "SessionLocal", async_sessionmaker(dead, class_=AsyncSession))
    client, _ = report_client(monkeypatch)
    writer = FetchWriter(max_items=10, max_bytes=1 << 20)
    writer.start()

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        for code in ("D1", "D2", "D3"):
            assert (await client.query(REPORT_Q, {"code": code}))["data"]["reportData"]["report"] == SUMMARY
        await writer.stop()
    await client.aclose()
    await dead.dispose()

    failed = [m for m in warnings(caplog) if "write(s) failed" in m]
    # Throttled: the first failure at once, the other two flushed on stop (sc-177), never lost.
    assert [m.split(" write(s)")[0][-1] for m in failed] == ["1", "2"]
    assert writer.dropped == 0  # failures are not drops


async def test_a_raising_store_never_reaches_the_caller(monkeypatch, caplog):
    async def broken(batch):
        raise OSError("connection refused")

    client, _ = report_client(monkeypatch)
    writer = FetchWriter(broken, max_items=10, max_bytes=1 << 20)
    writer.start()
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        assert await client.query(REPORT_Q, {"code": "R1"})
        await writer.stop()
    await client.aclose()
    assert any("connection refused" in m for m in warnings(caplog))


# --- a full queue drops without blocking the fetch (PO condition, decision 17) ----


async def test_a_full_queue_drops_new_responses_without_blocking_the_fetch(monkeypatch, caplog):
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked(batch):
        entered.set()
        await release.wait()

    client, _ = report_client(monkeypatch)
    writer = FetchWriter(blocked, max_items=2, max_bytes=1 << 20)
    writer.start()

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        await client.query(REPORT_Q, {"code": "Q0"})
        await entered.wait()  # the writer holds Q0 and never finishes it
        started = time.perf_counter()
        for i in range(1, 5):
            await client.query(REPORT_Q, {"code": f"Q{i}"})
        elapsed = time.perf_counter() - started

    assert elapsed < 1.0  # the fetches never waited on the stuck writer
    assert writer.dropped == 2  # Q1, Q2 queued (max 2); Q3, Q4 dropped
    assert len([m for m in warnings(caplog) if "queue full" in m]) == 1
    release.set()
    await writer.stop()
    await client.aclose()


async def test_a_response_beyond_the_byte_budget_is_dropped():
    stored: list[str] = []

    async def recording(batch):
        stored.extend(p.item.variables["code"] for p in batch)

    writer = FetchWriter(recording, max_items=10, max_bytes=300)
    writer.start()
    writer.offer(item("small", size=10))
    writer.offer(item("big", size=500))
    await writer.stop()
    assert stored == ["small"] and writer.dropped == 1


# --- shutdown (FR-011) -----------------------------------------------------------


async def test_stop_drains_the_queue_in_time():
    stored: list[str] = []

    async def recording(batch):
        await asyncio.sleep(0.01)
        stored.extend(p.item.variables["code"] for p in batch)

    writer = FetchWriter(recording, max_items=10, max_bytes=1 << 20)
    writer.start()
    assert wcl_client._fetch_sink == writer.offer
    for code in ("A", "B", "C"):
        writer.offer(item(code))
    await writer.stop()

    assert stored == ["A", "B", "C"] and writer.dropped == 0
    assert wcl_client._fetch_sink is None
    writer.offer(item("late"))  # after stop: ignored, never raises
    assert stored == ["A", "B", "C"]


async def test_stop_gives_up_after_the_grace_period_and_counts_the_rest(caplog):
    async def stuck(batch):
        await asyncio.Event().wait()

    writer = FetchWriter(stuck, max_items=10, max_bytes=1 << 20)
    writer.start()
    for code in ("A", "B", "C"):
        writer.offer(item(code))
    await asyncio.sleep(0)  # the writer takes A

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        started = time.perf_counter()
        await writer.stop(0.2)
        elapsed = time.perf_counter() - started

    assert elapsed < 1.2
    assert writer.dropped == 3  # A in flight + B, C queued
    assert any("dropped 3 unwritten" in m for m in warnings(caplog))


# --- other threads (W5) -----------------------------------------------------------


async def test_an_offer_from_another_thread_is_delivered():
    stored: list[str] = []

    async def recording(batch):
        stored.extend(p.item.variables["code"] for p in batch)

    writer = FetchWriter(recording, max_items=10, max_bytes=1 << 20)
    writer.start()
    await asyncio.to_thread(writer.offer, item("thread"))
    await asyncio.sleep(0)  # let the hopped call run
    await writer.stop()
    assert stored == ["thread"]


# --- feature 039 / sc-177: batches, error isolation, safe logs -------------------------


async def test_queued_items_are_written_in_one_batch():
    entered, release = asyncio.Event(), asyncio.Event()
    batches: list[list[str]] = []

    async def recording(batch):
        batches.append([p.item.variables["code"] for p in batch])
        entered.set()
        await release.wait()

    writer = FetchWriter(recording, max_items=50, max_bytes=1 << 20)
    writer.start()
    writer.offer(item("first"))
    await entered.wait()  # the writer holds "first"; the rest queue up meanwhile
    for code in ("A", "B", "C", "D"):
        writer.offer(item(code))
    release.set()
    await writer.stop()
    assert batches == [["first"], ["A", "B", "C", "D"]]


async def test_one_bad_item_loses_only_itself(caplog):
    stored: list[str] = []
    entered, release = asyncio.Event(), asyncio.Event()

    async def picky(batch):
        codes = [p.item.variables["code"] for p in batch]
        if codes == ["hold"]:
            entered.set()
            await release.wait()
            return
        if "BAD" in codes:
            raise ValueError("bad row")
        stored.extend(codes)

    writer = FetchWriter(picky, max_items=50, max_bytes=1 << 20)
    writer.start()
    writer.offer(item("hold"))
    await entered.wait()
    for code in ("A", "BAD", "C"):
        writer.offer(item(code))
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        release.set()
        await writer.stop()
    assert stored == ["A", "C"]
    assert any("1 write(s) failed" in m and "bad row" in m for m in warnings(caplog))


async def test_a_database_error_is_logged_without_its_parameters(monkeypatch, caplog):
    bare = create_async_engine("sqlite+aiosqlite://")  # no tables: the INSERT fails
    monkeypatch.setattr(db_session, "SessionLocal", async_sessionmaker(bare, class_=AsyncSession))
    writer = FetchWriter(max_items=10, max_bytes=1 << 20)
    writer.start()
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        writer.offer(item("SeCrEtCoDe"))
        await writer.stop()
    await bare.dispose()
    [failed] = [m for m in warnings(caplog) if "write(s) failed" in m]
    assert "OperationalError" in failed
    assert "SeCrEtCoDe" not in failed and "parameters" not in failed and "INSERT" not in failed


async def test_pending_drop_counts_are_flushed_on_stop(caplog):
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked(batch):
        entered.set()
        await release.wait()

    writer = FetchWriter(blocked, max_items=1, max_bytes=1 << 20)
    writer.start()
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        writer.offer(item("held"))
        await entered.wait()
        writer.offer(item("queued"))
        for code in ("x", "y", "z"):
            writer.offer(item(code))  # first drop logs at once, the other two wait for the interval
        release.set()
        await writer.stop()
    drops = [m for m in warnings(caplog) if "queue full" in m]
    assert drops == ["fetch persistence: queue full, dropped 1 response(s)",
                     "fetch persistence: queue full, dropped 2 response(s)"]


# --- feature 045 (sc-295 PERF-005, contract 5): fewer round trips per item ---------------


PLAIN_Q = "query ReportQ($code: String!) { reportData { report(code: $code) { table } } }"


def granting(code: str, n: int, at: datetime | None = None) -> FetchedResponse:
    """A plain report query whose body holds the report: it grants ``code`` (041 fix 2)."""
    body = json.dumps({"data": {"reportData": {"report": {"table": n}}}}).encode()
    variables = {"code": code, "n": n}
    return FetchedResponse(f"grant-{code}-{n}", PLAIN_Q, variables, body, at or datetime.now(UTC))


async def test_a_batch_scopes_each_tenant_once_and_skips_grants_it_just_wrote(
    patched_db, monkeypatch, tenant_id, other_tenant_id
):
    from backend.app.repositories import raw_fetches
    from backend.app.services import fetch_persistence

    scopes: list = []
    grants: list = []
    real_grant = raw_fetches.grant_codes

    async def scope(session, tenant):
        scopes.append(tenant)

    async def grant(session, tenant, codes, at):
        grants.append((tenant, list(codes)))
        await real_grant(session, tenant, codes, at)

    monkeypatch.setattr(fetch_persistence, "scope_tenant", scope)
    monkeypatch.setattr(fetch_persistence, "grant_codes", grant)
    batch = [PendingWrite(granting("Pf1", i), tenant_id) for i in range(5)]
    batch += [PendingWrite(granting("Pf1", 9), other_tenant_id), PendingWrite(granting("Pf2", 1), tenant_id),
              PendingWrite(granting("Pf3", 1), tenant_id)]
    result = await store_batch(batch)
    assert scopes == [tenant_id, other_tenant_id, tenant_id]  # once per tenant switch, not per item
    assert grants == [(tenant_id, ["Pf1"]), (other_tenant_id, ["Pf1"]), (tenant_id, ["Pf2"]), (tenant_id, ["Pf3"])]
    assert len(result.changed) == 8 and result.gone == []


async def test_an_unchanged_body_is_not_reported_changed(patched_db):
    first = item("Same1")
    assert [i.query_key for i in (await store_batch([PendingWrite(first)])).changed] == [first.query_key]
    again = FetchedResponse(first.query_key, first.query, first.variables, first.content, datetime.now(UTC))
    assert (await store_batch([PendingWrite(again)])).changed == []


async def test_a_grant_younger_than_an_hour_is_not_rewritten(patched_db, tenant_id):
    from datetime import timedelta

    from backend.app.db.models import RawFetchGrant

    t0 = datetime.now(UTC) - timedelta(hours=3)
    await store_batch([PendingWrite(granting("Gr1", 1, t0), tenant_id)])
    await store_batch([PendingWrite(granting("Gr1", 2, t0 + timedelta(minutes=30)), tenant_id)])
    async with patched_db() as session:
        kept = await session.scalar(select(RawFetchGrant.granted_at))
    assert kept.replace(tzinfo=UTC) == t0  # 30 min newer: left alone
    await store_batch([PendingWrite(granting("Gr1", 3, t0 + timedelta(hours=2)), tenant_id)])
    async with patched_db() as session:
        moved = await session.scalar(select(RawFetchGrant.granted_at))
    assert moved.replace(tzinfo=UTC) == t0 + timedelta(hours=2)
