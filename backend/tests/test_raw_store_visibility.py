"""The raw store's visibility rule (feature 039, sc-178; contracts/raw-store.md V1, W6, W7).

SQLite: app-level scoping. The RLS on grants and the JSONB delete are proven on Postgres in
test_raw_store_pg.py.
"""

from __future__ import annotations

import json
import pathlib
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from backend.app.db.models import RawFetch, RawFetchGrant, RawReport
from backend.app.repositories.raw_fetches import read_visible_fetch
from backend.app.services.fetch_persistence import FetchWriter, PendingWrite, store_batch
from backend.app.tenancy.context import RequestIdentity, current_identity
from backend.tests.wcl_fakes import gql_response, mock_async_client
from wcl_agent.cache.cache import keys
from wcl_agent.client import wcl_client
from wcl_agent.client.queries import REPORT_SUMMARY, report_summaries_query
from wcl_agent.client.wcl_client import FetchedResponse, ReportGone, _flight_key

NOW = datetime.now(UTC)
SINCE = NOW - timedelta(days=7)
TABLE_Q = "query ReportQ($code: String!) { reportData { report(code: $code) { table } } }"
ALWAYS = lambda fetched_at, statuses: True  # noqa: E731 - freshness is not under test here


def fetched(query: str, variables: dict, data: dict, at: datetime = NOW) -> FetchedResponse:
    body = json.dumps({"data": {"_cost": {"pointsSpentThisHour": 1}, **data}}).encode()
    return FetchedResponse(_flight_key(query, variables), query, variables, body, at)


def summary(code: str, visibility: str = "unlisted", end: int = 1) -> FetchedResponse:
    report = {"code": code, "visibility": visibility, "title": "Raid", "endTime": end}
    return fetched(REPORT_SUMMARY, {"code": code}, {"reportData": {"report": report}})


def table(code: str, at: datetime = NOW) -> FetchedResponse:
    return fetched(TABLE_Q, {"code": code}, {"reportData": {"report": {"table": {"rows": [1]}}}}, at)


async def read(session, item: FetchedResponse, tenant: uuid.UUID | None, since: datetime = SINCE):
    return await read_visible_fetch(session, item.query_key, tenant_id=tenant, since=since, fresh=ALWAYS)


@pytest.fixture
def a(tenant_id) -> uuid.UUID:
    return tenant_id


@pytest.fixture
def b(other_tenant_id) -> uuid.UUID:
    return other_tenant_id


# --- AC1/AC5: who is served a stored row ----------------------------------------------


async def test_tenant_b_cant_read_a_row_only_tenant_a_references(patched_db, a, b):
    row = table("UnLiStEd1")
    await store_batch([PendingWrite(summary("UnLiStEd1")), PendingWrite(row, a)])
    async with patched_db() as session:
        assert await read(session, row, b) is None
        assert await read(session, row, None) is None  # no tenant: public only
        stored = await read(session, row, a)
    assert json.loads(stored) == {"data": {"reportData": {"report": {"table": {"rows": [1]}}}}}


async def test_a_public_report_row_is_shared_with_every_tenant(patched_db, a, b):
    row = table("PuBlIc1")
    await store_batch([PendingWrite(summary("PuBlIc1", "public")), PendingWrite(row, a)])
    async with patched_db() as session:
        assert await read(session, row, b) is not None
        assert await read(session, row, None) is not None


async def test_public_status_and_grants_expire_after_the_reverify_window(patched_db, a, b):
    old = NOW - timedelta(days=8)
    pub, own = table("OldPub"), table("OldOwn")
    await store_batch(
        [
            PendingWrite(fetched(REPORT_SUMMARY, {"code": "OldPub"},
                                 {"reportData": {"report": {"code": "OldPub", "visibility": "public"}}}, old)),
            PendingWrite(pub),
            PendingWrite(fetched(TABLE_Q, {"code": "OldOwn"}, {"reportData": {"report": {}}}, old), a),
            PendingWrite(own),
        ]
    )
    async with patched_db() as session:
        assert await read(session, pub, b) is None
        assert await read(session, own, a) is None


async def test_a_batch_row_is_served_only_when_every_report_is_visible(patched_db, a, b):
    query = report_summaries_query(2)
    batch = fetched(query, {"c0": "PubX", "c1": "SecretY"}, {"reportData": {
        "r0": {"code": "PubX", "visibility": "public"}, "r1": {"code": "SecretY", "visibility": "unlisted"}}})
    await store_batch([PendingWrite(batch, a)])
    async with patched_db() as session:
        assert await read(session, batch, a) is not None
        assert await read(session, batch, b) is None  # PubX is public, SecretY isn't


async def test_an_overlong_code_is_never_visible(patched_db, a):
    row = table("X" * 40)
    await store_batch([PendingWrite(row, a)])
    async with patched_db() as session:
        assert await session.scalar(select(func.count()).select_from(RawFetchGrant)) == 0
        assert await read(session, row, a) is None


async def test_a_fetch_outside_a_signed_in_turn_grants_nothing(patched_db):
    await store_batch([PendingWrite(table("NoTurn"))])
    async with patched_db() as session:
        assert await session.scalar(select(func.count()).select_from(RawFetchGrant)) == 0


async def test_a_hand_written_query_cant_forge_a_report_status_or_grant(patched_db, a, b):
    """``code: title`` aliasing or a commented-out ``report(code:`` must not make another
    tenant's report public or grant it (research R3, bypass attempt)."""
    forged = fetched(
        'query { reportData { report(code: "Mine") { code: title visibility } } }', {},
        {"reportData": {"report": {"code": "Victim", "visibility": "public"}}},
    )
    hidden = fetched('# report(code: "Victim")\nquery { reportData { report (code: "Mine") { t } } }', {}, {})
    await store_batch([PendingWrite(forged, b), PendingWrite(hidden, b)])
    async with patched_db() as session:
        assert await session.scalar(select(func.count()).select_from(RawReport)) == 0
        codes = set(await session.scalars(select(RawFetchGrant.report_code)))
    assert codes == set()  # neither is a plain query (literals, alias, comment): no grant (041)


# --- AC3: a private or deleted report goes, rows and Redis keys -------------------------


async def test_gone_deletes_every_row_naming_the_code_and_evicts_its_redis_keys(patched_db, fake_redis, a):
    other = table("Keep")
    batch = fetched(report_summaries_query(2), {"c0": "Gone1", "c1": "Keep"}, {"reportData": {}})
    await store_batch([PendingWrite(summary("Gone1", "public")), PendingWrite(table("Gone1"), a),
                       PendingWrite(batch, a), PendingWrite(other, a)])
    await fake_redis.set(keys.report_summary("Gone1"), b"{}")
    await fake_redis.set(keys.report_participants("Gone1", 3), b"{}")
    await fake_redis.set(keys.report_summary("Keep"), b"{}")

    writer = FetchWriter(max_items=10, max_bytes=1 << 20)  # evicts Redis after the DB part
    writer.start()
    writer.offer(ReportGone(("Gone1",), NOW))
    await writer.stop()

    async with patched_db() as session:
        left = set(await session.scalars(select(RawFetch.query_key)))
        assert left == {other.query_key}
        assert await session.get(RawReport, "Gone1") is None
    assert await fake_redis.keys("wcl:v1:report:Gone1:*") == []
    assert await fake_redis.get(keys.report_summary("Keep")) == b"{}"


async def test_a_summary_showing_private_deletes_the_report(patched_db, a):
    await store_batch([PendingWrite(table("Priv1"), a)])
    await store_batch([PendingWrite(summary("Priv1", "private"), a)])
    async with patched_db() as session:
        assert await session.scalar(select(func.count()).select_from(RawFetch)) == 0


async def test_eviction_treats_the_code_as_data_not_a_pattern(fake_redis):
    from wcl_agent.cache.cache import evict_report

    await fake_redis.set("wcl:v1:report:abc:summary", b"1")
    assert await evict_report("*") == 0 and await evict_report("a?c") == 0
    assert await fake_redis.get("wcl:v1:report:abc:summary") == b"1"


async def test_a_null_report_from_wcl_reaches_the_writer_and_deletes_the_rows(patched_db, monkeypatch, a):
    """End to end: the client sees ``report: null`` and the writer deletes the stored rows."""
    monkeypatch.setattr(wcl_client, "_fetch_sink", None)
    await store_batch([PendingWrite(table("Vanish"), a)])
    client = mock_async_client(lambda request: gql_response({"data": {"reportData": {"report": None}}}))
    writer = FetchWriter(max_items=10, max_bytes=1 << 20)
    writer.start()
    await client.query(REPORT_SUMMARY, {"code": "Vanish"})
    await writer.stop()
    await client.aclose()
    async with patched_db() as session:
        assert await session.scalar(select(func.count()).select_from(RawFetch)) == 0


async def test_the_writer_records_the_fetching_turns_tenant(patched_db, monkeypatch, a):
    monkeypatch.setattr(wcl_client, "_fetch_sink", None)
    report = {"code": "Turn1", "visibility": "unlisted", "endTime": 1}
    client = mock_async_client(lambda request: gql_response({"data": {"reportData": {"report": report}}}))
    writer = FetchWriter(max_items=10, max_bytes=1 << 20)
    writer.start()
    identity = RequestIdentity(uuid.uuid4(), a, "member", False, uuid.uuid4())
    token = current_identity.set(identity)
    try:
        await client.query(REPORT_SUMMARY, {"code": "Turn1"})
    finally:
        current_identity.reset(token)
    await writer.stop()
    await client.aclose()
    async with patched_db() as session:
        grant = (await session.scalars(select(RawFetchGrant))).one()
        status = await session.get(RawReport, "Turn1")
    assert (grant.tenant_id, grant.report_code) == (a, "Turn1")
    assert status.visibility == "unlisted" and status.end_time_ms == 1


# --- AC2: one read function --------------------------------------------------------------


def test_only_the_repository_reads_the_raw_store():
    """Any other module touching ``RawFetch`` could bypass the visibility rule."""
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    allowed = {root / "db" / "models.py", root / "repositories" / "raw_fetches.py"}
    offenders = []
    for path in root.rglob("*.py"):
        # The ORM model, or the table in raw SQL; importing the repository is fine.
        if path not in allowed and re.search(
            r"\bRawFetch\b|(?i:\b(?:from|join|update|into)\s+raw_fetches\b)", path.read_text()
        ):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []
