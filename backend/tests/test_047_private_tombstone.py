"""A report found private by a summary stays gone after a race (feature 047, sc-322).

A table fetch is sent while the report is still visible; a summary then finds it private; the
table answer arrives after that. The stale answer must not be written, so the tenant's old grant
(kept by design, 039 R7) has nothing to serve.
"""

from __future__ import annotations

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
from wcl_agent.client.queries import REPORT_SUMMARY, report_summaries_query
from wcl_agent.client.wcl_client import FetchedResponse, _flight_key

NOW = datetime.now(UTC)
ENDED = int((NOW - timedelta(days=3)).timestamp() * 1000)
TABLE_Q = "query ReportQ($code: String!) { reportData { report(code: $code) { table } } }"


def fetched(query, variables, data, at, requested_at=None) -> FetchedResponse:
    body = json.dumps({"data": data}).encode()
    return FetchedResponse(_flight_key(query, variables), query, variables, body, at, requested_at)


def report(code: str, visibility: str) -> dict:
    return {"code": code, "visibility": visibility, "title": "Raid", "startTime": ENDED - 1000, "endTime": ENDED,
            "zone": {"id": 1, "name": "Zone"}, "guild": {"name": "G"}, "masterData": {"actors": []}, "fights": []}


def summary(code: str, visibility: str, at: datetime) -> FetchedResponse:
    return fetched(REPORT_SUMMARY, {"code": code}, {"reportData": {"report": report(code, visibility)}}, at)


def table(code: str, value: str, at: datetime, requested_at: datetime) -> FetchedResponse:
    return fetched(TABLE_Q, {"code": code}, {"reportData": {"report": {"table": value}}}, at, requested_at)


@contextlib.contextmanager
def turn(tenant: uuid.UUID):
    token = current_identity.set(RequestIdentity(uuid.uuid4(), tenant, "member", False, uuid.uuid4()))
    try:
        yield
    finally:
        current_identity.reset(token)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(raw_fetch_reads, "breaker", raw_fetch_reads.Breaker())
    monkeypatch.setattr(fetch_persistence, "_tombstones", type(fetch_persistence._tombstones)())


async def counts(factory, code: str) -> tuple[int, int]:
    async with factory() as session:
        fetches = await session.scalar(select(func.count()).select_from(RawFetch).where(RawFetch.report_code == code))
        grants = await session.scalar(
            select(func.count()).select_from(RawFetchGrant).where(RawFetchGrant.report_code == code)
        )
    return fetches, grants


async def served(tenant: uuid.UUID, code: str) -> bytes | None:
    with turn(tenant):
        found = await read_stored_fetch(_flight_key(TABLE_Q, {"code": code}), TABLE_Q, {"code": code})
    return None if found is None else found.content


async def test_a_table_fetch_under_way_when_a_summary_finds_the_report_private_is_not_written(
    patched_db, tenant_id
):
    t0 = NOW - timedelta(minutes=2)
    # The tenant saw the report while it was visible: a stored table and a grant.
    await store_batch([
        PendingWrite(summary("Prv1", "unlisted", t0), tenant_id),
        PendingWrite(table("Prv1", "old", t0, t0), tenant_id),
    ])
    assert await served(tenant_id, "Prv1") is not None  # the read path really serves it

    sent = NOW - timedelta(seconds=30)  # a new table request goes out ...
    await store_batch([PendingWrite(summary("Prv1", "private", NOW - timedelta(seconds=20)), tenant_id)])
    assert await counts(patched_db, "Prv1") == (0, 1)  # ... the summary drops the rows; the grant stays
    late = table("Prv1", "stale", NOW - timedelta(seconds=5), requested_at=sent)  # ... and answers late
    result = await store_batch([PendingWrite(late, tenant_id)])

    assert result.changed == []
    assert await counts(patched_db, "Prv1") == (0, 1)
    assert await served(tenant_id, "Prv1") is None  # the old grant has nothing to serve


async def test_a_batch_summary_tombstones_each_private_code(patched_db, tenant_id):
    seen = NOW - timedelta(seconds=10)
    variables = {"c0": "Prv2", "c1": "Pub2"}
    batch = fetched(report_summaries_query(2), variables,
                    {"reportData": {"r0": report("Prv2", "private"), "r1": report("Pub2", "public")}}, seen)
    await store_batch([PendingWrite(batch, tenant_id)])
    assert set(fetch_persistence._tombstones) == {"Prv2"}
    late = table("Prv2", "stale", NOW, requested_at=seen - timedelta(seconds=1))
    await store_batch([PendingWrite(late, tenant_id)])
    assert (await counts(patched_db, "Prv2"))[0] == 0


async def test_a_table_requested_after_the_private_summary_is_written(patched_db, tenant_id):
    """Only fetches already under way are stale: a later one (the report came back) is stored."""
    seen = NOW - timedelta(seconds=10)
    await store_batch([PendingWrite(summary("Prv3", "private", seen), tenant_id)])
    fresh = table("Prv3", "new", NOW, requested_at=seen + timedelta(seconds=1))
    await store_batch([PendingWrite(fresh, tenant_id)])
    assert (await counts(patched_db, "Prv3"))[0] == 1
