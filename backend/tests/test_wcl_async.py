"""Async WCL client: cache, single-flight, cancellation, timeout, auth and lanes (feature 013)."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from backend.tests.wcl_fakes import gql_response, mock_async_client
from wcl_agent import wcl_client
from wcl_agent.cache import get_cache
from wcl_agent.wcl_client import LaneLimiter, _limiter, background_lane

REPORT_Q = "query($code: String) { reportData { report(code: $code) { title } } }"
RATE_Q = "{ rateLimitData { limitPerHour } }"


@pytest.fixture(autouse=True)
def _clean_cache():
    get_cache().clear()
    yield
    get_cache().clear()


def counting(payload_for=lambda n: {"data": {"value": n}}):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return gql_response(payload_for(calls["n"]))

    return calls, handler


async def test_cache_hits_are_equal_but_distinct_objects():
    calls, handler = counting()
    client = mock_async_client(handler)
    first = await client.query(REPORT_Q, {"code": "ABC"})
    first["data"]["value"] = "MUTATED"
    second = await client.query(REPORT_Q, {"code": "ABC"})
    third = await client.query(REPORT_Q, {"code": "ABC"})
    assert calls["n"] == 1
    assert second == {"data": {"value": 1}} and second is not third
    await client.aclose()


async def test_rate_limit_and_cache_false_always_reach_the_network():
    calls, handler = counting()
    client = mock_async_client(handler)
    await client.query(RATE_Q)
    await client.query(RATE_Q)
    await client.query(REPORT_Q, {"code": "X"}, cache=False)
    await client.query(REPORT_Q, {"code": "X"}, cache=False)
    assert calls["n"] == 4
    await client.aclose()


async def test_concurrent_identical_queries_post_once():
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return gql_response({"data": {"value": 1}})

    client = mock_async_client(handler)
    results = await asyncio.gather(*(client.query(REPORT_Q, {"code": "SF"}) for _ in range(10)))
    assert calls["n"] == 1
    assert all(r == {"data": {"value": 1}} for r in results)
    assert len({id(r) for r in results}) == 10  # each caller owns its dict
    await client.aclose()


async def test_cancelling_one_waiter_leaves_the_others_their_result():
    release = asyncio.Event()

    async def handler(request):
        await release.wait()
        return gql_response({"data": {"value": 7}})

    client = mock_async_client(handler)
    tasks = [asyncio.create_task(client.query(REPORT_Q, {"code": "C"})) for _ in range(3)]
    await asyncio.sleep(0.05)
    tasks[0].cancel()
    await asyncio.sleep(0)
    release.set()
    done = await asyncio.gather(*tasks, return_exceptions=True)
    assert isinstance(done[0], asyncio.CancelledError)
    assert done[1] == done[2] == {"data": {"value": 7}}
    await client.aclose()


async def test_cancelling_every_waiter_cancels_the_fetch_and_frees_the_slot():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def handler(request):
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    client = mock_async_client(handler)
    tasks = [asyncio.create_task(client.query(REPORT_Q, {"code": "H"})) for _ in range(3)]
    await asyncio.wait_for(started.wait(), 5)
    assert _limiter().in_use == 1
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await asyncio.wait_for(cancelled.wait(), 5)
    for _ in range(50):
        if _limiter().in_use == 0:
            break
        await asyncio.sleep(0.1)
    assert _limiter().in_use == 0  # SC-007 at client level
    assert client._flights == {}
    await client.aclose()


async def test_a_hanging_query_times_out_and_frees_the_slot(monkeypatch):
    monkeypatch.setenv("WCL_QUERY_TIMEOUT_S", "1")

    async def handler(request):
        await asyncio.sleep(3600)

    client = mock_async_client(handler)
    with pytest.raises(TimeoutError):
        await client.query(REPORT_Q, {"code": "T"})
    assert _limiter().in_use == 0
    await client.aclose()


async def test_graphql_errors_raise_and_are_not_cached():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return gql_response({"errors": [{"message": "nope"}]})
        return gql_response({"data": {"ok": True}})

    client = mock_async_client(handler)
    with pytest.raises(RuntimeError, match="nope"):
        await client.query(REPORT_Q, {"code": "E"})
    assert await client.query(REPORT_Q, {"code": "E"}) == {"data": {"ok": True}}
    assert calls["n"] == 2
    await client.aclose()


async def test_http_errors_raise_status_errors():
    client = mock_async_client(lambda r: httpx.Response(429, content=b"slow down"))
    with pytest.raises(httpx.HTTPStatusError):
        await client.query(REPORT_Q, {"code": "R"})
    await client.aclose()


async def test_a_401_refreshes_the_token_once_and_retries():
    seen: list[str] = []

    def handler(request):
        seen.append(request.headers["Authorization"])
        if len(seen) == 1:
            return httpx.Response(401, content=b"expired")
        return gql_response({"data": {"ok": True}})

    client = mock_async_client(handler, client_id="auth-test", tokens=["old", "new"])
    assert await client.query(RATE_Q) == {"data": {"ok": True}}
    assert seen == ["Bearer old", "Bearer new"]
    await client.aclose()


async def test_concurrent_first_calls_fetch_one_token():
    token_calls = {"n": 0}

    async def route(request):
        if str(request.url) == wcl_client.TOKEN_URL:
            token_calls["n"] += 1
            await asyncio.sleep(0.02)
            return httpx.Response(200, json={"access_token": "t"})
        return gql_response({"data": {}})

    wcl_client._tokens.pop("one-token", None)
    client = wcl_client.AsyncWCLClient("one-token", "s", transport=httpx.MockTransport(route))
    await asyncio.gather(*(client.query(RATE_Q) for _ in range(5)))
    assert token_calls["n"] == 1
    await client.aclose()


async def test_big_payloads_parse_correctly():
    big = {"data": {"rows": ["x" * 100] * 25_000}}  # > 2 MB: parsed off the loop

    client = mock_async_client(lambda r: gql_response(big))
    assert len(json.dumps(big)) > 2_000_000
    assert await client.query(REPORT_Q, {"code": "BIG"}) == big
    assert await client.query(REPORT_Q, {"code": "BIG"}) == big  # from the bytes cache
    await client.aclose()


async def test_requests_respect_the_concurrency_cap(monkeypatch):
    monkeypatch.setenv("WCL_MAX_CONCURRENCY", "2")
    inflight = peak = 0

    async def handler(request):
        nonlocal inflight, peak
        inflight += 1
        peak = max(peak, inflight)
        await asyncio.sleep(0.05)
        inflight -= 1
        return gql_response({"data": {"rateLimitData": {}}})

    async def run():  # a fresh loop builds its limiter from the patched env
        client = mock_async_client(handler)
        await asyncio.gather(*(client.query(RATE_Q) for _ in range(8)))
        await client.aclose()

    await asyncio.to_thread(asyncio.run, run())
    assert peak == 2


# --- LaneLimiter (SC-009) -------------------------------------------------------------


async def _hold(limiter: LaneLimiter, lane: str, held: list, release: asyncio.Event):
    got = await limiter.acquire(lane)
    held.append(got)
    try:
        await release.wait()
    finally:
        limiter.release(got)


async def test_background_never_holds_more_than_its_cap():
    limiter = LaneLimiter(6, 2)
    held: list[str] = []
    release = asyncio.Event()
    tasks = [asyncio.create_task(_hold(limiter, "background", held, release)) for _ in range(3)]
    await asyncio.sleep(0.05)
    assert held == ["background", "background"] and limiter.bg_in_use == 2
    release.set()
    await asyncio.gather(*tasks)
    assert held.count("background") == 3 and limiter.in_use == 0


async def test_interactive_gets_a_slot_while_background_is_saturated_and_queued():
    limiter = LaneLimiter(6, 2)
    held: list[str] = []
    release = asyncio.Event()
    bg = [asyncio.create_task(_hold(limiter, "background", held, release)) for _ in range(3)]
    await asyncio.sleep(0.05)
    lane = await asyncio.wait_for(limiter.acquire("interactive"), 1)
    assert lane == "interactive" and limiter.in_use == 3
    limiter.release(lane)
    release.set()
    await asyncio.gather(*bg)


async def test_background_waits_while_interactive_is_waiting():
    limiter = LaneLimiter(2, 1)
    a = await limiter.acquire("interactive")
    await limiter.acquire("interactive")
    waiting_i = asyncio.create_task(limiter.acquire("interactive"))
    await asyncio.sleep(0.01)
    waiting_bg = asyncio.create_task(limiter.acquire("background"))
    await asyncio.sleep(0.01)
    assert limiter.interactive_waiting == 1
    # A freed slot goes to the interactive waiter, though background is allowed one.
    limiter.release(a)
    await asyncio.sleep(0.01)
    assert waiting_i.done() and not waiting_bg.done()
    limiter.release(waiting_i.result())
    assert await asyncio.wait_for(waiting_bg, 1) == "background"


async def test_a_cancelled_interactive_waiter_unblocks_background():
    limiter = LaneLimiter(1, 1)
    first = await limiter.acquire("interactive")
    waiting_i = asyncio.create_task(limiter.acquire("interactive"))
    await asyncio.sleep(0.01)
    waiting_bg = asyncio.create_task(limiter.acquire("background"))
    await asyncio.sleep(0.01)
    waiting_i.cancel()
    await asyncio.gather(waiting_i, return_exceptions=True)
    assert limiter.interactive_waiting == 0
    limiter.release(first)
    assert await asyncio.wait_for(waiting_bg, 1) == "background"
    limiter.release("background")
    assert limiter.in_use == 0


async def test_background_lane_context_reaches_the_limiter():
    limiter = LaneLimiter(6, 2)
    with background_lane():
        lane = await limiter.acquire()
    assert lane == "background"
    limiter.release(lane)
    assert await limiter.acquire() == "interactive"
