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
from backend.app.services.fetch_persistence import FetchWriter, store_fetch
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
    stored: list[FetchedResponse] = []

    async def recording(fetched):
        stored.append(fetched)
        await store_fetch(fetched)

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
    assert len(failed) == 1  # throttled: one warning for three failed writes
    assert writer.dropped == 0  # failures are not drops


async def test_a_raising_store_never_reaches_the_caller(monkeypatch, caplog):
    async def broken(fetched):
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

    async def blocked(fetched):
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

    async def recording(fetched):
        stored.append(fetched.variables["code"])

    writer = FetchWriter(recording, max_items=10, max_bytes=300)
    writer.start()
    writer.offer(item("small", size=10))
    writer.offer(item("big", size=500))
    await writer.stop()
    assert stored == ["small"] and writer.dropped == 1


# --- shutdown (FR-011) -----------------------------------------------------------


async def test_stop_drains_the_queue_in_time():
    stored: list[str] = []

    async def recording(fetched):
        await asyncio.sleep(0.01)
        stored.append(fetched.variables["code"])

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
    async def stuck(fetched):
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

    async def recording(fetched):
        stored.append(fetched.variables["code"])

    writer = FetchWriter(recording, max_items=10, max_bytes=1 << 20)
    writer.start()
    await asyncio.to_thread(writer.offer, item("thread"))
    await asyncio.sleep(0)  # let the hopped call run
    await writer.stop()
    assert stored == ["thread"]
