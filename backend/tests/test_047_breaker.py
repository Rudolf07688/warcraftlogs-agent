"""One slow stored read doesn't switch the stored data off (feature 047, sc-323).

The shared breaker opens on a connection error at once, but on timeouts (a slow read, a wait for
a pool connection) only after ``TIMEOUTS_TO_OPEN`` (since 052 sc-355: inside the window, from two
workspaces or more, and at least half of the window's probes; test_052_breaker.py).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

import pytest
from sqlalchemy.exc import TimeoutError as PoolTimeout

from backend.app.db import session as db_session
from backend.app.services import raw_fetch_reads
from backend.app.services.raw_fetch_reads import BREAKER_S, TIMEOUTS_TO_OPEN, Breaker, read_stored_fetch
from backend.app.tenancy.context import RequestIdentity, current_identity
from wcl_agent.client.wcl_client import _flight_key

TABLE_Q = "query ReportQ($code: String!) { reportData { report(code: $code) { table } } }"


class Clock:
    now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def breaker(monkeypatch) -> Breaker:
    fresh = Breaker(clock=Clock())
    monkeypatch.setattr(raw_fetch_reads, "breaker", fresh)
    monkeypatch.setattr(raw_fetch_reads.settings, "raw_store_probe_timeout_ms", 30)
    return fresh


@contextlib.asynccontextmanager
async def slow():
    await asyncio.Event().wait()
    yield


def pool_wait():
    raise PoolTimeout("QueuePool limit reached, connection timed out")


def refused():
    raise OSError("connection refused")


async def probe(tenant: uuid.UUID) -> None:
    token = current_identity.set(RequestIdentity(uuid.uuid4(), tenant, "member", False, uuid.uuid4()))
    try:
        variables = {"code": "Slow1"}
        assert await read_stored_fetch(_flight_key(TABLE_Q, variables), TABLE_Q, variables) is None
    finally:
        current_identity.reset(token)


def test_n_is_three():
    assert TIMEOUTS_TO_OPEN == 3


@pytest.mark.parametrize("failure", [slow, pool_wait], ids=["slow-read", "pool-wait"])
async def test_one_timeout_keeps_the_breaker_closed(monkeypatch, breaker, tenant_id, failure):
    monkeypatch.setattr(db_session, "SessionLocal", failure)
    await probe(tenant_id)
    assert breaker.open_until == 0 and breaker.admit() is False  # the next read still probes


@pytest.mark.parametrize("failure", [slow, pool_wait], ids=["slow-read", "pool-wait"])
async def test_n_timeouts_from_two_workspaces_open_it(
    monkeypatch, breaker, tenant_id, other_tenant_id, failure
):
    monkeypatch.setattr(db_session, "SessionLocal", failure)
    for _ in range(TIMEOUTS_TO_OPEN - 1):
        await probe(tenant_id)
    assert breaker.open_until == 0
    await probe(other_tenant_id)
    assert breaker.open_until == breaker.clock() + BREAKER_S


async def test_a_connection_error_opens_it_at_once(monkeypatch, breaker, tenant_id):
    monkeypatch.setattr(db_session, "SessionLocal", refused)
    await probe(tenant_id)
    assert breaker.open_until > 0


def test_successes_outweighing_timeouts_keep_it_closed():
    b = Breaker(clock=Clock())
    b.timed_out(False, "ws-a")
    b.timed_out(False, "ws-b")
    for _ in range(4):
        b.succeeded(False)
    b.timed_out(False, "ws-b")
    assert b.open_until == 0  # 3 timeouts from two workspaces, but only 3 of 7 probes
    b.timed_out(False, "ws-a")
    assert b.open_until > 0  # 4 of 8: half the window's probes


def test_a_half_open_trial_that_times_out_reopens_it():
    clock = Clock()
    b = Breaker(clock=clock)
    b.failed()
    clock.now += BREAKER_S
    assert b.admit() is True
    b.timed_out(True)
    assert b.admit() is None and b.open_until == clock.now + BREAKER_S and not b.recent
