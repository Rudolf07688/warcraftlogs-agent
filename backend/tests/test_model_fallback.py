"""Feature 021: fall back to the same-class sibling model on a lasting rate limit.

The ADK model wrappers run their real request path down to the provider client; only the
client is fake (ADK uses a preset ``client`` on both ``Gemini`` and ``Claude``; it is set
after construction because the field only validates real SDK clients), so the tests also
prove that the switched model id reaches the client call. No Vertex needed.
"""

from __future__ import annotations

import contextlib
import logging
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from google.adk.models.llm_request import LlmRequest
from google.genai import errors as genai_errors
from google.genai import types

from backend.app import agent_runner
from backend.app.model_state import fallback_model_for
from wcl_agent.llm.model_retry import (
    ModelRateLimited,
    RetryingClaude,
    RetryingGemini,
    RetryPolicy,
    TurnStats,
    current_turn,
)
from wcl_agent.llm.models import class_label, model_class, sibling_model

A, B = "gemini-3.8-flash", "gemini-3.7-flash"
CA, CB = "claude-sonnet-4-6", "claude-sonnet-4-5"
POLICY = RetryPolicy(attempts=2, initial_s=0.0, max_s=0.0, jitter_s=0.0)
SKIP = b"skip_thought_signature_validator"


# --- sibling rule (FR-002) ---------------------------------------------------------------

SERVED = [A, B, "gemini-3.8-pro", "gemini-3.6-flash-lite", "claude-sonnet-4-6@20260101"]


@pytest.mark.parametrize(
    ("model", "served", "expected"),
    [
        (A, SERVED, B),  # newest → second
        (B, SERVED, A),  # second → back to the newest
        ("gemini-3.6-flash", [A, B, "gemini-3.6-flash"], A),  # any other peer → newest
        ("gemini-3.8-pro", SERVED, None),  # one served pro
        ("gemini-3.6-flash-lite", SERVED, None),  # flash-lite is its own class
        ("claude-sonnet-4-6@20260101", SERVED, None),  # Claude today: one per class
        (CA, [CA, CB], CB),  # a two-model Claude class falls back too (Q3)
        ("claude-sonnet-4-6@20260101", ["claude-sonnet-4-6@20260101", CB], CB),
        ("gpt-5", SERVED + ["gpt-5"], None),  # outside the discovery naming
        (A, [B], None),  # not served
    ],
)
def test_sibling_model(model, served, expected):
    assert sibling_model(model, served) == expected


def test_model_class_and_label():
    assert model_class(A) == ("google", "flash")
    assert model_class("gemini-3.6-flash-lite") == ("google", "flash-lite")
    assert model_class("claude-opus-4-6@20260101") == ("anthropic", "opus")
    assert model_class("projects/p/models/x") is None
    assert class_label(A) == "Gemini flash"
    assert class_label(CA) == "Claude sonnet"
    assert class_label("gpt-5") is None


def test_fallback_model_for_reads_the_served_set():
    app = SimpleNamespace(state=SimpleNamespace(models=[A, B], default_model=A))
    assert fallback_model_for(app, A) == B
    assert fallback_model_for(app, B) == A
    # No discovered state: falls back to the configured list, like get_model_state.
    bare = SimpleNamespace(state=SimpleNamespace())
    assert fallback_model_for(bare, "not-a-model") is None


# --- fakes -------------------------------------------------------------------------------


def _genai_429() -> genai_errors.ClientError:
    return genai_errors.ClientError(
        429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}}
    )


def _anthropic_429() -> anthropic.RateLimitError:
    response = httpx2.Response(429, request=httpx2.Request("POST", "https://vertex.test"))
    return anthropic.RateLimitError("quota", response=response, body=None)


def _text_response(text: str) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[types.Part(text=text)]),
                finish_reason="STOP",
            )
        ]
    )


class FakeGenai:
    """A genai client whose ``busy`` models answer 429; the rest answer with their id.

    ``api_client.aio.models.generate_content[_stream]`` is what ADK's Gemini calls with
    ``model=llm_request.model``. ``fail_after_first_chunk`` makes the stream 429 after
    one chunk (a mid-stream rate limit).
    """

    vertexai = True

    def __init__(self, busy=(), *, fail_after_first_chunk=False, respond=None):
        self.busy = set(busy)
        self.calls: list[str] = []
        self.contents: list[list[types.Content]] = []
        self.fail_after_first_chunk = fail_after_first_chunk
        self.respond = respond or (lambda model, n: _text_response(f"from {model}"))
        self.aio = SimpleNamespace(models=self)

    async def generate_content(self, *, model, contents, config):
        self.calls.append(model)
        self.contents.append(list(contents))
        if model in self.busy:
            raise _genai_429()
        return self.respond(model, len(self.calls))

    async def generate_content_stream(self, *, model, contents, config):
        first = await self.generate_content(model=model, contents=contents, config=config)
        fail = self.fail_after_first_chunk

        async def chunks():
            yield first
            if fail:
                raise _genai_429()

        return chunks()


class FakeAnthropic:
    """An AsyncAnthropicVertex stand-in: ``busy`` models raise ``RateLimitError``."""

    def __init__(self, busy=()):
        self.busy = set(busy)
        self.calls: list[str] = []
        self.messages = self

    def with_options(self, **_kwargs):
        return self

    async def create(self, **kwargs):
        self.calls.append(kwargs["model"])
        if kwargs["model"] in self.busy:
            raise _anthropic_429()
        return anthropic.types.Message(
            id="msg_1",
            type="message",
            role="assistant",
            model=kwargs["model"],
            content=[anthropic.types.TextBlock(type="text", text=f"from {kwargs['model']}")],
            stop_reason="end_turn",
            usage=anthropic.types.Usage(input_tokens=3, output_tokens=2),
        )


@contextlib.contextmanager
def _turn(model: str, fallback: str | None):
    records: list[dict] = []
    stats = TurnStats(model=model, notify=records.append, fallback_model=fallback)
    token = current_turn.set(stats)
    try:
        yield stats, records
    finally:
        current_turn.reset(token)


def _request(model: str, contents=None) -> LlmRequest:
    contents = contents or [types.Content(role="user", parts=[types.Part(text="how did we do?")])]
    return LlmRequest(model=model, contents=list(contents))


def _gemini(model: str, client) -> RetryingGemini:
    llm = RetryingGemini(model=model, policy=POLICY)
    llm.client = client
    return llm


def _claude(model: str, client) -> RetryingClaude:
    llm = RetryingClaude(model=model, policy=POLICY)
    llm.client = client
    return llm


async def _collect(llm, request, *, stream=False) -> list:
    return [r async for r in llm.generate_content_async(request, stream=stream)]


def _texts(responses) -> list[str]:
    return [p.text for r in responses for p in (r.content.parts if r.content else []) if p.text]


# --- US1: the turn continues on the sibling (Gemini and Anthropic paths) ----------------


@pytest.mark.parametrize("stream", [False, True])
async def test_gemini_switches_to_the_sibling_and_the_client_sees_it(stream):
    client = FakeGenai(busy={A})
    with _turn(A, B) as (stats, records):
        out = await _collect(_gemini(A, client), _request(A), stream=stream)
    assert "from " + B in "".join(_texts(out))
    assert client.calls == [A, A, B]  # the policy's 2 attempts on A, then B
    assert records[-1] == {"type": "model_fallback", "from_model": A, "to_model": B}
    assert [r["type"] for r in records].count("model_fallback") == 1
    assert stats.switched_to == B


async def test_gemini_second_model_switches_back_to_the_first():
    client = FakeGenai(busy={B})
    with _turn(B, A) as (stats, records):
        out = await _collect(_gemini(B, client), _request(B))
    assert _texts(out) == [f"from {A}"]
    assert client.calls == [B, B, A]
    assert records[-1]["to_model"] == A


async def test_later_requests_of_the_turn_go_straight_to_the_sibling():
    client = FakeGenai(busy={A})
    llm = _gemini(A, client)
    with _turn(A, B):
        await _collect(llm, _request(A))
        client.calls.clear()
        out = await _collect(llm, _request(A))  # ADK sets the agent's model on every step
    assert client.calls == [B]
    assert _texts(out) == [f"from {B}"]


async def test_anthropic_switches_to_the_sibling_and_the_client_sees_it():
    client = FakeAnthropic(busy={CA})
    with _turn(CA, CB) as (stats, records):
        out = await _collect(_claude(CA, client), _request(CA))
    assert _texts(out) == [f"from {CB}"]
    assert client.calls == [CA, CA, CB]
    assert records == [
        {"type": "model_retry", "attempt": 1, "max_attempts": 2, "wait_s": 0.0},
        {"type": "model_fallback", "from_model": CA, "to_model": CB},
    ]
    assert stats.switched_to == CB


# --- US2: one switch only; no sibling -------------------------------------------------------


async def test_gemini_both_busy_raises_after_exactly_one_switch():
    client = FakeGenai(busy={A, B})
    with _turn(A, B) as (stats, records):
        with pytest.raises(ModelRateLimited):
            await _collect(_gemini(A, client), _request(A))
    assert client.calls == [A, A, B, B]
    assert [r["type"] for r in records].count("model_fallback") == 1
    assert stats.switched_to == B


async def test_anthropic_both_busy_raises_after_exactly_one_switch():
    client = FakeAnthropic(busy={CA, CB})
    with _turn(CA, CB) as (_stats, records):
        with pytest.raises(ModelRateLimited):
            await _collect(_claude(CA, client), _request(CA))
    assert client.calls == [CA, CA, CB, CB]
    assert [r["type"] for r in records].count("model_fallback") == 1


async def test_sibling_busy_later_in_the_turn_does_not_switch_back():
    client = FakeGenai(busy={A})
    llm = _gemini(A, client)
    with _turn(A, B) as (_stats, records):
        await _collect(llm, _request(A))
        client.busy = {A, B}
        client.calls.clear()
        with pytest.raises(ModelRateLimited):
            await _collect(llm, _request(A))
    assert client.calls == [B, B]
    assert [r["type"] for r in records].count("model_fallback") == 1


@pytest.mark.parametrize("provider", ["gemini", "anthropic"])
async def test_no_sibling_fails_as_before(provider):
    """Claude today (decision 7), or any one-model class: no switch, no record."""
    if provider == "gemini":
        client, model = FakeGenai(busy={A}), A
        llm = _gemini(A, client)
    else:
        client, model = FakeAnthropic(busy={CA}), CA
        llm = _claude(CA, client)
    with _turn(model, None) as (stats, records):
        with pytest.raises(ModelRateLimited):
            await _collect(llm, _request(model))
    assert client.calls == [model, model]
    assert all(r["type"] != "model_fallback" for r in records)
    assert stats.switched_to is None


# --- guards ---------------------------------------------------------------------------------


async def test_non_rate_limit_errors_never_switch():
    client = FakeGenai()

    async def broken(**_kwargs):
        client.calls.append("x")
        raise genai_errors.ClientError(400, {"error": {"code": 400, "message": "bad"}})

    client.generate_content = broken
    with _turn(A, B) as (stats, records):
        with pytest.raises(genai_errors.ClientError):
            await _collect(_gemini(A, client), _request(A))
    assert client.calls == ["x"]
    assert stats.switched_to is None and records == []


async def test_mid_stream_rate_limit_never_switches():
    """Q5: once a chunk was yielded, a switch would duplicate text, so the error stands."""
    client = FakeGenai(fail_after_first_chunk=True)
    seen = []
    with _turn(A, B) as (stats, records):
        with pytest.raises(genai_errors.ClientError):
            async for r in _gemini(A, client).generate_content_async(_request(A), stream=True):
                seen.append(r)
    assert seen  # the first chunk went out once
    assert client.calls == [A]
    assert stats.switched_to is None and records == []


async def test_without_a_turn_the_wrapper_only_retries():
    client = FakeGenai(busy={A})
    assert current_turn.get() is None
    with pytest.raises(ModelRateLimited):
        await _collect(_gemini(A, client), _request(A))
    assert client.calls == [A, A]


async def test_a_request_for_another_model_is_left_alone():
    """E.g. a sub-agent on a different model inside the turn: only the turn's model switches."""
    other = "gemini-3.8-pro"
    client = FakeGenai(busy={other})
    with _turn(A, B) as (stats, records):
        with pytest.raises(ModelRateLimited):
            await _collect(_gemini(other, client), _request(other))
    assert client.calls == [other, other]
    assert stats.switched_to is None
    assert all(r["type"] != "model_fallback" for r in records)


async def test_signature_guard_rewrites_copies_of_the_current_turn_only():
    """R5: pre-switch signatures of the current turn get the bypass value in the switched
    request; the stored contents (the session events) and earlier turns stay untouched."""
    old_call = types.Content(
        role="model",
        parts=[types.Part(function_call=types.FunctionCall(name="t", args={}), thought_signature=b"old")],
    )
    turn_call = types.Content(
        role="model",
        parts=[
            types.Part(function_call=types.FunctionCall(name="t", args={}), thought_signature=b"sig-a"),
            types.Part(text="plain"),
        ],
    )

    def result():
        return types.Content(
            role="user",
            parts=[types.Part(function_response=types.FunctionResponse(name="t", response={}))],
        )

    stored = [
        types.Content(role="user", parts=[types.Part(text="q0")]),
        old_call,
        result(),
        types.Content(role="user", parts=[types.Part(text="q1")]),
        turn_call,
        result(),
    ]
    client = FakeGenai(busy={A})
    with _turn(A, B):
        await _collect(_gemini(A, client), _request(A, stored))

    sent_to_b = client.contents[-1]
    assert sent_to_b[4].parts[0].thought_signature == SKIP
    assert sent_to_b[4].parts[1].thought_signature is None
    assert sent_to_b[1].parts[0].thought_signature == b"old"  # earlier turn: not validated
    # The stored objects were never mutated.
    assert turn_call.parts[0].thought_signature == b"sig-a"
    assert stored[4] is turn_call and old_call.parts[0].thought_signature == b"old"
    # What A was sent still carried A's own signature.
    assert client.contents[0][4].parts[0].thought_signature == b"sig-a"


async def test_signature_guard_is_skipped_for_claude():
    client = FakeAnthropic(busy={CA})
    with _turn(CA, CB) as (stats, _records):
        await _collect(_claude(CA, client), _request(CA))
    assert stats.switched_to == CB  # switched; nothing Gemini-specific was needed


# --- runner (T013) ----------------------------------------------------------------------------


class _Runner:
    def __init__(self, script):
        self._script = script

    async def run_async(self, **kwargs):
        async for ev in self._script(current_turn.get()):
            yield ev


def _text_event(text: str):
    ev = SimpleNamespace(
        grounding_metadata=None,
        usage_metadata=None,
        content=SimpleNamespace(
            parts=[SimpleNamespace(function_call=None, function_response=None, thought=False, text=text)]
        ),
        partial=False,
    )
    ev.is_final_response = lambda: True
    return ev


def _install(monkeypatch, script):
    monkeypatch.setattr(agent_runner, "_get_runner", lambda model: _Runner(script))

    async def _noop(_session_id, _user_id=None):
        return None

    monkeypatch.setattr(agent_runner, "_ensure_session", _noop)


def _stats_line(caplog) -> str:
    (line,) = [r.getMessage() for r in caplog.records if r.getMessage().startswith("turn stats")]
    return line


async def test_runner_carries_the_sibling_and_logs_the_switch(monkeypatch, caplog):
    seen = {}

    async def script(stats):
        seen["fallback"] = stats.fallback_model
        stats.switched_to = stats.fallback_model
        stats.emit({"type": "model_fallback", "from_model": A, "to_model": B})
        yield _text_event("answer")

    _install(monkeypatch, script)
    with caplog.at_level(logging.INFO, logger="backend.app.agent_runner"):
        out = [r async for r in agent_runner.stream_response(A, "s", "hi", fallback_model=B)]
    assert seen["fallback"] == B
    assert out == [
        {"type": "model_fallback", "from_model": A, "to_model": B},
        {"type": "token", "text": "answer"},
    ]
    assert _stats_line(caplog).endswith(f"fallback={B}")


async def test_runner_without_a_sibling_logs_no_switch(monkeypatch, caplog):
    seen = {}

    async def script(stats):
        seen["fallback"] = stats.fallback_model
        yield _text_event("answer")

    _install(monkeypatch, script)
    with caplog.at_level(logging.INFO, logger="backend.app.agent_runner"):
        [r async for r in agent_runner.stream_response(A, "s", "hi")]
    assert seen["fallback"] is None
    assert _stats_line(caplog).endswith("fallback=-")
