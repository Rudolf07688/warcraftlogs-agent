"""084: one re-run per model call (sc-586 Gemini empty STOP, sc-580 Claude time bound).

Bounds first (brief 084): a call gets at most one re-run of any kind, every re-run counts as a
model request (a round toward ``round_cap``), and a streamed Claude call is cut at
``CLAUDE_CALL_TIMEOUT_S`` with its stream closed. The parents are faked at the ADK class (no
network); the hung-stream test runs the real Anthropic client on a scripted transport.
"""

from __future__ import annotations

import asyncio
import contextlib

import anthropic
import httpx2
import pytest
from google.adk.models.anthropic_llm import AnthropicLlm
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from backend.tests.test_llm_provider_agent import (  # noqa: F401 - fixtures used by name
    CLAUDE,
    SENTINEL_KEY,
    _message_start,
    _sse,
    text_answer,
    use_provider,
)
from wcl_agent.llm import model_retry, provider
from wcl_agent.llm.model_retry import (
    WRAP_UP_INSTRUCTION,
    RetryingClaude,
    RetryingGemini,
    RetryPolicy,
    TurnStats,
    current_turn,
    make_before_model_callback,
)

GEMINI = "gemini-3.1-pro-preview"
STOP = types.FinishReason.STOP
MAX_TOKENS = types.FinishReason.MAX_TOKENS


# --- fakes ------------------------------------------------------------------------------------


def _response(*parts: types.Part, partial=False, finish=None, candidates=None) -> LlmResponse:
    return LlmResponse(
        content=types.Content(role="model", parts=list(parts)) if parts else None,
        partial=partial,
        finish_reason=finish,
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10, candidates_token_count=candidates
        ),
    )


def empty_stop() -> list[LlmResponse]:
    """What the 11-20 live pass saw: a stop with an empty text part and 0 candidate tokens."""
    return [
        _response(types.Part(text=""), partial=True),
        _response(types.Part(text=""), finish=STOP, candidates=0),
    ]


def answer(text: str) -> list[LlmResponse]:
    return [
        _response(types.Part(text=text), partial=True),
        _response(types.Part(text=text), finish=STOP, candidates=5),
    ]


def thought(text: str) -> LlmResponse:
    return _response(types.Part(text=text, thought=True), partial=True)


class Parent:
    """Stands in for the ADK parent's ``generate_content_async``: one script per call.

    A script is a list of responses, or a callable returning an async iterator (for streams
    that hang or advance the clock). Records each call's effort and whether its stream closed.
    """

    def __init__(self, *scripts) -> None:
        self.scripts = list(scripts)
        self.efforts: list[str | None] = []
        self.closed: list[bool] = []

    def install(self, monkeypatch, cls) -> Parent:
        parent = self

        async def generate_content_async(self, llm_request, stream=False):
            parent.efforts.append(getattr(llm_request.config, "effort", None))
            index = len(parent.closed)
            parent.closed.append(False)
            script = parent.scripts.pop(0) if parent.scripts else answer("unscripted")
            try:
                if callable(script):
                    async for item in script():
                        yield item
                else:
                    for item in script:
                        yield item
            finally:
                parent.closed[index] = True

        monkeypatch.setattr(cls, "generate_content_async", generate_content_async)
        return self

    @property
    def calls(self) -> int:
        return len(self.efforts)


@contextlib.contextmanager
def turn(model: str):
    records: list[dict] = []
    stats = TurnStats(model=model, notify=records.append)
    token = current_turn.set(stats)
    try:
        yield stats
    finally:
        current_turn.reset(token)


def _request(model: str) -> LlmRequest:
    request = LlmRequest(model=model, contents=[types.Content(role="user", parts=[types.Part(text="is frost mage difficult?")])])
    request.config = types.GenerateContentConfig()
    return request


async def _collect(llm, request, *, stream=True) -> list[LlmResponse]:
    return [r async for r in llm.generate_content_async(request, stream=stream)]


def _answer_text(responses) -> str:
    return "".join(
        p.text for r in responses if not r.partial and r.content for p in r.content.parts or [] if p.text and not p.thought
    )


@pytest.fixture(autouse=True)
def _reset_rate_limit_memory():
    model_retry.forget_rate_limits()
    yield
    model_retry.forget_rate_limits()


# --- sc-586: Gemini empty STOP ----------------------------------------------------------------


async def test_an_empty_gemini_stop_is_rerun_once_and_the_answer_used(monkeypatch):
    parent = Parent(empty_stop(), answer("Frost is one of the easier specs.")).install(monkeypatch, Gemini)
    with turn(GEMINI) as stats:
        out = await _collect(RetryingGemini(model=GEMINI), _request(GEMINI))

    assert parent.calls == 2
    assert _answer_text(out) == "Frost is one of the easier specs."
    # The empty final never reaches the agent: only one final response comes out.
    assert [r.finish_reason for r in out if not r.partial] == [STOP]
    assert stats.empty_retries == 1 and stats.budget_retries == 0


async def test_an_always_empty_gemini_gets_exactly_one_rerun(monkeypatch):
    parent = Parent(empty_stop(), empty_stop(), empty_stop()).install(monkeypatch, Gemini)
    with turn(GEMINI) as stats:
        out = await _collect(RetryingGemini(model=GEMINI), _request(GEMINI))

    assert parent.calls == 2  # the second outcome stands: the runner says "no answer"
    assert [r.finish_reason for r in out if not r.partial] == [STOP]
    assert stats.empty_retries == 1


@pytest.mark.parametrize(
    "final",
    [
        _response(types.Part(text="Yes."), finish=STOP, candidates=0),  # text, whatever the count
        _response(types.Part(function_call=types.FunctionCall(name="ping", args={})), finish=STOP, candidates=0),
        _response(types.Part(text=""), finish=STOP, candidates=3),  # tokens were produced
        _response(types.Part(text=""), finish=MAX_TOKENS, candidates=0),  # not a stop
    ],
)
async def test_only_a_truly_empty_stop_is_rerun(monkeypatch, final):
    parent = Parent([final]).install(monkeypatch, Gemini)
    with turn(GEMINI) as stats:
        await _collect(RetryingGemini(model=GEMINI), _request(GEMINI))
    assert parent.calls == 1 and stats.empty_retries == 0


async def test_an_empty_stop_without_usage_is_rerun(monkeypatch):
    bare = LlmResponse(content=None, partial=False, finish_reason=STOP)
    parent = Parent([bare], answer("Ok.")).install(monkeypatch, Gemini)
    with turn(GEMINI):
        out = await _collect(RetryingGemini(model=GEMINI), _request(GEMINI))
    assert parent.calls == 2 and _answer_text(out) == "Ok."


async def test_without_a_turn_the_rerun_still_happens(monkeypatch):
    parent = Parent(empty_stop(), answer("Ok.")).install(monkeypatch, Gemini)
    assert current_turn.get() is None
    out = await _collect(RetryingGemini(model=GEMINI), _request(GEMINI))
    assert parent.calls == 2 and _answer_text(out) == "Ok."


# --- rate bound: re-runs are rounds -----------------------------------------------------------


async def test_every_rerun_counts_as_a_request_and_n_such_calls_trip_the_round_cap(monkeypatch):
    Parent(*[empty_stop() for _ in range(20)]).install(monkeypatch, Gemini)
    before_model = make_before_model_callback(RetryPolicy(round_cap=6))
    llm = RetryingGemini(model=GEMINI)
    capped_at = None
    with turn(GEMINI) as stats:
        for call in range(1, 6):
            request = _request(GEMINI)
            before_model(None, request)
            await _collect(llm, request)
            assert stats.model_requests == 2 * call  # the request and its one re-run
            if capped_at is None and WRAP_UP_INSTRUCTION in (request.config.system_instruction or ""):
                capped_at = call
    # Re-runs count: 3 calls make 6 requests, so the 4th call is told to wrap up (not the 7th).
    assert capped_at == 4
    assert stats.empty_retries == 5


async def test_a_claude_budget_rerun_counts_as_a_request(monkeypatch):
    cutoff = [thought("Comparing every boss..."), _response(types.Part(text="Comparing every boss...", thought=True), finish=MAX_TOKENS)]
    parent = Parent(cutoff, answer("Here.")).install(monkeypatch, AnthropicLlm)
    with turn(CLAUDE) as stats:
        stats.model_requests = 1  # the before-model callback counted the request
        out = await _collect(RetryingClaude(model=CLAUDE), _request(CLAUDE))
    assert parent.efforts == [None, "low"]
    assert _answer_text(out) == "Here."
    assert stats.budget_retries == 1 and stats.model_requests == 2


# --- time bound: a streamed Claude call is cut at CLAUDE_CALL_TIMEOUT_S ----------------------


@pytest.fixture
def clock(monkeypatch):
    """The ``_clock`` seam (fact clock-seam-wall-clock-budgets), advanced by the fake streams."""
    now = {"t": 1000.0}
    monkeypatch.setattr(model_retry, "_clock", lambda: now["t"])
    return now


def thinks_forever(clock, step_s: float = 50.0):
    """A stream that keeps sending thought chunks, each ``step_s`` later, far past the bound
    (20 chunks, so a missing cut fails the test instead of hanging it)."""

    async def stream():
        for _ in range(20):
            clock["t"] += step_s
            yield thought("Still comparing. ")
        yield _response(types.Part(text="Still comparing. ", thought=True), finish=MAX_TOKENS)

    return stream


async def test_a_call_still_thinking_at_the_bound_is_cut_and_rerun_once_at_low_effort(monkeypatch, clock):
    parent = Parent(thinks_forever(clock), answer("The short version.")).install(monkeypatch, AnthropicLlm)
    with turn(CLAUDE) as stats:
        started = clock["t"]
        out = await _collect(RetryingClaude(model=CLAUDE), _request(CLAUDE))

    assert parent.calls == 2 and parent.efforts == [None, "low"]
    assert parent.closed == [True, True]  # the cut stream was closed, not left running
    assert _answer_text(out) == "The short version."
    # Cut at the wait after the first chunk past the bound: 180 s at 50 s a chunk is the 4th
    # chunk (200 s), which arrived and is passed on (088a BUG-007).
    assert clock["t"] - started == 200.0
    assert len([r for r in out if r.partial and r.content.parts[0].thought]) == 4
    assert stats.budget_retries == 1


async def test_a_rerun_that_is_cut_too_ends_the_call(monkeypatch, clock):
    parent = Parent(thinks_forever(clock), thinks_forever(clock), answer("never")).install(monkeypatch, AnthropicLlm)
    with turn(CLAUDE) as stats:
        out = await _collect(RetryingClaude(model=CLAUDE), _request(CLAUDE))

    assert parent.calls == 2 and parent.closed == [True, True]  # no third call
    assert stats.budget_retries == 1
    finals = [r for r in out if not r.partial]
    assert len(finals) == 1 and finals[0].finish_reason == MAX_TOKENS and finals[0].content is None


async def test_a_call_cut_after_answer_text_keeps_the_text_and_is_not_rerun(monkeypatch, clock):
    async def answers_slowly():
        for chunk in ["Short ", "version: ", "frost is ", "easy."]:
            clock["t"] += 50.0
            yield _response(types.Part(text=chunk), partial=True)

    parent = Parent(answers_slowly, answer("repeat")).install(monkeypatch, AnthropicLlm)
    with turn(CLAUDE) as stats:
        out = await _collect(RetryingClaude(model=CLAUDE), _request(CLAUDE))

    assert parent.calls == 1 and parent.closed == [True]
    final = out[-1]
    assert not final.partial and final.finish_reason == MAX_TOKENS
    # What the player saw (the 4th chunk arrived, 088a BUG-007), then the cut line (088a BUG-001).
    assert final.content.parts[0].text == "Short version: frost is easy.\n\n" + model_retry.CUT_LINE
    assert stats.budget_retries == 0


async def test_a_hung_claude_stream_is_cut_at_the_bound_and_its_connection_closed(use_provider, monkeypatch):
    """The real client on a transport whose body stops after the first thought: nothing more
    ever arrives, so only the deadline can end the call."""
    use_provider("anthropic", key=SENTINEL_KEY)
    monkeypatch.setattr(model_retry, "CLAUDE_CALL_TIMEOUT_S", 0.3)
    streams: list[Hanging] = []

    class Hanging(httpx2.AsyncByteStream):
        def __init__(self) -> None:
            self.closed = False

        async def __aiter__(self):
            yield _sse(
                _message_start(CLAUDE),
                {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "", "signature": ""}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "Weighing..."}},
            )
            await asyncio.Event().wait()  # a peer that never sends the rest

        async def aclose(self) -> None:
            self.closed = True

    answers = [None, text_answer("Low effort answer.")]

    def handler(request):
        item = answers.pop(0)
        if item is None:
            stream = Hanging()
            streams.append(stream)
            return httpx2.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=item)

    real = provider.async_anthropic_client

    def build(**kwargs):
        return real(http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)), **kwargs)

    monkeypatch.setattr(model_retry, "async_anthropic_client", build)
    request = _request(CLAUDE)
    request.config.thinking_config = types.ThinkingConfig(include_thoughts=True, thinking_budget=-1)

    with turn(CLAUDE) as stats:
        out = await asyncio.wait_for(_collect(RetryingClaude(model=CLAUDE), request), timeout=10)

    assert streams and streams[0].closed  # the cut call's HTTP stream was released
    assert not answers  # exactly one more request: the re-run
    assert _answer_text(out) == "Low effort answer."
    assert stats.budget_retries == 1


async def test_a_non_streamed_claude_call_has_no_time_bound(monkeypatch, clock):
    async def slow():
        clock["t"] += 500.0  # past the bound, but the CLI's non-streamed call is not bounded
        for item in answer("Done."):
            yield item

    parent = Parent(slow).install(monkeypatch, AnthropicLlm)
    out = await _collect(RetryingClaude(model=CLAUDE), _request(CLAUDE), stream=False)
    assert parent.calls == 1 and _answer_text(out) == "Done."


async def test_the_bound_applies_to_each_rate_limit_attempt_not_to_the_waits(monkeypatch, clock):
    """The 90 s retry wait budget is unchanged: waiting between attempts does not eat the bound."""

    async def fake_sleep(seconds: float) -> None:
        clock["t"] += seconds

    monkeypatch.setattr(model_retry.asyncio, "sleep", fake_sleep)

    def rate_limited():
        async def stream():
            clock["t"] += 100.0
            raise anthropic.RateLimitError(
                "busy",
                response=httpx2.Response(429, headers={"retry-after": "80"}, request=httpx2.Request("POST", "https://x")),
                body=None,
            )
            yield  # pragma: no cover - makes this an async generator

        return stream

    async def answers_late():
        clock["t"] += 170.0  # within the bound counted from this attempt's start
        for item in answer("After the wait."):
            yield item

    parent = Parent(rate_limited(), answers_late).install(monkeypatch, AnthropicLlm)
    llm = RetryingClaude(model=CLAUDE, policy=RetryPolicy(attempts=2, jitter_s=0))
    with turn(CLAUDE) as stats:
        out = await _collect(llm, _request(CLAUDE))
    assert parent.calls == 2 and _answer_text(out) == "After the wait."
    assert stats.retries == 1 and stats.budget_retries == 0
