"""Async WCL client: cache, single-flight, cancellation, timeout, auth and lanes (feature 013)."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from backend.tests.wcl_fakes import gql_response, mock_async_client
from wcl_agent import wcl_client
from wcl_agent.wcl_client import LaneLimiter, _limiter, background_lane

REPORT_Q = "query($code: String) { reportData { report(code: $code) { title } } }"
RATE_Q = "{ rateLimitData { limitPerHour } }"


def counting(payload_for=lambda n: {"data": {"value": n}}):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return gql_response(payload_for(calls["n"]))

    return calls, handler


async def test_the_client_never_caches_results():
    """Feature 014: caching lives in typed key families, not in the client (W1)."""
    calls, handler = counting()
    client = mock_async_client(handler)
    await client.query(RATE_Q)
    await client.query(RATE_Q)
    first = await client.query(REPORT_Q, {"code": "X"})
    second = await client.query(REPORT_Q, {"code": "X"})
    assert calls["n"] == 4
    assert first == {"data": {"value": 3}} and second == {"data": {"value": 4}}
    await client.aclose()


async def test_a_failed_fetch_fails_all_its_waiters_and_the_next_call_refetches():
    calls = {"n": 0}

    async def flaky(request):
        calls["n"] += 1
        await asyncio.sleep(0.1)
        if calls["n"] == 1:
            return httpx.Response(400, content=b"bad")
        return gql_response({"data": {"value": calls["n"]}})

    client = mock_async_client(flaky)
    results = await asyncio.gather(*(client.query(REPORT_Q, {"code": "FL"}) for _ in range(3)), return_exceptions=True)
    assert calls["n"] == 1 and all(isinstance(r, httpx.HTTPStatusError) for r in results)
    assert await client.query(REPORT_Q, {"code": "FL"}) == {"data": {"value": 2}}
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
    assert await client.query(REPORT_Q, {"code": "BIG"}) == big  # a fresh parse each time
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
        # distinct requests: identical ones would share one fetch (single-flight)
        await asyncio.gather(*(client.query(REPORT_Q, {"code": f"C{i}"}) for i in range(8)))
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


# --- feature 014: retries, API cost logging, shared token ------------------------


@pytest.fixture
def no_sleep(monkeypatch):
    """Record backoff delays instead of sleeping them."""
    delays: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay, *args, **kwargs):
        delays.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(wcl_client.asyncio, "sleep", fake_sleep)
    return delays


async def test_429_is_retried_then_succeeds(no_sleep):
    statuses = iter([429, 200])

    def handler(request):
        status = next(statuses)
        return gql_response({"data": {"ok": status}}, status=status)

    c = mock_async_client(handler)
    assert await c.query("query A { x }") == {"data": {"ok": 200}}
    assert len(no_sleep) == 1


async def test_5xx_gives_up_after_two_retries(no_sleep):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503, content=b"down")

    c = mock_async_client(handler)
    with pytest.raises(httpx.HTTPStatusError):
        await c.query("query A { x }")
    assert calls["n"] == 3  # first try + MAX_RETRIES
    assert no_sleep[1] > no_sleep[0]  # exponential backoff


async def test_retry_after_is_honoured(no_sleep):
    statuses = iter([(429, "3"), (503, None), (200, None)])

    def handler(request):
        status, after = next(statuses)
        headers = {"Retry-After": after} if after else {}
        return httpx.Response(status, content=b'{"data": {}}', headers=headers)

    await mock_async_client(handler).query("query A { x }")
    assert no_sleep[0] == 3.0 and len(no_sleep) == 2


async def test_spent_budget_fails_fast_and_blocks_later_calls(no_sleep):
    """PERF-004: a Retry-After longer than we'd wait means the hour's budget is spent."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, content=b"spent", headers={"Retry-After": "1800"})

    client = mock_async_client(handler)
    with pytest.raises(httpx.HTTPStatusError):
        await client.query("query A { x }")
    assert calls["n"] == 1 and no_sleep == []  # no retries into a spent budget
    with pytest.raises(httpx.HTTPStatusError) as err:
        await client.query("query B { y }")
    assert calls["n"] == 1  # blocked without a request
    assert err.value.response.status_code == 429


async def test_backoff_longer_than_the_deadline_is_not_waited(no_sleep, monkeypatch):
    monkeypatch.setenv("WCL_QUERY_TIMEOUT_S", "2")
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, content=b"slow down", headers={"Retry-After": "5"})

    with pytest.raises(httpx.HTTPStatusError):
        await mock_async_client(handler).query("query A { x }")
    assert calls["n"] == 1 and no_sleep == []


async def test_400_is_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, content=b"bad")

    with pytest.raises(httpx.HTTPStatusError):
        await mock_async_client(handler).query("query A { x }")
    assert calls["n"] == 1


@pytest.mark.parametrize(
    "query",
    [
        "query ReportQ($code: String!) { reportData { report(code: $code) { title } } }",
        "{ worldData { zones { id } } }",
    ],
)
async def test_cost_field_is_injected_logged_and_stripped(query, caplog):
    sent: list[str] = []

    def handler(request):
        sent.append(json.loads(request.content)["query"])
        cost = {"limitPerHour": 3600, "pointsSpentThisHour": 12.5, "pointsResetIn": 900}
        return gql_response({"data": {"_cost": cost, "real": 1}})

    wcl_client._last_points = 10.0
    with caplog.at_level("INFO", logger="wcl_agent.wcl_client"):
        result = await mock_async_client(handler).query(query)
    assert "_cost: rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn }" in sent[0]
    assert result == {"data": {"real": 1}}  # never visible to callers
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("wcl_cost"))
    assert "points_this_hour=12.5" in line and "delta=2.5" in line
    assert ("op=ReportQ" in line) == query.startswith("query ReportQ")


def test_queries_with_fragments_are_not_rewritten():
    q = "fragment F on Report { title } query Q { reportData { report(code: \"x\") { ...F } } }"
    assert wcl_client._with_cost(q) == q


async def test_token_is_shared_through_the_cache(fake_redis):
    token_posts = {"n": 0}

    async def route(request):
        if str(request.url) == wcl_client.TOKEN_URL:
            token_posts["n"] += 1
            return httpx.Response(200, json={"access_token": "shared", "expires_in": 3600})
        return gql_response({"data": {}})

    wcl_client._tokens.pop("shared-client", None)
    first = wcl_client.AsyncWCLClient("shared-client", "s", transport=httpx.MockTransport(route))
    await first.query("query A { x }")
    wcl_client._tokens.pop("shared-client", None)  # a fresh process: empty memo
    second = wcl_client.AsyncWCLClient("shared-client", "s", transport=httpx.MockTransport(route))
    await second.query("query A { x }")
    assert token_posts["n"] == 1
    assert 0 < await fake_redis.ttl("wcl:v1:oauth:token") <= 3600 - 60


async def test_401_reloads_the_shared_token(fake_redis):
    issued = iter(["old", "new"])
    seen: list[str] = []

    async def route(request):
        if str(request.url) == wcl_client.TOKEN_URL:
            return httpx.Response(200, json={"access_token": next(issued), "expires_in": 3600})
        seen.append(request.headers["Authorization"])
        if request.headers["Authorization"] == "Bearer old":
            return httpx.Response(401)
        return gql_response({"data": {}})

    wcl_client._tokens.pop("rotating", None)
    c = wcl_client.AsyncWCLClient("rotating", "s", transport=httpx.MockTransport(route))
    await c.query("query A { x }")
    assert seen == ["Bearer old", "Bearer new"]
    assert b"new" in await fake_redis.get("wcl:v1:oauth:token")


async def test_expired_memo_is_renewed():
    issued = iter(["a", "b"])

    async def route(request):
        if str(request.url) == wcl_client.TOKEN_URL:
            return httpx.Response(200, json={"access_token": next(issued), "expires_in": 30})
        return gql_response({"data": {}})

    wcl_client._tokens.pop("short", None)
    c = wcl_client.AsyncWCLClient("short", "s", transport=httpx.MockTransport(route))
    assert await c._token() == "a"
    assert await c._token() == "b"  # 30s lifetime is inside the 60s renewal margin


async def test_rate_limit_check_reuses_the_last_response_budget():
    """PERF-009: every response carries the budget, so a fresh snapshot needs no request."""
    sent: list[str] = []

    def handler(request):
        sent.append(json.loads(request.content)["query"])
        cost = {"limitPerHour": 3600, "pointsSpentThisHour": 100, "pointsResetIn": 900}
        return gql_response({"data": {"_cost": cost, "rateLimitData": {
            "limitPerHour": 3600, "pointsSpentThisHour": 100, "pointsResetIn": 900}}})

    client = mock_async_client(handler)
    wcl_client._clients[asyncio.get_running_loop()] = client
    try:
        await client.query("query A { x }")
        assert await wcl_client.acheck_rate_limit() == {
            "limitPerHour": 3600.0, "pointsSpentThisHour": 100.0, "pointsResetIn": 900}
        assert len(sent) == 1  # answered from the snapshot
        await wcl_client.acheck_rate_limit(max_age_s=0)  # too old: asks WCL
        assert len(sent) == 2
    finally:
        wcl_client._clients.pop(asyncio.get_running_loop(), None)
