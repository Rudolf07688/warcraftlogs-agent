"""Turn accounting survives failures (feature 052, sc-357).

A turn whose setup fails after it opened (the preamble, or the setup transaction's commit) is
closed without being counted and leaves no refresh actor behind; a turn that joins an unshareable
load is counted by its own reload (the 047 edge case); a failing final save ends the turn with
the error frame instead of escaping it. Same harness as test_047_local_rate.py.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from backend.app.api import ws as ws_mod
from backend.tests.test_047_local_rate import turn, turns
from backend.tests.test_proposal_ws import _ctx_stream, _FakeSocket, _quiet, _run
from wcl_agent.cache import cache
from wcl_agent.cache.cache import (
    CacheFamily,
    get_or_load,
    get_refresh_actor,
    keys,
    mark_unshareable,
    note_external_call,
    set_refresh_actor,
)
from wcl_agent.cache.cache_models import PlayerTable


@pytest.fixture(autouse=True)
def _clean_actor(monkeypatch):
    monkeypatch.setattr(cache, "_schedule_flush", lambda: None)  # the counts stay readable here
    set_refresh_actor(None)
    yield
    set_refresh_actor(None)


def _real_turns(monkeypatch, records=None) -> None:
    async def answer(ctx):
        yield {"type": "token", "text": "ok"}

    _quiet(monkeypatch, _ctx_stream(records or answer))
    monkeypatch.setattr(ws_mod, "set_refresh_actor", set_refresh_actor)


def _closed() -> bool:
    return get_refresh_actor() is None and cache.current_turn() is None


# --- AC1: a turn whose setup fails is closed, not counted -------------------------------------


async def test_a_failed_preamble_closes_the_turn_uncounted(as_user, monkeypatch):
    async def boom(*args, **kwargs):
        note_external_call()  # it even asked WCL first: still not a turn that answered
        raise RuntimeError("db hiccup")

    _real_turns(monkeypatch)
    monkeypatch.setattr(ws_mod, "_build_turn_preamble", boom)
    with pytest.raises(RuntimeError):
        await _run(_FakeSocket(), as_user)
    assert _closed() and turns() == (0, 0)


async def test_a_failed_setup_commit_closes_the_turn_and_the_next_counts_only_itself(as_user, monkeypatch):
    real_scope = ws_mod.tenant_scope
    calls = {"n": 0}

    @contextlib.asynccontextmanager
    async def first_commit_fails(*args, **kwargs):
        calls["n"] += 1
        async with real_scope(*args, **kwargs) as session:
            yield session
        if calls["n"] == 1:
            raise RuntimeError("commit failed")

    _real_turns(monkeypatch)
    monkeypatch.setattr(ws_mod, "tenant_scope", first_commit_fails)
    with pytest.raises(RuntimeError):
        await _run(_FakeSocket(), as_user)
    assert _closed() and turns() == (0, 0)  # used to stay open with the actor set
    await _run(_FakeSocket(), as_user)
    assert _closed() and turns() == (1, 1)


async def test_a_cancelled_setup_closes_the_turn_uncounted(as_user, monkeypatch):
    async def hang(*args, **kwargs):
        await asyncio.Event().wait()

    _real_turns(monkeypatch)
    monkeypatch.setattr(ws_mod, "_build_turn_preamble", hang)

    closed: list[bool] = []

    async def run():  # its own task: the turn's context variables are checked inside it
        try:
            await _run(_FakeSocket(), as_user)
        finally:
            closed.append(_closed())

    task = asyncio.create_task(run())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed == [True]
    assert turns() == (0, 0)


# --- AC2: an unshareable-load joiner counts by its own reload ----------------------------------


async def test_a_joiner_of_an_unshareable_load_with_a_local_reload_is_local(fake_redis):
    key = keys.report_summary("Unshare1")
    started, release = asyncio.Event(), asyncio.Event()

    async def own_grant_from_wcl() -> PlayerTable:
        started.set()
        await release.wait()
        note_external_call()  # the first turn asked WCL ...
        mark_unshareable()  # ... for a report only its own workspace may see
        return PlayerTable(data=[])

    async def answered_locally() -> PlayerTable:
        return PlayerTable(data=[])  # e.g. the joiner's own store read: no network call

    first = asyncio.create_task(turn("user-a", lambda: get_or_load(
        CacheFamily.REPORT_SUMMARY, key, PlayerTable, own_grant_from_wcl)))
    await started.wait()
    joiner = asyncio.create_task(turn("user-b", lambda: get_or_load(
        CacheFamily.REPORT_SUMMARY, key, PlayerTable, answered_locally)))
    await asyncio.sleep(0.01)  # the joiner waits on the shared load
    release.set()
    await asyncio.gather(first, joiner)
    assert turns() == (2, 1)  # the first external, the joiner local


async def test_a_joiner_whose_own_reload_goes_to_wcl_is_external(fake_redis):
    key = keys.report_summary("Unshare2")
    started, release = asyncio.Event(), asyncio.Event()

    async def own_grant_locally() -> PlayerTable:
        started.set()
        await release.wait()
        mark_unshareable()
        return PlayerTable(data=[])

    async def from_wcl() -> PlayerTable:
        note_external_call()
        return PlayerTable(data=[])

    first = asyncio.create_task(turn("user-a", lambda: get_or_load(
        CacheFamily.REPORT_SUMMARY, key, PlayerTable, own_grant_locally)))
    await started.wait()
    joiner = asyncio.create_task(turn("user-b", lambda: get_or_load(
        CacheFamily.REPORT_SUMMARY, key, PlayerTable, from_wcl)))
    await asyncio.sleep(0.01)
    release.set()
    await asyncio.gather(first, joiner)
    assert turns() == (2, 1)  # the first local, the joiner external


# --- AC3: a failing final save is handled inside the turn ------------------------------------


async def test_a_failing_final_save_ends_the_turn_with_the_error_frame(as_user, monkeypatch, caplog):
    async def save_fails(*args, **kwargs):
        raise RuntimeError("lock timeout")

    _real_turns(monkeypatch)
    monkeypatch.setattr(ws_mod, "_save_answer", save_fails)
    sock = _FakeSocket()
    await _run(sock, as_user)  # nothing escapes
    types = [f["type"] for f in sock.frames]
    assert types[-1] == "error" and "done" not in types
    assert sock.frames[-1]["code"] == "agent_error"
    assert _closed() and turns() == (1, 1)  # the turn ran and is counted once
    assert "answer not saved" in caplog.text
