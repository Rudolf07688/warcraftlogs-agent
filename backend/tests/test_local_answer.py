"""Local-answer rate (feature 045, sc-132): a chat turn with no network WCL call is local.

The turn boundary is ``set_refresh_actor`` (called by the chat socket at turn start and end);
the WCL client marks the running turn on every network call, failed ones included.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from backend.tests.wcl_fakes import gql_response, mock_async_client
from wcl_agent.cache import cache
from wcl_agent.cache.cache import LOCAL_METRICS, set_refresh_actor
from wcl_agent.client import wcl_client
from wcl_agent.client.wcl_client import StoredFetch

TABLE_Q = "query ReportQ($code: String!) { reportData { report(code: $code) { table } } }"


def turns() -> tuple[int, int]:
    return cache._counts[(LOCAL_METRICS, "turns")], cache._counts[(LOCAL_METRICS, "local_turns")]


class Stored:
    def scope(self) -> str:
        return ""

    async def __call__(self, *args):
        return StoredFetch(b'{"data": {"t": 1}}', True)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(wcl_client, "_fetch_sink", None)
    monkeypatch.setattr(wcl_client, "_fetch_source", None)
    return mock_async_client(lambda request: gql_response({"data": {"t": 2}})), None


async def run_turn(body) -> None:
    """Like the chat socket: open the turn, run its tools in a copied context, close it."""
    set_refresh_actor("user-1")
    try:
        await asyncio.create_task(body())  # ADK's producer task copies the context
    finally:
        set_refresh_actor(None)


async def test_a_turn_without_any_wcl_call_is_local():
    async def nothing():
        return None

    await run_turn(nothing)
    assert turns() == (1, 1)


async def test_a_turn_with_a_network_call_is_not_local(client):
    wcl, _ = client

    async def ask():
        await wcl.query(TABLE_Q, {"code": "Net1"})

    await run_turn(ask)
    assert turns() == (1, 0)


async def test_a_turn_answered_from_the_store_is_local(client, monkeypatch):
    wcl, _ = client
    monkeypatch.setattr(wcl_client, "_fetch_source", Stored())

    async def ask():
        await wcl.query(TABLE_Q, {"code": "Sto1"})

    await run_turn(ask)
    assert turns() == (1, 1)


async def test_a_failed_wcl_call_is_not_local(monkeypatch):
    monkeypatch.setattr(wcl_client, "_fetch_sink", None)
    monkeypatch.setattr(wcl_client, "_fetch_source", None)
    monkeypatch.setattr(wcl_client, "MAX_RETRIES", 0)
    wcl = mock_async_client(_server_error)

    async def ask():
        with pytest.raises(Exception):
            await wcl.query(TABLE_Q, {"code": "Err1"})

    await run_turn(ask)
    assert turns() == (1, 0)


def _server_error(request):
    import httpx

    return httpx.Response(500, request=request)


async def test_a_call_from_a_tool_thread_marks_the_turn(client):
    """Tools may run in threads with the turn's copied context (test_tool_concurrency)."""
    wcl, _ = client
    import contextvars

    async def ask():
        ctx = contextvars.copy_context()
        done = threading.Event()

        def in_thread():
            ctx.run(cache.note_external_call)
            done.set()

        threading.Thread(target=in_thread).start()
        await asyncio.to_thread(done.wait)

    await run_turn(ask)
    assert turns() == (1, 0)


async def test_calls_outside_a_turn_count_nothing(client):
    wcl, _ = client
    await wcl.query(TABLE_Q, {"code": "Out1"})
    set_refresh_actor(None)
    assert turns() == (0, 0)
