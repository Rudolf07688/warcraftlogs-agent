"""Feature 011: retry policy, error classification, per-turn stats."""

from __future__ import annotations

import anthropic
import httpx2
import pytest
from google.genai import errors as genai_errors

from wcl_agent.model_retry import (
    ModelRateLimited,
    RetryPolicy,
    TurnStats,
    is_rate_limited,
    retry_after_hint,
)


def _genai_error(code: int, status: str | None = None) -> genai_errors.APIError:
    body = {"error": {"code": code, "message": "boom", "status": status or "X"}}
    return genai_errors.APIError(code, body)


def _anthropic_response(status: int, headers: dict | None = None) -> httpx2.Response:
    return httpx2.Response(
        status, headers=headers or {}, request=httpx2.Request("POST", "https://vertex.test")
    )


def _anthropic_error(cls, status: int, headers: dict | None = None):
    return cls("boom", response=_anthropic_response(status, headers), body=None)


# --- classification (FR-002) ------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        _genai_error(429, "RESOURCE_EXHAUSTED"),
        _genai_error(503, "UNAVAILABLE"),
        _genai_error(400, "RESOURCE_EXHAUSTED"),  # status wins when code is unhelpful
        _anthropic_error(anthropic.RateLimitError, 429),
        _anthropic_error(anthropic.OverloadedError, 529),
        _anthropic_error(anthropic.APIStatusError, 503),
    ],
)
def test_rate_limit_errors_are_classified(exc):
    assert is_rate_limited(exc)


@pytest.mark.parametrize(
    "exc",
    [
        _genai_error(400, "INVALID_ARGUMENT"),
        _genai_error(404, "NOT_FOUND"),
        _genai_error(500, "INTERNAL"),
        _anthropic_error(anthropic.BadRequestError, 400),
        _anthropic_error(anthropic.APIStatusError, 500),
        RuntimeError("network"),
        ValueError("bad"),
    ],
)
def test_other_errors_are_not_rate_limits(exc):
    assert not is_rate_limited(exc)


# --- retry-after hint (FR-007) -------------------------------------------------------


def test_retry_after_hint_reads_numeric_header():
    exc = _anthropic_error(anthropic.RateLimitError, 429, {"retry-after": "7"})
    assert retry_after_hint(exc) == 7.0


def test_retry_after_hint_ignores_http_date_and_missing():
    exc = _anthropic_error(
        anthropic.RateLimitError, 429, {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}
    )
    assert retry_after_hint(exc) is None
    assert retry_after_hint(_anthropic_error(anthropic.RateLimitError, 429)) is None
    assert retry_after_hint(_genai_error(429)) is None
    assert retry_after_hint(RuntimeError("x")) is None


# --- delay schedule (FR-001) ---------------------------------------------------------


def test_delay_grows_exponentially_and_caps(monkeypatch):
    monkeypatch.setattr("wcl_agent.model_retry.random.uniform", lambda a, b: 0.0)
    p = RetryPolicy(initial_s=2.0, max_s=30.0, exp_base=2.0, jitter_s=1.0)
    assert [p.delay_for(n) for n in (1, 2, 3, 4, 5)] == [2.0, 4.0, 8.0, 16.0, 30.0]


def test_delay_adds_bounded_jitter():
    p = RetryPolicy(initial_s=2.0, jitter_s=1.0)
    for _ in range(50):
        assert 2.0 <= p.delay_for(1) <= 3.0


def test_delay_prefers_server_hint():
    p = RetryPolicy(initial_s=2.0)
    assert p.delay_for(1, hint_s=12.5) == 12.5
    assert p.delay_for(1, hint_s=-1) >= 2.0  # nonsense hint ignored


# --- stats -----------------------------------------------------------------------------


def test_turn_stats_rounds_and_cap():
    s = TurnStats(model="m")
    assert s.tool_rounds == 0
    s.model_requests = 1
    assert s.tool_rounds == 0
    s.model_requests = 4
    assert s.tool_rounds == 3
    assert not s.cap_reached(RetryPolicy(round_cap=6))
    assert s.cap_reached(RetryPolicy(round_cap=3))


def test_turn_stats_emit_is_safe_without_and_with_failing_notify():
    TurnStats(model="m").emit({"type": "model_retry"})  # no notify → no-op
    seen: list[dict] = []
    s = TurnStats(model="m", notify=seen.append)
    s.emit({"type": "model_retry", "attempt": 1})
    assert seen == [{"type": "model_retry", "attempt": 1}]

    def boom(_):
        raise RuntimeError("ui gone")

    TurnStats(model="m", notify=boom).emit({"type": "model_retry"})  # swallowed


def test_model_rate_limited_message():
    exc = ModelRateLimited(5, 42.0, RuntimeError("429"))
    assert exc.attempts == 5 and exc.waited_s == 42.0
    assert "5 attempt" in str(exc) and "429" in str(exc)


# --- the retry loop (US1) ----------------------------------------------------------------

from wcl_agent.model_retry import current_turn, generate_with_retry  # noqa: E402


def _script(failures: list[BaseException], chunks: tuple[str, ...] = ("a", "b")):
    """Return an ``inner`` factory that raises each failure once, then yields chunks."""
    calls = {"n": 0}

    async def inner():
        idx = calls["n"]
        calls["n"] += 1
        if idx < len(failures):
            raise failures[idx]
        for c in chunks:
            yield c

    return inner, calls


async def _collect(inner, policy):
    return [x async for x in generate_with_retry(inner, policy)]


@pytest.fixture
def no_sleep(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(d):
        slept.append(d)

    monkeypatch.setattr("wcl_agent.model_retry.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("wcl_agent.model_retry.random.uniform", lambda a, b: 0.0)
    return slept


@pytest.fixture
def turn():
    seen: list[dict] = []
    stats = TurnStats(model="m", notify=seen.append)
    token = current_turn.set(stats)
    yield stats, seen
    current_turn.reset(token)


async def test_retries_twice_then_succeeds_and_notifies(no_sleep, turn):
    stats, seen = turn
    inner, calls = _script([_genai_error(429), _genai_error(503)])
    out = await _collect(inner, RetryPolicy(attempts=5, initial_s=2.0))
    assert out == ["a", "b"]
    assert calls["n"] == 3
    assert stats.retries == 2 and stats.waited_s == 6.0  # 2s + 4s
    assert no_sleep == [2.0, 4.0]
    assert [(r["type"], r["attempt"], r["max_attempts"]) for r in seen] == [
        ("model_retry", 1, 5),
        ("model_retry", 2, 5),
    ]
    assert all(r["wait_s"] > 0 for r in seen)


async def test_attempts_exhausted_raises_model_rate_limited(no_sleep, turn):
    stats, _ = turn
    inner, _ = _script([_genai_error(429)] * 10)
    with pytest.raises(ModelRateLimited) as exc:
        await _collect(inner, RetryPolicy(attempts=3, initial_s=1.0))
    assert exc.value.attempts == 3
    assert exc.value.waited_s == 3.0  # 1s + 2s
    assert stats.retries == 2


async def test_budget_exhausted_before_attempts(no_sleep, turn):
    inner, _ = _script([_genai_error(429)] * 10)
    with pytest.raises(ModelRateLimited) as exc:
        await _collect(inner, RetryPolicy(attempts=5, initial_s=10.0, max_s=10.0, budget_s=15.0))
    assert exc.value.attempts == 2  # one 10s wait fit; the second would exceed 15s
    assert exc.value.waited_s == 10.0


async def test_non_rate_limit_error_is_not_retried(no_sleep, turn):
    _, seen = turn
    inner, calls = _script([_genai_error(400, "INVALID_ARGUMENT")])
    with pytest.raises(genai_errors.APIError):
        await _collect(inner, RetryPolicy())
    assert calls["n"] == 1 and seen == [] and no_sleep == []


async def test_error_after_first_chunk_is_not_retried(no_sleep, turn):
    stats, _ = turn

    async def inner():
        yield "a"
        raise _genai_error(429)

    with pytest.raises(genai_errors.APIError):
        await _collect(inner, RetryPolicy())
    assert stats.retries == 0 and no_sleep == []


async def test_retry_disabled_turn_fails_fast(no_sleep):
    stats = TurnStats(model="m", retry_enabled=False)
    token = current_turn.set(stats)
    try:
        inner, calls = _script([_genai_error(429)])
        with pytest.raises(ModelRateLimited) as exc:
            await _collect(inner, RetryPolicy(attempts=5))
    finally:
        current_turn.reset(token)
    assert exc.value.attempts == 1 and calls["n"] == 1 and no_sleep == []


async def test_without_a_turn_retries_silently(no_sleep):
    assert current_turn.get() is None
    inner, calls = _script([_anthropic_error(anthropic.RateLimitError, 429, {"retry-after": "3"})])
    assert await _collect(inner, RetryPolicy()) == ["a", "b"]
    assert calls["n"] == 2 and no_sleep == [3.0]  # the server hint was honoured


async def test_retry_wrappers_expose_policy_and_disable_sdk_retries():
    from wcl_agent.model_retry import RetryingClaude, RetryingGemini

    g = RetryingGemini(model="gemini-3.6-flash", policy=RetryPolicy(attempts=2))
    assert g.policy.attempts == 2 and g.retry_options.attempts == 1
    c = RetryingClaude(model="claude-test", policy=RetryPolicy(attempts=4))
    assert c.policy.attempts == 4


# --- request counting + round cap (US2) ----------------------------------------------------

from google.adk.models.llm_request import LlmRequest  # noqa: E402

from wcl_agent.model_retry import WRAP_UP_INSTRUCTION, make_before_model_callback  # noqa: E402


def _request(model: str) -> LlmRequest:
    req = LlmRequest(model=model)
    req.append_instructions(["Base system prompt."])
    return req


def test_callback_counts_requests_and_caps_gemini(turn):
    stats, _ = turn
    cb = make_before_model_callback(RetryPolicy(round_cap=2))
    reqs = [_request("gemini-3.6-flash") for _ in range(3)]
    for i, req in enumerate(reqs, start=1):
        assert cb(None, req) is None
        assert stats.model_requests == i
    # requests 1 and 2 (rounds 0 and 1) untouched
    for req in reqs[:2]:
        assert WRAP_UP_INSTRUCTION not in req.config.system_instruction
        assert req.config.tool_config is None
    # request 3 (round 2 == cap): wrap-up injected and tools hard-disabled
    assert WRAP_UP_INSTRUCTION in reqs[2].config.system_instruction
    assert "Base system prompt." in reqs[2].config.system_instruction
    assert reqs[2].config.tool_config.function_calling_config.mode == "NONE"


def test_callback_cap_on_claude_uses_instruction_only(turn):
    stats, _ = turn
    cb = make_before_model_callback(RetryPolicy(round_cap=1))
    cb(None, _request("claude-sonnet-4@20250514"))
    req = _request("claude-sonnet-4@20250514")
    cb(None, req)
    assert stats.model_requests == 2
    assert WRAP_UP_INSTRUCTION in req.config.system_instruction
    assert req.config.tool_config is None


def test_callback_is_noop_without_a_turn():
    assert current_turn.get() is None
    cb = make_before_model_callback(RetryPolicy(round_cap=1))
    req = _request("gemini-3.6-flash")
    for _ in range(5):
        assert cb(None, req) is None
    assert WRAP_UP_INSTRUCTION not in req.config.system_instruction
    assert req.config.tool_config is None
