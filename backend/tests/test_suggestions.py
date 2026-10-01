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
