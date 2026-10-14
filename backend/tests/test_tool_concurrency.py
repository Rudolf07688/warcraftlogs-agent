"""Tools off the event loop and parallel WCL fan-out (QA PERF-001, PERF-002)."""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import threading
import time

from google.adk.tools.function_tool import FunctionTool

from backend.tests.test_benchmark import FIGHT, PLAYER_CODE, make_responder
from backend.tests.wcl_fakes import install
from wcl_agent import wcl_client
from wcl_agent.agent import TOOLS, build_agent
from wcl_agent.benchmark import compare_player_to_cohort
from wcl_agent.cache import TTLCache, get_scope_prefix, set_scope_prefix
from wcl_agent.report_tools import get_report_table
from wcl_agent.threading_utils import gather_threads, off_loop, unwrap
from wcl_agent.tools import compare_specs

# --- off_loop -------------------------------------------------------------------


def test_off_loop_keeps_the_adk_declaration():
    for fn in (compare_specs, get_report_table):  # one with ToolContext, one without
        wrapped = off_loop(fn)
        assert wrapped.__name__ == fn.__name__ and wrapped.__doc__ == fn.__doc__
        decl = FunctionTool(wrapped)._get_declaration()
        assert decl is not None and decl == FunctionTool(fn)._get_declaration()
    # ToolContext is still detected and kept out of the schema.
    assert "tool_context" not in str(FunctionTool(off_loop(compare_specs))._get_declaration())


async def test_adk_runs_a_wrapped_tool_off_the_loop_thread():
    loop_thread = threading.get_ident()

    def where() -> int:
        return threading.get_ident()

    # ADK's SSE path calls a plain sync tool inline on the loop (the PERF-001 defect)...
    raw = FunctionTool(where)
    assert await raw._invoke_callable(raw.func, {}) == loop_thread
    # ...and awaits the off_loop wrapper, which runs it in a worker thread.
    wrapped = FunctionTool(off_loop(where))
    assert await wrapped._invoke_callable(wrapped.func, {}) != loop_thread


def test_build_agent_wraps_every_tool_as_async():
    agent = build_agent("claude-sonnet-4@20250514")  # Anthropic: no web_search tool appended
    assert [t.__name__ for t in agent.tools] == [fn.__name__ for fn in TOOLS]
    assert all(inspect.iscoroutinefunction(t) for t in agent.tools)


async def test_off_loop_runs_tools_concurrently_without_blocking_the_loop():
    loop_thread = threading.get_ident()
    seen: list[tuple[int, str]] = []

    def slow_tool(n: int) -> int:
        seen.append((threading.get_ident(), get_scope_prefix()))
        time.sleep(0.3)
        return n

    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    set_scope_prefix("tenant-a")
    beat = asyncio.create_task(heartbeat())
    start = time.monotonic()
    results = await asyncio.gather(off_loop(slow_tool)(1), off_loop(slow_tool)(2))
    elapsed = time.monotonic() - start
    beat.cancel()
    set_scope_prefix("")

    assert results == [1, 2]
    assert elapsed < 0.5  # overlapped, not 0.6 s back to back
    assert ticks >= 5  # the loop kept running while the tools slept
    assert all(tid != loop_thread for tid, _ in seen)
    assert all(scope == "tenant-a" for _, scope in seen)  # cache scope reaches the thread


# --- gather_threads -------------------------------------------------------------


def test_gather_threads_keeps_order_captures_errors_and_context():
    var: contextvars.ContextVar[str] = contextvars.ContextVar("v", default="unset")
    var.set("caller")

    def make(i: int):
        def call():
            time.sleep(0.05 * (3 - i))  # later items finish first
            if i == 1:
                raise ValueError("boom")
            return (i, var.get())

        return call

    start = time.monotonic()
    results = gather_threads([make(i) for i in range(3)])
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


# --- thread safety --------------------------------------------------------------


def test_ttl_cache_survives_concurrent_access():
    cache = TTLCache(maxsize=8)
    errors: list[BaseException] = []

    def hammer(n: int):
        try:
            for i in range(2000):
                key = f"k{(n + i) % 20}"
                cache.set(key, {"v": i}, ttl=60)
                cache.get(key)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=hammer, args=(n,)) for n in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(cache) <= 8


def test_wcl_requests_respect_the_concurrency_cap(monkeypatch):
    inflight = peak = 0
    lock = threading.Lock()

    class Resp:
        content = b"{}"

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"rateLimitData": {}}}

    def fake_post(_self, *_args, **_kwargs):
        nonlocal inflight, peak
        with lock:
            inflight += 1
            peak = max(peak, inflight)
        time.sleep(0.05)
        with lock:
            inflight -= 1
        return Resp()

    monkeypatch.setattr(wcl_client.requests.Session, "post", fake_post)
    monkeypatch.setattr(wcl_client, "_inflight", threading.BoundedSemaphore(2))
    client = wcl_client.WCLClient("id", "secret", access_token="token")
    # rateLimitData bypasses the cache, so every call reaches requests.post.
    gather_threads([lambda: client.query("{ rateLimitData { limitPerHour } }")] * 8, max_workers=8)
    assert peak == 2


# --- PERF-002: compare_player_to_cohort fans out ---------------------------------


def test_compare_player_to_cohort_fans_out_and_keeps_tenant_scope(monkeypatch):
    base = make_responder()
    scopes: list[str] = []

    def slow(query, variables):
        scopes.append(get_scope_prefix())
        time.sleep(0.1)
        return base(query, variables)

    fake = install(monkeypatch, slow)

    def run():
        set_scope_prefix("tenant-b")
        return compare_player_to_cohort(PLAYER_CODE, FIGHT, "Hrslkks")

    start = time.monotonic()
    res = contextvars.copy_context().run(run)
    elapsed = time.monotonic() - start

    assert res["status"] == "success" and res["cohort"]["size"] == 5
    serial = 0.1 * len(fake.calls)  # context + budget + 3 pages + casts + deaths + 5 members
    assert len(fake.calls) >= 10
    assert elapsed < serial * 0.6, (elapsed, serial)
    assert scopes and all(s == "tenant-b" for s in scopes)  # no cross-tenant cache keys


# --- PERF-101: tools have their own thread pool -----------------------------------


async def test_tools_do_not_queue_behind_a_busy_default_executor():
    from concurrent.futures import ThreadPoolExecutor

    loop = asyncio.get_running_loop()
    busy = ThreadPoolExecutor(max_workers=1)
    loop.set_default_executor(busy)
    try:
        blocker = asyncio.to_thread(time.sleep, 1.0)  # occupies the only default worker
        blocker_task = asyncio.ensure_future(blocker)
        await asyncio.sleep(0.05)

        def tool() -> tuple[str, str]:
            return threading.current_thread().name, get_scope_prefix()

        set_scope_prefix("tenant-c")
        start = time.monotonic()
        name, scope = await off_loop(tool)()
        elapsed = time.monotonic() - start
        set_scope_prefix("")

        assert elapsed < 0.3  # not stuck behind the 1 s default-executor job
        assert name.startswith("wcl-tool")
        assert scope == "tenant-c"
        await blocker_task
    finally:
        busy.shutdown(wait=False)
