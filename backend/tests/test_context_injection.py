"""PERF-004: the KNOWN PLAYER CONTEXT reaches each model request but never the ADK history."""

from __future__ import annotations

from types import SimpleNamespace

from google.adk.models.llm_request import LlmRequest
from google.genai import types

from backend.app import agent_runner
from wcl_agent.llm.model_retry import (
    RetryPolicy,
    TurnStats,
    current_turn,
    inject_preamble,
    make_before_model_callback,
)


def _text(role: str, text: str) -> types.Content:
    return types.Content(role=role, parts=[types.Part(text=text)])


def _history() -> list[types.Content]:
    return [
        _text("user", "old question"),
        _text("model", "old answer"),
        _text("user", "new question"),
        types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name="t", args={}))]),
        types.Content(
            role="user",
            parts=[types.Part(function_response=types.FunctionResponse(name="t", response={"ok": 1}))],
        ),
    ]


def test_inject_preamble_targets_the_turns_user_message_without_mutating_history():
    history = _history()
    original = history[2]
    request = LlmRequest(contents=list(history))

    inject_preamble(request, "KNOWN PLAYER CONTEXT: Alpha")

    injected = request.contents[2]
    assert injected is not original  # a new Content; the stored event is untouched
    assert [p.text for p in injected.parts] == ["KNOWN PLAYER CONTEXT: Alpha\n\n", "new question"]
    assert [p.text for p in original.parts] == ["new question"]
    assert request.contents[0] is history[0] and request.contents[4] is history[4]


def test_before_model_callback_injects_only_with_a_turn_preamble():
    callback = make_before_model_callback(RetryPolicy())

    plain = LlmRequest(contents=_history())
    callback(None, plain)  # no turn installed (CLI): untouched
    assert [p.text for p in plain.contents[2].parts] == ["new question"]

    stats = TurnStats(model="gemini-3.6-flash", preamble="CTX")
    token = current_turn.set(stats)
    try:
        request = LlmRequest(contents=_history())
        callback(None, request)
        assert request.contents[2].parts[0].text == "CTX\n\n"
        assert stats.model_requests == 1
    finally:
        current_turn.reset(token)


async def test_stream_response_keeps_the_preamble_out_of_the_stored_message(monkeypatch):
    seen = {}

    class _Runner:
        async def run_async(self, *, user_id, session_id, new_message, run_config):
            seen["message"] = new_message
            seen["preamble"] = current_turn.get().preamble
            yield SimpleNamespace(
                content=None,
                grounding_metadata=None,
                usage_metadata=SimpleNamespace(prompt_token_count=1234),
            )

    async def _no_session(*args, **kwargs):
        return None

    monkeypatch.setattr(agent_runner, "_get_runner", lambda model: _Runner())
    monkeypatch.setattr(agent_runner, "_ensure_session", _no_session)

    records = [
        r
        async for r in agent_runner.stream_response(
            "gemini-3.6-flash", "s1", "how did I do?", context_preamble="KNOWN PLAYER CONTEXT: Alpha"
        )
    ]

    assert [p.text for p in seen["message"].parts] == ["how did I do?"]  # what ADK stores
    assert seen["preamble"] == "KNOWN PLAYER CONTEXT: Alpha"  # what the callback injects
    assert records == []


def test_turn_stats_tracks_prompt_tokens():
    stats = TurnStats(model="m")
    stats.record_prompt_tokens(None)
    assert stats.last_prompt_tokens is None
    stats.record_prompt_tokens(900)
    stats.record_prompt_tokens(400)
    assert (stats.last_prompt_tokens, stats.max_prompt_tokens) == (400, 900)
