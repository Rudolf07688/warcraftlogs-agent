"""Both models busy: one deadline over requests and waits (feature 052, sc-297).

When the turn's model and its sibling are both remembered as rate limited, the turn gets one
10 s budget. Since 052 it is a monotonic deadline: the requests' own time counts, so "both models
are busy" arrives within 10 s plus at most one request in flight, not 10 s of sleeps plus every
request (about 11-16 s before). Same fakes as test_model_fallback.py, on a fake clock.
"""

from __future__ import annotations

import pytest

from backend.tests.test_model_fallback import A, B, FakeGenai, _collect, _gemini, _request, _turn
from wcl_agent.llm import model_retry
from wcl_agent.llm.model_retry import ModelRateLimited, RetryPolicy

REQUEST_S = 2.0
WAITING = RetryPolicy(attempts=5, initial_s=3.0, max_s=30.0, jitter_s=0.0, budget_s=90.0)


class Clock:
    def __init__(self) -> None:
        self.now = 5000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(model_retry, "_clock", fake)

    async def sleep(seconds: float) -> None:
        fake.now += seconds

    monkeypatch.setattr(model_retry.asyncio, "sleep", sleep)
    for model in (A, B):
        model_retry._limited_until[model] = model_retry.time.monotonic() + 60
    yield fake
    model_retry.forget_rate_limits()


class SlowGenai(FakeGenai):
    """Every request takes ``REQUEST_S`` on the fake clock before it answers (or 429s)."""

    def __init__(self, clock: Clock, busy, request_s: float = REQUEST_S):
        super().__init__(busy)
        self.clock, self.request_s, self.started = clock, request_s, []

    async def generate_content(self, *, model, contents, config):
        self.started.append(self.clock.now)
        self.clock.now += self.request_s
        return await super().generate_content(model=model, contents=contents, config=config)


async def _both_busy(clock: Clock, client: SlowGenai):
    llm = _gemini(A, client)
    llm.policy = WAITING
    start = clock.now
    with _turn(A, B) as (stats, records), pytest.raises(ModelRateLimited):
        await _collect(llm, _request(A))
    return clock.now - start, stats, records


async def test_requests_count_against_the_budget(clock):
    client = SlowGenai(clock, busy={A, B})
    elapsed, stats, records = await _both_busy(clock, client)
    # A at 0-2, wait 3, A at 5-7 (probe spent), B at 7-9; B's next wait (3 s) would end past 10
    assert client.calls == [A, A, B]
    assert elapsed <= model_retry._BOTH_LIMITED_BUDGET_S + REQUEST_S
    assert [r["type"] for r in records].count("model_fallback") == 1  # "both busy" for the user
    assert stats.switched_to == B


async def test_every_request_starts_before_the_deadline(clock):
    client = SlowGenai(clock, busy={A, B}, request_s=4.5)
    start = clock.now
    elapsed, _stats, _records = await _both_busy(clock, client)
    # A at 0-4.5, wait 3, A at 7.5-12: past the deadline, so B never starts
    assert client.calls == [A, A]
    assert all(t - start < model_retry._BOTH_LIMITED_BUDGET_S for t in client.started)
    assert elapsed <= model_retry._BOTH_LIMITED_BUDGET_S + 4.5


async def test_a_sibling_that_answers_in_time_still_answers(clock):
    client = SlowGenai(clock, busy={A})
    llm = _gemini(A, client)
    llm.policy = WAITING
    with _turn(A, B) as (stats, _records):
        await _collect(llm, _request(A))
    assert client.calls == [A, A, B] and stats.switched_to == B


async def test_without_both_remembered_there_is_no_deadline(clock):
    model_retry.forget_rate_limits()
    client = SlowGenai(clock, busy={A, B})
    llm = _gemini(A, client)
    llm.policy = WAITING
    with _turn(A, B), pytest.raises(ModelRateLimited):
        await _collect(llm, _request(A))
    assert client.calls == [A, A] + [B] * 5  # the probe, then the sibling's full schedule
