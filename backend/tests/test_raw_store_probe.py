"""The cheap, fail-fast raw-store probe (feature 045, sc-295).

The visibility clause (contract 3), the probe's statement budget, the breaker's transitions,
the probe counters, and the probe's place inside the WCL client's single-flight and lane slot.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, select

from backend.app.db import session as db_session
from backend.app.db.models import RawFetch
from backend.app.repositories import raw_fetches
from backend.app.repositories.raw_fetches import fetch_visible_clause, probe_visible_fetch
from backend.app.services import raw_fetch_reads
from backend.app.services.fetch_persistence import PendingWrite, store_batch
from backend.app.services.raw_fetch_reads import BREAKER_S, Breaker, read_stored_fetch
from backend.app.tenancy.context import RequestIdentity, current_identity
from backend.tests.wcl_fakes import gql_response, mock_async_client
from wcl_agent.cache import cache as wcl_cache
from wcl_agent.client import wcl_client
from wcl_agent.client.queries import REPORT_SUMMARY
from wcl_agent.client.wcl_client import FetchedResponse, StoredFetch, _flight_key

NOW = datetime.now(UTC)
SINCE = NOW - timedelta(days=1)
ENDED = int((NOW - timedelta(days=3)).timestamp() * 1000)
TABLE_Q = "query ReportQ($code: String!) { reportData { report(code: $code) { table } } }"
ALWAYS = lambda fetched_at, statuses: True  # noqa: E731
NEVER = lambda fetched_at, statuses: False  # noqa: E731


def fetched(query: str, variables: dict, data: dict, at: datetime = NOW) -> FetchedResponse:
    body = json.dumps({"data": {"_cost": {"pointsSpentThisHour": 1}, **data}}).encode()
    return FetchedResponse(_flight_key(query, variables), query, variables, body, at)


def summary(code: str, visibility: str = "unlisted", at: datetime = NOW) -> FetchedResponse:
    report = {"code": code, "visibility": visibility, "title": "Raid", "endTime": ENDED}
    return fetched(REPORT_SUMMARY, {"code": code}, {"reportData": {"report": report}}, at)


def table(code: str) -> FetchedResponse:
    return fetched(TABLE_Q, {"code": code}, {"reportData": {"report": {"table": code}}})


@contextlib.contextmanager
def turn(tenant: uuid.UUID | None):
    token = current_identity.set(
        RequestIdentity(uuid.uuid4(), tenant, "member", False, uuid.uuid4()) if tenant else None
    )
    try:
        yield
    finally:
        current_identity.reset(token)


@contextlib.contextmanager
def statements(factory):
    seen: list[str] = []

    def on(conn, cursor, statement, params, context, executemany):
        seen.append(statement)

    engine = factory.kw["bind"].sync_engine
    event.listen(engine, "before_cursor_execute", on)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", on)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(autouse=True)
def clock(monkeypatch) -> Clock:
    """A fresh breaker on a fake clock for every test (the breaker is process-wide)."""
    fake = Clock()
    monkeypatch.setattr(raw_fetch_reads, "breaker", Breaker(clock=fake))
    return fake


# --- Contract 3: the visibility clause -----------------------------------------------------


async def visible(session, item: FetchedResponse, tenant: uuid.UUID | None, since: datetime = SINCE) -> bool:
    return bool(await session.scalar(select(fetch_visible_clause(item.query_key, tenant_id=tenant, since=since))))


async def test_the_clause_is_the_039_rule(patched_db, tenant_id, other_tenant_id):
    own, pub, mixed = table("Own1"), table("Pub1"), fetched(
        "query B($a: String!, $b: String!) { reportData { x: report(code: $a) { t } y: report(code: $b) { t } } }",
        {"a": "Own1", "b": "Pub1"}, {"reportData": {}},
    )
    await store_batch([
        PendingWrite(summary("Own1")), PendingWrite(summary("Pub1", "public")),
        PendingWrite(own, tenant_id), PendingWrite(pub, tenant_id), PendingWrite(mixed),
    ])
    async with patched_db() as session:
        assert await visible(session, own, tenant_id)  # granted
        assert not await visible(session, own, other_tenant_id)
        assert not await visible(session, own, None)
        assert await visible(session, pub, other_tenant_id) and await visible(session, pub, None)  # public
        assert await visible(session, mixed, tenant_id)  # every code: one public, one granted
        assert not await visible(session, mixed, other_tenant_id)  # one code hidden hides the row
        assert not await visible(session, own, tenant_id, since=NOW + timedelta(seconds=1))  # expired
        assert not await visible(session, pub, None, since=NOW + timedelta(seconds=1))
        assert not await visible(session, table("Absent"), tenant_id)  # no row


async def test_the_clause_refuses_rows_naming_no_report_or_overlong_codes(patched_db, tenant_id):
    long_code = "L" * (raw_fetches.MAX_CODE + 1)
    anon = fetched("{ worldData { zones { id } } }", {}, {"worldData": {}})
    overlong = table(long_code)
    await store_batch([PendingWrite(anon, tenant_id), PendingWrite(summary(long_code, "public")),
                       PendingWrite(overlong, tenant_id)])
    async with patched_db() as session:
        assert not await visible(session, anon, tenant_id)
        assert not await visible(session, overlong, tenant_id)


async def test_the_clause_takes_a_column(patched_db, tenant_id, other_tenant_id):
    """044 joins its chunks through the clause by column; here the row joins itself."""
    own, pub = table("Col1"), table("Col2")
    await store_batch([PendingWrite(summary("Col1")), PendingWrite(summary("Col2", "public")),
                       PendingWrite(own, tenant_id), PendingWrite(pub, tenant_id)])
    async with patched_db() as session:
        keys = set(await session.scalars(select(RawFetch.query_key).where(
            fetch_visible_clause(RawFetch.query_key, tenant_id=other_tenant_id, since=SINCE)
        )))
    assert keys == {pub.query_key, summary("Col2").query_key}  # the public report's rows only


# --- AC2: the statement budget ----------------------------------------------------------------


async def probe(session, item, tenant, fresh=ALWAYS):
    return await probe_visible_fetch(session, item.query_key, tenant_id=tenant, since=SINCE, fresh=fresh)


async def test_a_miss_costs_one_statement_and_sets_no_scope(patched_db, monkeypatch, tenant_id):
    scoped: list = []
    monkeypatch.setattr(raw_fetches, "scope_tenant", lambda *a: scoped.append(a))
    async with patched_db() as session:
        with statements(patched_db) as seen:
            result = await probe(session, table("None1"), tenant_id)
    assert result.outcome == "miss" and len(seen) == 1 and scoped == []


async def test_a_stale_row_costs_two_statements(patched_db, tenant_id):
    row = table("Stale1")
    await store_batch([PendingWrite(summary("Stale1")), PendingWrite(row, tenant_id)])
    async with patched_db() as session:
        with statements(patched_db) as seen:
            result = await probe(session, row, tenant_id, fresh=NEVER)
    assert result.outcome == "miss" and len(seen) == 2


async def test_a_hit_fetches_visibility_and_payload_in_one_statement(patched_db, monkeypatch, tenant_id):
    scoped: list = []

    async def scope(session, tenant):
        scoped.append(tenant)

    monkeypatch.setattr(raw_fetches, "scope_tenant", scope)
    own, pub = table("Hit1"), table("Hit2")
    await store_batch([PendingWrite(summary("Hit1")), PendingWrite(summary("Hit2", "public")),
                       PendingWrite(own, tenant_id), PendingWrite(pub, tenant_id)])
    async with patched_db() as session:
        with statements(patched_db) as seen:
            granted = await probe(session, own, tenant_id)
        assert granted.outcome == "hit" and not granted.shared and len(seen) == 3  # + set_config on PG
        assert json.loads(granted.body) == {"data": {"reportData": {"report": {"table": "Hit1"}}}}
        assert scoped == [tenant_id]  # a grant was needed: scope set once
        with statements(patched_db) as seen:
            public = await probe(session, pub, tenant_id)
        assert public.outcome == "hit" and public.shared and len(seen) == 3
        assert scoped == [tenant_id]  # every code public: no scope
        assert isinstance(public.body, bytes)  # PERF-006: no text decode on the loop


async def test_an_invisible_row_is_not_visible_and_carries_no_body(patched_db, tenant_id, other_tenant_id):
    row = table("Inv1")
    await store_batch([PendingWrite(summary("Inv1")), PendingWrite(row, tenant_id)])
    async with patched_db() as session:
        result = await probe(session, row, other_tenant_id)
    assert result.outcome == "not_visible" and result.body is None


async def test_a_row_replaced_between_the_statements_is_a_miss(patched_db, monkeypatch, tenant_id):
    row = table("Swap1")
    await store_batch([PendingWrite(summary("Swap1", "public")), PendingWrite(row, tenant_id)])

    def fresh(fetched_at, statuses):  # runs between the lookup and the payload statement
        return True

    async with patched_db() as session:
        real_execute = session.execute
        calls = {"n": 0}

        async def execute(stmt, *a, **kw):
            calls["n"] += 1
            if calls["n"] == 3:  # the payload statement: the writer replaced the row just before
                async with patched_db() as other:
                    from sqlalchemy import update

                    await other.execute(update(RawFetch).values(fetched_at=NOW + timedelta(seconds=5)))
                    await other.commit()
            return await real_execute(stmt, *a, **kw)

        monkeypatch.setattr(session, "execute", execute)
        result = await probe(session, row, tenant_id, fresh=fresh)
    assert result.outcome == "miss"


# --- AC1: timeout and breaker -----------------------------------------------------------------


@contextlib.asynccontextmanager
async def hung():
    await asyncio.Event().wait()
    yield


async def source(item: FetchedResponse) -> StoredFetch | None:
    return await read_stored_fetch(item.query_key, item.query, item.variables)


async def test_a_hung_store_costs_one_timeout_then_the_breaker_skips_it(monkeypatch, clock, tenant_id):
    monkeypatch.setattr(raw_fetch_reads.settings, "raw_store_probe_timeout_ms", 50)
    opened = {"n": 0}

    def counting_hung():
        opened["n"] += 1
        return hung()

    monkeypatch.setattr(db_session, "SessionLocal", counting_hung)
    with turn(tenant_id):
        started = time.monotonic()
        assert await source(table("Hang1")) is None
        assert time.monotonic() - started < 0.5
        assert await source(table("Hang1")) is None  # breaker open: no session at all
        clock.now += BREAKER_S - 1
        assert await source(table("Hang1")) is None
    assert opened["n"] == 1


async def test_after_the_breaker_one_trial_probes_and_its_success_closes_it(
    patched_db, monkeypatch, clock, tenant_id
):
    row = table("Trial1")
    await store_batch([PendingWrite(summary("Trial1", "public")), PendingWrite(row, tenant_id)])
    raw_fetch_reads.breaker.failed()
    with turn(tenant_id):
        assert await source(row) is None  # open
        clock.now += BREAKER_S
        assert (await source(row)).shared  # the trial hit
        assert raw_fetch_reads.breaker.open_until == 0  # closed
        assert await source(row) is not None


async def test_while_the_trial_runs_other_callers_skip_and_a_failed_trial_reopens(
    monkeypatch, clock, tenant_id
):
    monkeypatch.setattr(raw_fetch_reads.settings, "raw_store_probe_timeout_ms", 100)
    raw_fetch_reads.breaker.failed()
    clock.now += BREAKER_S
    opened = {"n": 0}

    def counting_hung():
        opened["n"] += 1
        return hung()

    monkeypatch.setattr(db_session, "SessionLocal", counting_hung)
    with turn(tenant_id):
        trial = asyncio.create_task(source(table("T2")))
        await asyncio.sleep(0.01)
        assert await source(table("T2")) is None and opened["n"] == 1  # skipped, no session
        assert await trial is None  # timed out
    assert raw_fetch_reads.breaker.open_until == clock.now + BREAKER_S and not raw_fetch_reads.breaker.trial


async def test_a_cancelled_trial_frees_the_trial_and_keeps_the_breaker_half_open(monkeypatch, clock, tenant_id):
    raw_fetch_reads.breaker.failed()
    clock.now += BREAKER_S
    monkeypatch.setattr(db_session, "SessionLocal", hung)
    with turn(tenant_id):
        trial = asyncio.create_task(source(table("T3")))
        await asyncio.sleep(0.01)
        assert raw_fetch_reads.breaker.trial
        trial.cancel()
        with pytest.raises(asyncio.CancelledError):
            await trial
    assert not raw_fetch_reads.breaker.trial and raw_fetch_reads.breaker.admit() is True  # next one may try


async def test_a_connection_error_opens_the_breaker_but_a_bug_is_only_a_miss(monkeypatch, tenant_id):
    def bug():
        raise ValueError("a bad row")

    def refused():
        raise OSError("connection refused")

    monkeypatch.setattr(db_session, "SessionLocal", bug)
    with turn(tenant_id):
        assert await source(table("Bug1")) is None
        assert raw_fetch_reads.breaker.open_until == 0
        monkeypatch.setattr(db_session, "SessionLocal", refused)
        assert await source(table("Bug1")) is None
    assert raw_fetch_reads.breaker.open_until > 0


def test_breaker_transitions(clock):
    b = Breaker(clock=clock)
    assert b.admit() is False  # closed: probe, not a trial
    b.succeeded(False)
    b.failed()
    assert b.admit() is None  # open
    clock.now += BREAKER_S
    assert b.admit() is True and b.admit() is None  # half-open: one trial, the rest skip
    b.released(True)
    assert b.admit() is True  # the freed trial goes to the next caller
    b.failed()
    assert b.admit() is None  # the trial failed: open again
    clock.now += BREAKER_S
    assert b.admit() is True
    b.succeeded(True)
    assert b.admit() is False  # closed


# --- sc-132 AC1 (counted here): probe outcomes ---------------------------------------------------


async def test_every_probe_is_counted_once(patched_db, monkeypatch, tenant_id, other_tenant_id):
    row = table("Cnt1")
    await store_batch([PendingWrite(summary("Cnt1")), PendingWrite(row, tenant_id)])
    with turn(tenant_id):
        await source(row)  # hit
        await source(table("Cnt2"))  # miss
    with turn(other_tenant_id):
        await source(row)  # not visible
    monkeypatch.setattr(raw_fetch_reads.settings, "raw_store_probe_timeout_ms", 20)
    monkeypatch.setattr(db_session, "SessionLocal", hung)
    with turn(tenant_id):
        await source(row)  # timeout
        await source(row)  # skipped by the breaker: not counted
    counts = {k[1]: v for k, v in wcl_cache._counts.items() if k[0] == wcl_cache.LOCAL_METRICS}
    assert counts == {"store_hit": 1, "store_miss": 1, "store_not_visible": 1, "store_timeout": 1}


# --- AC3: the probe runs inside single-flight and a lane slot -----------------------------------


class FakeSource:
    def __init__(self, answer: StoredFetch | None = None):
        self.answer, self.calls, self.slots = answer, 0, []

    def scope(self) -> str:
        identity = current_identity.get()
        return str(identity.tenant_id) if identity else ""

    async def __call__(self, query_key, query, variables):
        self.calls += 1
        self.slots.append(wcl_client._limiter().in_use)
        await asyncio.sleep(0.02)
        return self.answer


@pytest.fixture
def network(monkeypatch):
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        await asyncio.sleep(0.02)
        return gql_response({"data": {"reportData": {"report": {"table": "network"}}}})

    monkeypatch.setattr(wcl_client, "_fetch_sink", None)
    return mock_async_client(handler), calls


async def test_identical_concurrent_queries_share_one_probe_inside_a_lane_slot(monkeypatch, network, tenant_id):
    client, calls = network
    stored = StoredFetch(b'{"data": {"t": 1}}', True)
    fake = FakeSource(stored)
    monkeypatch.setattr(wcl_client, "_fetch_source", fake)
    with turn(tenant_id):
        results = await asyncio.gather(*(client.query(TABLE_Q, {"code": "Fan1"}) for _ in range(10)))
    assert results == [{"data": {"t": 1}}] * 10
    assert fake.calls == 1 and fake.slots == [1] and calls["n"] == 0


async def test_two_workspaces_never_share_a_probe(monkeypatch, network, tenant_id, other_tenant_id):
    client, calls = network
    fake = FakeSource()
    monkeypatch.setattr(wcl_client, "_fetch_source", fake)

    async def as_tenant(tenant):
        with turn(tenant):
            return await client.query(TABLE_Q, {"code": "Two1"})

    await asyncio.gather(as_tenant(tenant_id), as_tenant(other_tenant_id), as_tenant(tenant_id))
    assert fake.calls == 2 and calls["n"] == 2


async def test_a_stored_answer_is_served_while_the_wcl_budget_is_spent(monkeypatch, network, tenant_id):
    client, calls = network
    monkeypatch.setattr(wcl_client, "_fetch_source", FakeSource(StoredFetch(b'{"data": {"t": 2}}', True)))
    monkeypatch.setattr(wcl_client, "_blocked_until", time.monotonic() + 600)
    with turn(tenant_id):
        assert await client.query(TABLE_Q, {"code": "Blk1"}) == {"data": {"t": 2}}
    monkeypatch.setattr(wcl_client, "_fetch_source", FakeSource(None))
    with turn(tenant_id), pytest.raises(Exception):
        await client.query(TABLE_Q, {"code": "Blk2"})  # a miss still fails fast
    assert calls["n"] == 0


async def test_the_network_fetch_records_when_it_was_requested(monkeypatch, network):
    client, _ = network
    offered: list = []
    monkeypatch.setattr(wcl_client, "_fetch_sink", offered.append)
    before = datetime.now(UTC)
    await client.query(TABLE_Q, {"code": "Req1"})
    assert before <= offered[0].requested_at <= offered[0].fetched_at


async def test_a_probe_miss_goes_to_wcl_in_the_same_lane_slot(monkeypatch, network, tenant_id):
    client, calls = network
    monkeypatch.setattr(wcl_client, "_fetch_source", FakeSource(None))
    taken = {"n": 0}
    real_acquire = wcl_client.LaneLimiter.acquire

    async def acquire(self, lane=None):
        taken["n"] += 1
        return await real_acquire(self, lane)

    monkeypatch.setattr(wcl_client.LaneLimiter, "acquire", acquire)
    with turn(tenant_id):
        await client.query(TABLE_Q, {"code": "Once1"})
    assert calls["n"] == 1 and taken["n"] == 1  # no second queue for the network request
