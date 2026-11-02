"""The shared raw-store breaker counts workspaces, not bursts (feature 052, sc-355; P7 SEC-001/003).

One workspace's probes timing out (a turn's parallel burst, two tabs, a turn plus its own
pre-fetch) must not switch the store off for every workspace: they only make that workspace
skip the store for a while, which also stops a single-workspace install paying the timeout on a
slow store. A store that is slow for most reads switches off even when one answers in between;
a real outage (a connection error, or timeouts from two workspaces inside the window) opens it
as before. The half-open trial is unchanged (test_raw_store_probe.py).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

import pytest

from backend.app.db import session as db_session
from backend.app.services import raw_fetch_reads
from backend.app.services.raw_fetch_reads import (
    _SLOW_MAX,
    _WINDOW_MAX,
    BREAKER_S,
    TIMEOUTS_TO_OPEN,
    WINDOW_S,
    Breaker,
    read_stored_fetch,
)
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


async def in_turn(tenant: uuid.UUID, body, *, chat: bool = True) -> None:
    """Like a chat turn (or a background job when ``chat`` is False) of a member of ``tenant``,
    in its own task's context."""

    async def run() -> None:
        current_identity.set(RequestIdentity(uuid.uuid4(), tenant, "member", False, uuid.uuid4()))
        if chat:
            set_refresh_actor(str(uuid.uuid4()))
        try:
            await body()
        finally:
            set_refresh_actor(None)

    await asyncio.create_task(run())


def burst(n: int, prefix: str = "Burst"):
    async def run():
        await asyncio.gather(*(probe(f"{prefix}{i}") for i in range(n)))

    return run


def b() -> Breaker:
    return raw_fetch_reads.breaker


# --- AC1 + SEC-001: one workspace alone can't open it -----------------------------------------


async def test_one_turns_parallel_timeouts_keep_it_closed(clock, opened, tenant_id):
    await in_turn(tenant_id, burst(10))
    assert opened["n"] == 10 and b().open_until == 0  # every workspace still probes
    assert b().admit(uuid.uuid4()) is False


async def test_one_account_in_two_tabs_cannot_open_it(clock, opened, tenant_id):
    await in_turn(tenant_id, burst(2, "TabA"))
    await in_turn(tenant_id, burst(2, "TabB"))  # another turn, same workspace
    assert b().open_until == 0


async def test_a_turn_and_its_own_pre_fetch_cannot_open_it(clock, opened, tenant_id):
    await in_turn(tenant_id, burst(2, "Turn"))
    await in_turn(tenant_id, burst(2, "Pre"), chat=False)  # the kickoff pre-fetch
    assert b().open_until == 0


async def test_a_slow_workspace_stops_probing_itself_only(clock, opened, tenant_id, other_tenant_id):
    async def slow_turn():
        for _ in range(TIMEOUTS_TO_OPEN + 2):
            await probe()

    await in_turn(tenant_id, slow_turn)
    assert opened["n"] == TIMEOUTS_TO_OPEN  # a single-workspace install stops paying the timeout
    await in_turn(tenant_id, slow_turn)  # its next turn too, while the timeouts are in the window
    assert opened["n"] == TIMEOUTS_TO_OPEN and b().open_until == 0

    async def one():
        await probe()

    await in_turn(other_tenant_id, one)
    assert opened["n"] == TIMEOUTS_TO_OPEN + 1  # another workspace still probes ... and opens it
    assert b().open_until == clock.now + BREAKER_S


async def test_background_reads_are_capped_per_workspace(clock, opened, tenant_id, other_tenant_id):
    await in_turn(tenant_id, burst(TIMEOUTS_TO_OPEN, "Pre"), chat=False)
    before = opened["n"]

    async def one():
        await probe("Other")

    await in_turn(tenant_id, one, chat=False)
    assert opened["n"] == before  # this workspace's pre-fetch skips the store
    assert b().admit(other_tenant_id) is False  # another workspace's background reads don't


# --- AC2: a mostly slow store opens it although one read succeeds -------------------------------


def test_a_mostly_slow_store_opens_despite_an_odd_success(clock):
    breaker = b()
    breaker.timed_out(False, "ws-a")
    breaker.timed_out(False, "ws-a")
    breaker.succeeded(False)  # used to reset the count: the store never opened
    assert breaker.open_until == 0
    breaker.timed_out(False, "ws-b")
    assert breaker.open_until == clock.now + BREAKER_S  # 3 of 4 timed out, from two workspaces


def test_a_healthy_store_with_sporadic_timeouts_stays_closed(clock):
    breaker = b()
    for i in range(20):
        breaker.succeeded(False)
        if i % 5 == 0:
            breaker.timed_out(False, f"ws-{i}")
    assert breaker.open_until == 0  # 4 timeouts from 4 workspaces, but 4 of 24 probes


def test_timeouts_older_than_the_window_are_forgotten(clock):
    breaker = b()
    for _ in range(TIMEOUTS_TO_OPEN):
        breaker.timed_out(False, "ws-a")
    assert breaker.admit("ws-a") is None and breaker.open_until == 0
    clock.now += WINDOW_S
    assert breaker.admit("ws-a") is False  # they left the window: it probes again
    breaker.timed_out(False, "ws-b")
    assert breaker.open_until == 0  # one timeout in the window, from one workspace


# --- SEC-003: the per-workspace memory is bounded and can't be flushed by others' traffic -------


def test_other_traffic_does_not_reset_a_workspaces_skip(clock):
    breaker = b()
    for _ in range(TIMEOUTS_TO_OPEN):
        breaker.timed_out(False, "ws-a")
    for _ in range(_WINDOW_MAX + 10):
        breaker.succeeded(False)  # a flood of other probes evicts the ratio's outcomes
    assert breaker.admit("ws-a") is None


def test_the_workspace_memory_is_bounded(clock):
    breaker = b()
    for i in range(_SLOW_MAX + 50):
        breaker.timed_out(False, f"ws-{i}")
        breaker.succeeded(False)
        breaker.succeeded(False)  # keep the ratio low: it stays closed
    assert breaker.open_until == 0 and len(breaker.slow) == _SLOW_MAX


# --- AC3: a real outage opens it as fast as today ------------------------------------------------


async def test_two_workspaces_timing_out_open_it(clock, opened, tenant_id, other_tenant_id):
    async def one():
        await probe("B1")

    await in_turn(tenant_id, burst(2, "A"))
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
    assert breaker.admit("ws-a") is None  # open: every workspace skips
    clock.now += BREAKER_S
    assert breaker.admit("ws-a") is True and breaker.admit("ws-b") is None  # one trial
    breaker.timed_out(True, "ws-a")
    assert breaker.open_until == clock.now + BREAKER_S and not breaker.trial  # reopened at once
    clock.now += BREAKER_S
    assert breaker.admit("ws-a") is True
    breaker.succeeded(True)
    assert breaker.open_until == 0 and breaker.admit("ws-a") is False


def test_is_open_changes_nothing(clock):
    breaker = b()
    assert breaker.is_open() is False
    breaker.failed()
    assert breaker.is_open() is True
    clock.now += BREAKER_S
    assert breaker.is_open() is False  # half-open: a caller may try
    assert not breaker.trial  # asking took no trial
    assert breaker.admit() is True
