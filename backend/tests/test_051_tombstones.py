"""Private-report tombstones can't be flushed, and gone signals aren't dropped (feature 051, sc-353).

A flood of made-up gone codes past the tombstone cap keeps a real tombstone's protection (the
floor); a full write queue still delivers gone and private signals; a null report entry of a
stored batch summary is a gone signal; the tombstones stay within their stated bound.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from backend.app.db.models import RawFetch
from backend.app.services import fetch_persistence
from backend.app.services.fetch_persistence import FetchWriter, PendingWrite, store_batch
from wcl_agent.client.queries import REPORT_SUMMARY, report_summaries_query
from wcl_agent.client.wcl_client import FetchedResponse, ReportGone, _flight_key

TABLE_Q = "query ReportQ($code: String!) { reportData { report(code: $code) { table } } }"


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(fetch_persistence, "_tombstones", type(fetch_persistence._tombstones)())


def fetched(query, variables, data, at, requested_at=None) -> FetchedResponse:
    body = json.dumps({"data": data}).encode()
    return FetchedResponse(_flight_key(query, variables), query, variables, body, at, requested_at)


def report(code: str, visibility: str) -> dict:
    return {"code": code, "visibility": visibility, "title": "Raid", "startTime": 1, "endTime": 2,
            "zone": {"id": 1, "name": "Zone"}, "guild": {"name": "G"}, "masterData": {"actors": []}, "fights": []}


def table(code: str, at: datetime, requested_at: datetime) -> FetchedResponse:
    return fetched(TABLE_Q, {"code": code}, {"reportData": {"report": {"table": "t"}}}, at, requested_at)


async def stored(factory, code: str) -> int:
    async with factory() as session:
        return await session.scalar(select(func.count()).select_from(RawFetch).where(RawFetch.report_code == code))


# --- AC1: a flood can't flush a real tombstone inside the in-flight window --------------------


async def test_a_flood_past_the_cap_keeps_the_real_tombstones_protection(patched_db, tenant_id):
    now = datetime.now(UTC)
    seen = now - timedelta(seconds=30)
    await store_batch([PendingWrite(ReportGone(("Real1",), seen))])
    flood = [f"Fake{i}" for i in range(fetch_persistence.TOMBSTONE_MAX + 5)]
    await store_batch([PendingWrite(ReportGone((c,), seen + timedelta(seconds=1))) for c in flood[:20]])
    fetch_persistence._bury(flood[20:], seen + timedelta(seconds=2))
    assert "Real1" not in fetch_persistence._tombstones  # evicted by the cap ...
    assert len(fetch_persistence._tombstones) == fetch_persistence.TOMBSTONE_MAX

    late = table("Real1", now, requested_at=seen - timedelta(seconds=5))  # ... but its fetch under way
    result = await store_batch([PendingWrite(late, tenant_id)])
    assert result.changed == [] and await stored(patched_db, "Real1") == 0  # is still not written


async def test_a_fetch_requested_after_the_flood_is_written(patched_db, tenant_id):
    now = datetime.now(UTC)
    fetch_persistence._bury([f"Fake{i}" for i in range(fetch_persistence.TOMBSTONE_MAX + 1)], now - timedelta(seconds=10))
    fresh = table("After1", now, requested_at=now - timedelta(seconds=1))
    await store_batch([PendingWrite(fresh, tenant_id)])
    assert await stored(patched_db, "After1") == 1


def test_expired_tombstones_leave_no_floor_and_the_bound_holds():
    now = datetime.now(UTC)
    fetch_persistence._bury(["Old1"], now - fetch_persistence.TOMBSTONE_TTL - timedelta(seconds=1))
    fetch_persistence._bury(["x" * 33, "", "New1"], now)  # over-long and empty codes are never served
    assert list(fetch_persistence._tombstones) == ["New1"] and fetch_persistence._tombstones.floor is None


# --- AC2: gone/private signals survive a full queue -----------------------------------------


@pytest.fixture
def blocked_writer():
    """A writer whose store holds the first batch until released, recording every item."""
    entered, release = asyncio.Event(), asyncio.Event()
    written: list[object] = []

    async def store(batch):
        written.extend(p.item for p in batch)
        entered.set()
        await release.wait()

    writer = FetchWriter(store, max_items=1, max_bytes=1 << 20)
    return writer, entered, release, written


async def test_a_gone_signal_is_queued_when_the_queue_is_full(blocked_writer):
    writer, entered, release, written = blocked_writer
    now = datetime.now(UTC)
    writer.start()
    writer.offer(table("Q0", now, now))
    await entered.wait()  # Q0 is being written; the queue holds one more fetch
    writer.offer(table("Q1", now, now))
    writer.offer(table("Q2", now, now))  # full: dropped
    writer.offer(ReportGone(("Gone1",), now))  # full, but a signal: kept
    release.set()
    await writer.stop()
    assert writer.dropped == 1
    assert [i.codes for i in written if isinstance(i, ReportGone)] == [("Gone1",)]


async def test_a_dropped_summary_still_sends_its_private_and_null_codes(blocked_writer):
    writer, entered, release, written = blocked_writer
    now = datetime.now(UTC)
    writer.start()
    writer.offer(table("Q0", now, now))
    await entered.wait()
    writer.offer(table("Q1", now, now))  # fills the queue
    variables = {"c0": "Prv1", "c1": "Pub1", "c2": "Null1"}
    batch = fetched(report_summaries_query(3), variables,
                    {"reportData": {"r0": report("Prv1", "private"), "r1": report("Pub1", "public"), "r2": None}}, now)
    writer.offer(batch)  # dropped as a write ...
    writer.offer(fetched(REPORT_SUMMARY, {"code": "Pub2"}, {"reportData": {"report": report("Pub2", "public")}}, now))
    release.set()
    await writer.stop()
    assert writer.dropped == 2
    gone = [i for i in written if isinstance(i, ReportGone)]
    assert [(g.codes, g.seen_at) for g in gone] == [(("Prv1", "Null1"), now)]  # ... its signal is not
    assert batch not in written


async def test_a_dropped_summary_without_a_finding_is_not_kept(blocked_writer):
    """P7 SEC-004: only a body that can hold a private or null finding is kept for parsing."""
    writer, entered, release, _ = blocked_writer
    now = datetime.now(UTC)
    writer.start()
    writer.offer(table("Q0", now, now))
    await entered.wait()
    writer.offer(table("Q1", now, now))
    writer.offer(fetched(REPORT_SUMMARY, {"code": "Pub4"}, {"reportData": {"report": report("Pub4", "public")}}, now))
    assert writer.dropped == 1 and not writer._salvaging
    writer.offer(fetched(REPORT_SUMMARY, {"code": "Prv4"}, {"reportData": {"report": report("Prv4", "private")}}, now))
    assert len(writer._salvaging) == 1
    release.set()
    await writer.stop()


async def test_a_dropped_summary_signal_deletes_the_rows_end_to_end(patched_db, tenant_id):
    now = datetime.now(UTC)
    t0 = now - timedelta(minutes=1)
    await store_batch([PendingWrite(table("Prv3", t0, t0), tenant_id)])
    entered, release = asyncio.Event(), asyncio.Event()

    async def held_then_real(batch):
        if not entered.is_set():
            entered.set()
            await release.wait()
            return None
        return await store_batch(batch)

    writer = FetchWriter(held_then_real, max_items=1, max_bytes=1 << 20)
    writer.start()
    writer.offer(table("Q0", now, now))
    await entered.wait()
    writer.offer(table("Q1", now, now))
    writer.offer(fetched(REPORT_SUMMARY, {"code": "Prv3"}, {"reportData": {"report": report("Prv3", "private")}}, now))
    release.set()
    await writer.stop()
    assert await stored(patched_db, "Prv3") == 0 and "Prv3" in fetch_persistence._tombstones


# --- AC3: a null batch entry is a gone signal -----------------------------------------------


async def test_a_null_batch_entry_deletes_and_tombstones_the_report(patched_db, tenant_id):
    now = datetime.now(UTC)
    t0 = now - timedelta(minutes=1)
    await store_batch([PendingWrite(table("Null2", t0, t0), tenant_id)])
    variables = {"c0": "Pub3", "c1": "Null2"}
    batch = fetched(report_summaries_query(2), variables, {"reportData": {"r0": report("Pub3", "public"), "r1": None}}, now)
    result = await store_batch([PendingWrite(batch, tenant_id)])
    assert result.gone == ["Null2"]
    assert await stored(patched_db, "Null2") == 0 and "Null2" in fetch_persistence._tombstones
    assert "Pub3" not in fetch_persistence._tombstones


async def test_a_null_entry_of_a_hand_written_query_is_no_signal(patched_db, tenant_id):
    now = datetime.now(UTC)
    t0 = now - timedelta(minutes=1)
    await store_batch([PendingWrite(table("Null3", t0, t0), tenant_id)])
    forged = "query ReportsBatch($c0: String!) { reportData { r0: report(code: $c0) { code } } }"
    result = await store_batch([PendingWrite(fetched(forged, {"c0": "Null3"}, {"reportData": {"r0": None}}, now), tenant_id)])
    assert result.gone == [] and await stored(patched_db, "Null3") == 2  # the table row stays (and the forged row)


def test_tombstone_entries_are_bounded():
    now = datetime.now(UTC)
    fetch_persistence._bury([uuid.uuid4().hex for _ in range(3 * fetch_persistence.TOMBSTONE_MAX)], now)
    assert len(fetch_persistence._tombstones) == fetch_persistence.TOMBSTONE_MAX
    assert fetch_persistence._tombstones.floor == now


def test_a_fetch_after_the_floor_is_not_parsed_once_the_tombstones_are_gone(monkeypatch):
    """PERF-008: a floor long past and no tombstones left: no query parsing per write."""
    now = datetime.now(UTC)
    fetch_persistence._tombstones.floor = now - timedelta(hours=1)
    parsed: list[str] = []
    monkeypatch.setattr(fetch_persistence, "stored_codes", lambda q, v: parsed.append(q) or ["X1"])
    assert not fetch_persistence._stale(table("X1", now, requested_at=now))
    assert parsed == []
    assert fetch_persistence._stale(table("X1", now, requested_at=now - timedelta(hours=2)))  # under it: stale
