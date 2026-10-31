"""Findings synthesis service (feature 007 / US2-US3; 035 provider-neutral): model faked, timeout."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.app.services import report_synthesis as rs
from backend.tests.llm_fakes import llm, message, text  # noqa: F401 - fixture
from wcl_agent.llm.provider import ModelRole


def _fake_generate(monkeypatch, reply):
    """Replace the model call; ``reply(prompt)`` returns the text or raises."""
    calls = []

    async def fake(prompt, role, *, max_tokens, policy):
        calls.append(SimpleNamespace(prompt=prompt, role=role, max_tokens=max_tokens, policy=policy))
        return await reply(prompt)

    monkeypatch.setattr(rs, "generate_text", fake)
    return calls


async def test_happy_path_returns_markdown(monkeypatch):
    async def reply(prompt):
        assert "ANALYSIS CONTENT" in prompt  # the slice is embedded
        return "## Summary\n\nFound a 99 parse.\n"

    _fake_generate(monkeypatch, reply)
    out = await rs.synthesize_findings(
        [{"role": "agent", "content": "The parse was 99."}], scope="conversation"
    )
    assert out.startswith("## Summary")


async def test_empty_model_output_returns_empty(monkeypatch):
    # The service returns "" when the model produces nothing; the endpoint treats that
    # as a fail-closed error (FR-018). A real no-findings doc is emitted by the model.
    async def reply(prompt):
        return ""

    _fake_generate(monkeypatch, reply)
    out = await rs.synthesize_findings([{"role": "agent", "content": "hi"}], scope="conversation")
    assert out == ""


async def test_exception_propagates(monkeypatch):
    async def boom(prompt):
        raise RuntimeError("model down")

    _fake_generate(monkeypatch, boom)
    with pytest.raises(RuntimeError):
        await rs.synthesize_findings([{"role": "agent", "content": "x"}], scope="conversation")


async def test_timeout_raises(monkeypatch):
    monkeypatch.setattr(rs, "_TIMEOUT_S", 0.05)

    async def slow(prompt):
        await asyncio.sleep(0.5)
        return "late"

    _fake_generate(monkeypatch, slow)
    with pytest.raises(TimeoutError):
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


async def test_generate_caps_output_tokens_on_the_report_role_with_one_attempt(monkeypatch):
    # QA SEC-003: the findings call has an output budget; feature 035: report role, no retry.
    async def reply(prompt):
        return "## Summary\n\nok"

    calls = _fake_generate(monkeypatch, reply)
    assert await rs.synthesize_findings([{"role": "agent", "content": "x"}], scope="conversation") == "## Summary\n\nok"
    [call] = calls
    assert call.max_tokens == rs._MAX_OUTPUT_TOKENS
    assert call.role is ModelRole.REPORT
    assert call.policy.attempts == 1


async def test_vertex_report_config_is_unchanged(llm):
    llm.use("vertex")
    genai = llm.genai(SimpleNamespace(text="  ## Summary\n\nok  "))
    assert await rs.synthesize_findings([{"role": "agent", "content": "x"}], scope="conversation") == "## Summary\n\nok"
    [call] = genai.calls
    assert call.model == "gemini-3.6-flash"
    assert call.config.max_output_tokens == rs._MAX_OUTPUT_TOKENS
    assert call.config.temperature is None and call.config.thinking_config is None


async def test_report_on_the_anthropic_api(llm):
    llm.use("anthropic")
    api = llm.claude(message(text("## Summary\n\nFound a 99 parse."), model="claude-sonnet-5-5"))
    out = await rs.synthesize_findings([{"role": "agent", "content": "The parse was 99."}], scope="message", question="q")
    assert out.startswith("## Summary")
    [body] = api.bodies
    assert body["model"] == "claude-sonnet-5-5"
    assert body["max_tokens"] == rs._MAX_OUTPUT_TOKENS


def test_prompt_describes_the_report_components():
    # The PDF renderer styles these conventions (pdf_report._components).
    for marker in ("## At a Glance", "**Label:** value (short context)", "> [!TIP]", "`04:05`", "## Recommendations"):
        assert marker in rs._SYSTEM, marker
