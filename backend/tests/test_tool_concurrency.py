"""Async WCL tools: concurrency, cancellation and per-turn context (PERF-001/002, feature 013)."""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import threading
import time

from google.adk.tools.function_tool import FunctionTool

from backend.tests.test_benchmark import FIGHT, PLAYER_CODE, make_responder
from backend.tests.wcl_fakes import gql_response, install, mock_async_client
from wcl_agent import wcl_client
from wcl_agent.agent import TOOLS, build_agent
from wcl_agent.aio import gather_settled, unwrap
from wcl_agent.benchmark import compare_player_to_cohort
from wcl_agent.cache import get_refresh_actor, set_refresh_actor
from wcl_agent.report_tools import get_report_table
from wcl_agent.tools import compare_specs
from wcl_agent.wcl_client import _limiter

# --- Tools are coroutines, registered unwrapped -----------------------------------


def test_every_tool_is_a_coroutine_with_its_adk_declaration():
    assert all(inspect.iscoroutinefunction(fn) for fn in TOOLS)
    for fn in (compare_specs, get_report_table):  # one with ToolContext, one without
        assert FunctionTool(fn)._get_declaration() is not None
    # ToolContext is still detected and kept out of the schema.
    assert "tool_context" not in str(FunctionTool(compare_specs)._get_declaration())


def test_build_agent_registers_the_tools_unwrapped():
    agent = build_agent("claude-sonnet-4@20250514")  # Anthropic: no web_search tool appended
    assert agent.tools == list(TOOLS)


async def test_tool_calls_overlap_on_the_loop_without_threads(monkeypatch):
    loop_thread = threading.get_ident()
    seen: list[tuple[int, str]] = []

    async def slow(query, variables):
        seen.append((threading.get_ident(), get_refresh_actor()))
        await asyncio.sleep(0.3)
        return {"data": {"reportData": {"report": {"table": {"data": {}}}}}}

    install(monkeypatch, slow)
    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    async def turn():
        set_refresh_actor("user-a")
        return await asyncio.gather(
            get_report_table("ABC", "Casts", fight_id=1),
            get_report_table("ABC", "Deaths", fight_id=1),
        )

    beat = asyncio.create_task(heartbeat())
    start = time.monotonic()
    results = await asyncio.create_task(turn())
    elapsed = time.monotonic() - start
    beat.cancel()

    assert [r["status"] for r in results] == ["success", "success"]
    assert elapsed < 0.5  # overlapped, not 0.6 s back to back
    assert ticks >= 5  # the loop kept running while the lookups waited
    assert all(tid == loop_thread for tid, _ in seen)  # no worker threads
    assert all(actor == "user-a" for _, actor in seen)  # the turn's context travels with await


# --- gather_settled ------------------------------------------------------------------


async def test_gather_settled_keeps_order_captures_errors_and_context():
    var: contextvars.ContextVar[str] = contextvars.ContextVar("v", default="unset")
    var.set("caller")

    async def call(i: int):
        await asyncio.sleep(0.05 * (3 - i))  # later items finish first
        if i == 1:
            raise ValueError("boom")
        return (i, var.get())

    start = time.monotonic()
    results = await gather_settled(*(call(i) for i in range(3)))
    elapsed = time.monotonic() - start

    assert results[0] == (0, "caller") and results[2] == (2, "caller")
    assert isinstance(results[1], ValueError)
    assert elapsed < 0.25  # concurrent: ~0.15 s, not 0.3 s
    assert unwrap(results[0]) == (0, "caller")
    try:
        unwrap(results[1])
    except ValueError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("unwrap should re-raise the captured exception")


async def test_cancelling_gather_settled_cancels_every_child():
    cancelled = 0

    async def child():
        nonlocal cancelled
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled += 1
            raise

    task = asyncio.create_task(gather_settled(child(), child(), child()))
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert cancelled == 3


# The WCL concurrency cap is covered against the async client's lane limiter in
# test_wcl_async.py (feature 013).


# --- PERF-002: compare_player_to_cohort fans out ---------------------------------


async def test_compare_player_to_cohort_fans_out_and_keeps_turn_context(monkeypatch):
    base = make_responder()
    scopes: list[str] = []

    async def slow(query, variables):
        scopes.append(get_refresh_actor())
        await asyncio.sleep(0.1)
        return base(query, variables)

    fake = install(monkeypatch, slow)

    async def run():
        set_refresh_actor("user-b")  # in this task's context only
        return await compare_player_to_cohort(PLAYER_CODE, FIGHT, "Hrslkks")

    start = time.monotonic()
    res = await asyncio.create_task(run())
    elapsed = time.monotonic() - start

    assert res["status"] == "success" and res["cohort"]["size"] == 5
    serial = 0.1 * len(fake.calls)  # context + budget + 3 pages + casts + deaths + 5 members
    assert len(fake.calls) >= 10
    assert elapsed < serial * 0.6, (elapsed, serial)
    assert scopes and all(s == "user-b" for s in scopes)  # the fan-out keeps the turn's context


# --- SC-007: an abandoned turn stops its lookups --------------------------------


async def test_cancelling_a_tool_stops_its_lookup_and_frees_the_slot(monkeypatch):
    started = asyncio.Event()

    async def never(request):
        started.set()
        await asyncio.sleep(3600)
        return gql_response({})

    client = mock_async_client(never)
    monkeypatch.setattr(wcl_client, "get_async_client", lambda: client)

    task = asyncio.create_task(get_report_table("HANG", "Casts", fight_id=1))
    await asyncio.wait_for(started.wait(), 5)
    assert _limiter().in_use == 1
    await asyncio.sleep(0.2)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()  # the tool doesn't swallow cancellation into an error dict
    for _ in range(50):
        if _limiter().in_use == 0:
            break
        await asyncio.sleep(0.1)
    assert _limiter().in_use == 0  # within 5 s (SC-007)
    await client.aclose()
