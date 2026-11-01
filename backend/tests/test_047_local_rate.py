"""The local-answer rate counts every turn that waited on a WCL load (feature 047, sc-326).

A turn that joined a shared in-flight cache load that went to Warcraft Logs, or that waited on
another process's lock for its value, counts as external, not local. So does a turn whose
preamble called Warcraft Logs.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.app.api import ws as ws_mod
from backend.tests.test_proposal_ws import _ctx_stream, _FakeSocket, _quiet, _run
from wcl_agent.cache import cache
from wcl_agent.cache.cache import (
    LOCAL_METRICS,
    CacheFamily,
    get_or_load,
    keys,
    note_external_call,
    set_refresh_actor,
)
from wcl_agent.cache.cache_models import PlayerTable

KEY = keys.report_summary("Join1")


def turns() -> tuple[int, int]:
    return cache._counts[(LOCAL_METRICS, "turns")], cache._counts[(LOCAL_METRICS, "local_turns")]


@pytest.fixture(autouse=True)
def _clean_actor(monkeypatch):
    monkeypatch.setattr(cache, "_schedule_flush", lambda: None)  # the counts stay readable here
    set_refresh_actor(None)
    yield
    set_refresh_actor(None)


def network_loader(started: asyncio.Event, release: asyncio.Event):
    """Like a WCL client call that went to the network: the caller's context is marked."""

    async def load() -> PlayerTable:
        started.set()
        await release.wait()
        note_external_call()
        return PlayerTable(data=[])

    return load


async def turn(user: str | None, body) -> None:
    """Like the chat socket: open the turn (None: a background job, no turn), run, close it."""
    set_refresh_actor(user)
    try:
        await body()
    finally:
        set_refresh_actor(None)


async def joined_load(first_user: str | None) -> None:
    started, release = asyncio.Event(), asyncio.Event()
    first = asyncio.create_task(turn(first_user, lambda: get_or_load(
        CacheFamily.REPORT_SUMMARY, KEY, PlayerTable, network_loader(started, release))))
    await started.wait()

    async def never():
        raise AssertionError("the joiner must not load")

    joiner = asyncio.create_task(turn("user-b", lambda: get_or_load(CacheFamily.REPORT_SUMMARY, KEY, PlayerTable, never)))
    await asyncio.sleep(0.01)  # the joiner is waiting on the shared load
    release.set()
    await asyncio.gather(first, joiner)


async def test_a_turn_that_joined_a_shared_wcl_load_is_external(fake_redis):
    await joined_load("user-a")
    assert turns() == (2, 0)


async def test_a_turn_that_joined_a_background_load_is_external(fake_redis):
    """E.g. the recent-raid kickoff pre-fetch (sc-339): no turn of its own, its joiner pays."""
    await joined_load(None)
    assert turns() == (1, 0)


async def test_a_joined_load_whose_loader_went_external_through_a_nested_load(fake_redis):
    started, release = asyncio.Event(), asyncio.Event()

    async def outer() -> PlayerTable:
        return await get_or_load(CacheFamily.REPORT_SUMMARY, keys.report_summary("Inner1"), PlayerTable,
                                 network_loader(started, release))

    first = asyncio.create_task(turn("user-a", lambda: get_or_load(CacheFamily.REPORT_SUMMARY, KEY, PlayerTable, outer)))
    await started.wait()
    joiner = asyncio.create_task(turn("user-b", lambda: get_or_load(CacheFamily.REPORT_SUMMARY, KEY, PlayerTable, outer)))
    await asyncio.sleep(0.01)
    release.set()
    await asyncio.gather(first, joiner)
    assert turns() == (2, 0)


async def test_a_turn_that_read_a_cached_value_stays_local(fake_redis):
    await turn("user-a", lambda: get_or_load(CacheFamily.REPORT_SUMMARY, KEY, PlayerTable,
                                              network_loader(asyncio.Event(), _set())))
    await turn("user-b", lambda: get_or_load(CacheFamily.REPORT_SUMMARY, KEY, PlayerTable, _fail))
    assert turns() == (2, 1)  # the first went to WCL, the second read Redis


async def test_a_turn_that_waited_on_another_processs_lock_is_external(fake_redis, monkeypatch):
    monkeypatch.setattr(cache, "_POLL_S", 0.01)
    await fake_redis.set(keys.lock(KEY), b"1")  # another process is loading it

    async def winner():
        await asyncio.sleep(0.05)
        await fake_redis.set(KEY, PlayerTable(data=[]).model_dump_json())

    other = asyncio.create_task(winner())
    await turn("user-b", lambda: get_or_load(CacheFamily.REPORT_SUMMARY, KEY, PlayerTable, _fail))
    await other
    assert turns() == (1, 0)


async def test_a_wcl_call_while_building_the_preamble_counts_for_the_turn(as_user, monkeypatch):
    async def preamble(*args, **kwargs):
        note_external_call()  # e.g. a coaching brief loaded from WCL
        return ""

    async def records(ctx):
        yield {"type": "token", "text": "ok"}

    _quiet(monkeypatch, _ctx_stream(records))
    monkeypatch.setattr(ws_mod, "set_refresh_actor", set_refresh_actor)
    monkeypatch.setattr(ws_mod, "_build_turn_preamble", preamble)
    await _run(_FakeSocket(), as_user)
    assert turns() == (1, 0)


async def test_a_turn_without_wcl_calls_is_still_local_and_counted_once(as_user, monkeypatch):
    async def records(ctx):
        yield {"type": "token", "text": "ok"}

    _quiet(monkeypatch, _ctx_stream(records))
    monkeypatch.setattr(ws_mod, "set_refresh_actor", set_refresh_actor)
    await _run(_FakeSocket(), as_user)
    assert turns() == (1, 1)


def _set() -> asyncio.Event:
    event = asyncio.Event()
    event.set()
    return event


async def _fail() -> PlayerTable:
    raise AssertionError("must not load")
