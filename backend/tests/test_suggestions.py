"""US1 follow-up suggestions: parsing, caps, trivial handling, frame schema.

The live model call in `generate_followups` is exercised in quickstart.md; here we
test the deterministic logic (parsing/cap/dedup) and the fail-closed behavior that
needs no network.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.schemas import SuggestionsFrame
from backend.app.suggestions import generate_followups, parse_followups
from backend.tests.llm_fakes import llm, message, text  # noqa: F401 - fixture
from wcl_agent.llm import generation


def test_parse_json_array_caps_at_three():
    raw = '["one?", "two?", "three?", "four?"]'
    assert parse_followups(raw) == ["one?", "two?", "three?"]


def test_parse_strips_bullets_numbering_and_quotes():
    raw = '1. "What are the parse scores?"\n- Who died most?\n* Any cooldown gaps?'
    assert parse_followups(raw) == [
        "What are the parse scores?",
        "Who died most?",
        "Any cooldown gaps?",
    ]


def test_parse_dedupes_case_insensitively():
    raw = '["Parse scores?", "parse scores?", "Deaths?"]'
    assert parse_followups(raw) == ["Parse scores?", "Deaths?"]


def test_parse_drops_empty_and_overlong():
    raw = '["", "   ", "' + "x" * 500 + '", "Good one?"]'
    assert parse_followups(raw) == ["Good one?"]


def test_parse_empty_input_returns_empty():
    assert parse_followups("") == []
    assert parse_followups("[]") == []


@pytest.mark.parametrize("answer", ["", "   ", "(no response)"])
async def test_generate_followups_trivial_answer_returns_empty_without_network(answer):
    # Returns [] before any client call for trivial/empty answers.
    assert await generate_followups("gemini-3.6-flash", "hi", answer) == []


def test_suggestions_frame_rejects_more_than_three():
    with pytest.raises(ValidationError):
        SuggestionsFrame(suggestions=["a", "b", "c", "d"])


def test_suggestions_frame_valid():
    frame = SuggestionsFrame(suggestions=["a", "b"])
    assert frame.type == "suggestions"
    assert frame.model_dump()["suggestions"] == ["a", "b"]


# --- feature 011 / FR-012: suggestions fail fast and silently on a rate limit --------------


async def test_generate_followups_rate_limited_returns_empty_without_waiting(llm, monkeypatch):
    from google.genai import errors as genai_errors

    async def _no_sleep(*a, **k):  # any backoff here would delay the player's answer
        raise AssertionError("suggestions must not sleep/retry")

    llm.use("vertex")
    genai = llm.genai(genai_errors.APIError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}))
    monkeypatch.setattr("wcl_agent.llm.model_retry.asyncio.sleep", _no_sleep)
    assert await generate_followups("gemini-3.6-flash", "q", "a real answer") == []
    assert len(genai.calls) == 1  # one attempt, no retry


# --- PERF-005: fixed cheap model, thinking off, time-boxed --------------------------------


async def test_generate_followups_uses_suggest_model_without_thinking(llm):
    llm.use("vertex")
    genai = llm.genai(SimpleNamespace(text='["What about my healers?"]'))
    out = await generate_followups("gemini-3.1-pro-preview", "q", "a real answer")
    assert out == ["What about my healers?"]
    [call] = genai.calls
    assert call.model == "gemini-3.6-flash"  # the fast role, never the (slow) chat model
    assert call.config.thinking_config.thinking_budget == 0


async def test_generate_followups_times_out_to_empty(llm, monkeypatch):
    import asyncio

    from backend.app import suggestions

    class _Hung:
        aio = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: asyncio.sleep(10)))

    llm.use("vertex")
    monkeypatch.setattr(generation, "_genai_client", lambda: _Hung())
    monkeypatch.setattr(suggestions, "SUGGEST_TIMEOUT_S", 0.05)
    assert await generate_followups("gemini-3.6-flash", "q", "a real answer") == []


# --- feature 035: the fast Claude model under the Anthropic API ----------------------------


async def test_generate_followups_on_the_anthropic_api(llm):
    llm.use("anthropic")
    api = llm.claude(message(text('["Who died first?"]')))
    assert await generate_followups("claude-sonnet-5-5", "q", "a real answer") == ["Who died first?"]
    [body] = api.bodies
    assert body["model"] == "claude-haiku-5-5"
    assert body["thinking"] == {"type": "disabled"}
