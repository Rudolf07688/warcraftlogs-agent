"""The shared raw-store breaker counts turns, not bursts (feature 052, sc-355).

One turn's parallel probes timing out together must not switch the store off for every
workspace; a store that is slow for most reads must switch off even when one answers in
between; a real outage (a connection error, or timeouts from two turns inside the window) still
opens it as fast as before. The half-open trial is unchanged (test_raw_store_probe.py).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

import pytest

from backend.app.db import session as db_session
from backend.app.services import raw_fetch_reads
from backend.app.services.raw_fetch_reads import BREAKER_S, TIMEOUTS_TO_OPEN, WINDOW_S, Breaker, read_stored_fetch
from backend.app.tenancy.context import RequestIdentity, current_identity
from wcl_agent.cache import cache
from wcl_agent.cache.cache import set_refresh_actor
from wcl_agent.client.wcl_client import _flight_key

TABLE_Q = "query ReportQ($code: String!) { reportData { report(code: $code) { table } } }"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(raw_fetch_reads, "breaker", Breaker(clock=fake))
    monkeypatch.setattr(raw_fetch_reads.settings, "raw_store_probe_timeout_ms", 30)
    monkeypatch.setattr(cache, "_schedule_flush", lambda: None)
    return fake


@pytest.fixture
def opened(monkeypatch) -> dict[str, int]:
    """A hung store: every probe times out; counts the sessions opened."""
    seen = {"n": 0}

    @contextlib.asynccontextmanager
    async def hung():
        seen["n"] += 1
        await asyncio.Event().wait()
        yield

    monkeypatch.setattr(db_session, "SessionLocal", hung)
    return seen


async def probe(code: str = "Slow1") -> None:
    variables = {"code": code}
    assert await read_stored_fetch(_flight_key(TABLE_Q, variables), TABLE_Q, variables) is None


async def in_turn(tenant: uuid.UUID, body) -> None:
    """Like a chat turn: its own identity and its own turn, in its own task's context."""

    async def run() -> None:
        current_identity.set(RequestIdentity(uuid.uuid4(), tenant, "member", False, uuid.uuid4()))
        set_refresh_actor(str(uuid.uuid4()))
        try:
            await body()
        finally:
            set_refresh_actor(None)

    await asyncio.create_task(run())


def b() -> Breaker:
    return raw_fetch_reads.breaker


# --- AC1: one turn alone can't open it -------------------------------------------------------


async def test_one_turns_parallel_timeouts_keep_it_closed(clock, opened, tenant_id):
    async def burst():
        await asyncio.gather(*(probe(f"Burst{i}") for i in range(10)))

    await in_turn(tenant_id, burst)
    assert opened["n"] == 10 and b().open_until == 0  # every workspace still probes
    assert b().admit() is False


async def test_a_turn_with_n_timeouts_stops_probing_itself_only(clock, opened, tenant_id, other_tenant_id):
    async def slow_turn():
        for _ in range(TIMEOUTS_TO_OPEN + 2):
            await probe()

    await in_turn(tenant_id, slow_turn)
    assert opened["n"] == TIMEOUTS_TO_OPEN  # capped: the rest of the turn skipped the store
    assert b().open_until == 0

    async def one():
        await probe()

    await in_turn(other_tenant_id, one)
    assert opened["n"] == TIMEOUTS_TO_OPEN + 1  # another turn still probes ... and opens it
    assert b().open_until == clock.now + BREAKER_S


async def test_reads_outside_a_turn_are_one_turn(clock, opened, tenant_id):
    token = current_identity.set(RequestIdentity(uuid.uuid4(), tenant_id, "member", False, uuid.uuid4()))
    try:
        await asyncio.gather(*(probe(f"Bg{i}") for i in range(5)))  # e.g. the kickoff pre-fetch
        assert b().open_until == 0
        await probe()
        assert opened["n"] == 5  # its own cap: the background bucket stops probing
    finally:
        current_identity.reset(token)


# --- AC2: a mostly slow store opens it although one read succeeds -------------------------------


def test_a_mostly_slow_store_opens_despite_an_odd_success(clock):
    turns = [object() for _ in range(3)]
    breaker = b()
    breaker.timed_out(False, turns[0])
    breaker.timed_out(False, turns[0])
    breaker.succeeded(False, turns[1])  # used to reset the count: the store never opened
    assert breaker.open_until == 0
    breaker.timed_out(False, turns[1])
    assert breaker.open_until == clock.now + BREAKER_S  # 3 of 4 timed out, from two turns


def test_a_healthy_store_with_sporadic_timeouts_stays_closed(clock):
    breaker = b()
    for i in range(20):
        breaker.succeeded(False, object())
        if i % 5 == 0:
            breaker.timed_out(False, object())
    assert breaker.open_until == 0  # 4 timeouts from 4 turns, but 4 of 24 probes


def test_timeouts_older_than_the_window_are_forgotten(clock):
    first, second = object(), object()
    breaker = b()
    breaker.timed_out(False, first)
    breaker.timed_out(False, first)
    clock.now += WINDOW_S
    breaker.timed_out(False, second)
    assert breaker.open_until == 0  # the first two left the window
    assert breaker.admit(first) is False  # and the first turn's cap with them


# --- AC3: a real outage opens it as fast as today ------------------------------------------------


async def test_two_turns_timing_out_open_it(clock, opened, tenant_id, other_tenant_id):
    async def two():
        await asyncio.gather(probe("A1"), probe("A2"))

    async def one():
        await probe("B1")

    await in_turn(tenant_id, two)
    assert b().open_until == 0
    await in_turn(other_tenant_id, one)
    assert b().open_until == clock.now + BREAKER_S
    assert opened["n"] == TIMEOUTS_TO_OPEN


async def test_a_connection_error_opens_it_at_once(clock, monkeypatch, tenant_id):
    def refused():
        raise OSError("connection refused")

    monkeypatch.setattr(db_session, "SessionLocal", refused)

    async def one():
        await probe()

    await in_turn(tenant_id, one)
    assert b().open_until == clock.now + BREAKER_S


# --- AC4 + sc-352: half-open unchanged; is_open has no side effect ------------------------------


def test_the_half_open_trial_is_unchanged(clock):
    breaker = b()
    breaker.failed()
    assert breaker.admit(object()) is None  # open: every turn skips
    clock.now += BREAKER_S
    turn = object()
    assert breaker.admit(turn) is True and breaker.admit(object()) is None  # one trial
    breaker.timed_out(True, turn)
    assert breaker.open_until == clock.now + BREAKER_S and not breaker.trial  # reopened at once
    clock.now += BREAKER_S
    assert breaker.admit(turn) is True
    breaker.succeeded(True, turn)
    assert breaker.open_until == 0 and breaker.admit(turn) is False


def test_is_open_changes_nothing(clock):
    breaker = b()
    assert breaker.is_open() is False
    breaker.failed()
    assert breaker.is_open() is True
    clock.now += BREAKER_S
    assert breaker.is_open() is False  # half-open: a caller may try
    assert not breaker.trial  # asking took no trial
    assert breaker.admit() is True
