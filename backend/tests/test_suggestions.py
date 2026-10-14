"""US1 follow-up suggestions: parsing, caps, trivial handling, frame schema.

The live model call in `generate_followups` is exercised in quickstart.md; here we
test the deterministic logic (parsing/cap/dedup) and the fail-closed behavior that
needs no network.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.schemas import SuggestionsFrame
from backend.app.suggestions import generate_followups, parse_followups


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


async def test_generate_followups_rate_limited_returns_empty_without_waiting(monkeypatch):
    from google.genai import errors as genai_errors

    calls = {"n": 0}

    class _Models:
        async def generate_content(self, **kwargs):
            calls["n"] += 1
            raise genai_errors.APIError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}})

    class _Aio:
        models = _Models()

    class _Client:
        aio = _Aio()

    async def _no_sleep(*a, **k):  # any backoff here would delay the player's answer
        raise AssertionError("suggestions must not sleep/retry")

    monkeypatch.setattr("backend.app.suggestions._client", _Client())
    monkeypatch.setattr("backend.app.suggestions.asyncio.sleep", _no_sleep)
    assert await generate_followups("gemini-3.6-flash", "q", "a real answer") == []
    assert calls["n"] == 1  # one attempt, no retry


# --- PERF-005: fixed cheap model, thinking off, time-boxed --------------------------------


async def test_generate_followups_uses_suggest_model_without_thinking(monkeypatch):
    from backend.app import suggestions

    seen = {}

    class _Models:
        async def generate_content(self, *, model, contents, config):
            seen.update(model=model, config=config)

            class R:
                text = '["What about my healers?"]'

            return R()

    class _Client:
        class aio:
            models = _Models()

    monkeypatch.setattr(suggestions, "_client", _Client())
    out = await generate_followups("gemini-3.1-pro-preview", "q", "a real answer")
    assert out == ["What about my healers?"]
    assert seen["model"] == suggestions._SUGGEST_MODEL  # never the (slow) chat model
    assert seen["config"].thinking_config.thinking_budget == 0


async def test_generate_followups_times_out_to_empty(monkeypatch):
    import asyncio

    from backend.app import suggestions

    class _Models:
        async def generate_content(self, **kwargs):
            await asyncio.sleep(10)

    class _Client:
        class aio:
            models = _Models()

    monkeypatch.setattr(suggestions, "_client", _Client())
    monkeypatch.setattr(suggestions, "SUGGEST_TIMEOUT_S", 0.05)
    assert await generate_followups("gemini-3.6-flash", "q", "a real answer") == []
