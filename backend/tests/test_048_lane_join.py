"""A chat turn that joins a background flight is not held to the background limit (048).

QA PERF-001 = BUG-001 = SEC-001: the kickoff pre-fetch starts its boss tables in the background
lane, and the kickoff turn sends the same queries, so it joins those flights. Joining promotes
the flight to the interactive lane; background work nobody joins keeps the background rule.
Driven with a fake transport whose requests stay open until released: no WCL call.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from backend.tests.wcl_fakes import gql_response, mock_async_client
from wcl_agent.client import wcl_client
from wcl_agent.client.wcl_client import LaneLimiter, LaneTicket, background_lane

TABLE_Q = "query($code: String, $f: Int) { reportData { report(code: $code) { table(fightIDs: [$f]) } } }"


async def _granted(task: asyncio.Task, limit: float = 0.2) -> bool:
    try:
        await asyncio.wait_for(asyncio.shield(task), limit)
    except TimeoutError:
        return False
    return True


# --- LaneLimiter.promote ---------------------------------------------------------------


async def test_a_promoted_queued_ticket_is_served_by_the_interactive_rule():
    limiter = LaneLimiter(6, 2)
    held = [await limiter.acquire("background") for _ in range(2)]  # background at its cap
    ticket = LaneTicket("background")
    waiting = asyncio.create_task(limiter.acquire(ticket))
    assert not await _granted(waiting)  # the background rule holds it back
    limiter.promote(ticket)
    assert await _granted(waiting) and waiting.result() == "interactive"
    assert (limiter.in_use, limiter.bg_in_use) == (3, 2)
    limiter.release(ticket)
    for lane in held:
        limiter.release(lane)
    assert (limiter.in_use, limiter.bg_in_use) == (0, 0)


async def test_a_promoted_held_slot_stops_counting_against_the_background_cap():
    limiter = LaneLimiter(6, 2)
    ticket = LaneTicket("background")
    await limiter.acquire(ticket)
    other = await limiter.acquire("background")
    queued = asyncio.create_task(limiter.acquire("background"))
    assert not await _granted(queued)
    limiter.promote(ticket)  # its slot is interactive now: one background slot is free
    assert await _granted(queued) and limiter.bg_in_use == 2
    limiter.release(ticket)
    limiter.release(other)
    limiter.release(queued.result())
    assert (limiter.in_use, limiter.bg_in_use) == (0, 0)


async def test_promoting_an_interactive_ticket_changes_nothing():
    limiter = LaneLimiter(6, 2)
    ticket = LaneTicket("interactive")
    await limiter.acquire(ticket)
    limiter.promote(ticket)
    assert (limiter.in_use, limiter.bg_in_use) == (1, 0)
    limiter.release(ticket)
    assert (limiter.in_use, limiter.bg_in_use) == (0, 0)


# --- AsyncWCLClient single-flight join -------------------------------------------------


@pytest.fixture
async def gated(monkeypatch):
    """A client whose requests stay open until ``release`` is set, and a fresh 6/2 limiter."""
    release = asyncio.Event()
    sent: list[int] = []

    async def handler(request):
        sent.append(json.loads(request.content)["variables"]["f"])
        await release.wait()
        return gql_response({"data": {"ok": True}})

    limiter = LaneLimiter(6, 2)
    monkeypatch.setitem(wcl_client._limiters, asyncio.get_running_loop(), limiter)
    return mock_async_client(handler), limiter, release, sent


async def _warm_up(client, fights):
    """The pre-fetch's shape: whole-raid tables gathered inside the background lane."""
    with background_lane():
        return await asyncio.gather(*(client.query(TABLE_Q, {"code": "K1", "f": f}) for f in fights))


async def test_a_turn_joining_a_queued_background_flight_does_not_wait_for_a_background_slot(gated):
    client, limiter, release, sent = gated
    prefetch = asyncio.create_task(_warm_up(client, [1, 2, 3, 4]))
    await asyncio.sleep(0.05)
    assert sorted(sent) == [1, 2] and limiter.bg_in_use == 2  # 3 and 4 wait for the lane

    turn = asyncio.create_task(client.query(TABLE_Q, {"code": "K1", "f": 3}))  # the kickoff turn
    await asyncio.sleep(0.05)
    assert sorted(sent) == [1, 2, 3]  # sent at once, as an interactive request, not a new one
    assert limiter.bg_in_use == 2 and limiter.in_use == 3
    assert 4 not in sent  # background work nobody joined still obeys the background cap

    release.set()
    assert await asyncio.wait_for(turn, 5) == {"data": {"ok": True}}
    await asyncio.wait_for(prefetch, 5)
    assert sorted(sent) == [1, 2, 3, 4]  # one request per table: the turn shared the flight
    assert (limiter.in_use, limiter.bg_in_use) == (0, 0)
    await client.aclose()


async def test_a_turn_joining_a_running_background_flight_frees_its_background_slot(gated):
    client, limiter, release, sent = gated
    prefetch = asyncio.create_task(_warm_up(client, [1, 2, 3]))
    await asyncio.sleep(0.05)
    assert sorted(sent) == [1, 2]

    turn = asyncio.create_task(client.query(TABLE_Q, {"code": "K1", "f": 1}))
    await asyncio.sleep(0.05)
    # Fight 1's slot is interactive now, so the next background table takes the freed slot.
    assert sorted(sent) == [1, 2, 3] and limiter.bg_in_use == 2 and limiter.in_use == 3

    release.set()
    await asyncio.wait_for(asyncio.gather(turn, prefetch), 5)
    assert (limiter.in_use, limiter.bg_in_use) == (0, 0)
    await client.aclose()


async def test_background_callers_joining_a_background_flight_leave_it_in_the_background(gated):
    client, limiter, release, sent = gated
    prefetch = asyncio.create_task(_warm_up(client, [1, 2, 3]))
    await asyncio.sleep(0.05)
    again = asyncio.create_task(_warm_up(client, [3]))  # e.g. a guide job in the same lane
    await asyncio.sleep(0.05)
    assert sorted(sent) == [1, 2] and limiter.bg_in_use == 2  # still capped
    release.set()
    await asyncio.wait_for(asyncio.gather(prefetch, again), 5)
    assert sorted(sent) == [1, 2, 3]
    await client.aclose()
