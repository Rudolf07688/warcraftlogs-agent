"""Findings synthesis service (feature 007 / US2-US3): genai mocked, off-loop + timeout."""

from __future__ import annotations

import time

import pytest

from backend.app.services import report_synthesis as rs


async def test_happy_path_returns_markdown(monkeypatch):
    def fake_generate(model, prompt):
        assert "ANALYSIS CONTENT" in prompt  # the slice is embedded
        return "## Summary\n\nFound a 99 parse.\n"

    monkeypatch.setattr(rs, "_generate", fake_generate)
    out = await rs.synthesize_findings(
        [{"role": "agent", "content": "The parse was 99."}], scope="conversation"
    )
    assert out.startswith("## Summary")


async def test_empty_model_output_returns_empty(monkeypatch):
    # The service returns "" when the model produces nothing; the endpoint treats that
    # as a fail-closed error (FR-018). A real no-findings doc is emitted by the model.
    monkeypatch.setattr(rs, "_generate", lambda model, prompt: "")
    out = await rs.synthesize_findings([{"role": "agent", "content": "hi"}], scope="conversation")
    assert out == ""


async def test_exception_propagates(monkeypatch):
    def boom(model, prompt):
        raise RuntimeError("model down")

    monkeypatch.setattr(rs, "_generate", boom)
    with pytest.raises(RuntimeError):
        await rs.synthesize_findings([{"role": "agent", "content": "x"}], scope="conversation")


async def test_timeout_raises(monkeypatch):
    monkeypatch.setattr(rs, "_TIMEOUT_S", 0.05)

    def slow(model, prompt):
        time.sleep(0.5)
        return "late"

    monkeypatch.setattr(rs, "_generate", slow)
    with pytest.raises((TimeoutError, Exception)):
        await rs.synthesize_findings([{"role": "agent", "content": "x"}], scope="conversation")


def test_build_input_truncates_oldest_first(monkeypatch):
    monkeypatch.setattr(rs, "_MAX_INPUT_CHARS", 50)
    msgs = [
        {"role": "user", "content": "OLDEST " * 20},
        {"role": "agent", "content": "NEWEST FINDINGS"},
    ]
    text = rs._build_input(msgs, scope="conversation", question=None)
    assert "NEWEST FINDINGS" in text  # recent content kept
    assert "truncated" in text


def test_build_input_includes_question_for_message_scope():
    text = rs._build_input(
        [{"role": "agent", "content": "answer"}],
        scope="message",
        question="what was the parse?",
    )
    assert "Originating question" in text
    assert "what was the parse?" in text


def test_generate_caps_output_tokens(monkeypatch):
    # QA SEC-003: the findings call has an output budget.
    seen = {}

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            seen["config"] = config
            return type("R", (), {"text": "## Summary\n\nok"})()

    monkeypatch.setattr("wcl_agent.vertex.genai_client", lambda: type("C", (), {"models": FakeModels()})())
    assert rs._generate("m", "p") == "## Summary\n\nok"
    assert seen["config"].max_output_tokens == rs._MAX_OUTPUT_TOKENS
