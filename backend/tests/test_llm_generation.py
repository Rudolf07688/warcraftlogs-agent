"""The provider-neutral generation entry points (feature 035): faked Anthropic and genai only.

Claude runs on the real ``AsyncAnthropic`` / ``AsyncAnthropicVertex`` client over a mock
transport, so the request bodies are asserted as sent and the replies are parsed by the SDK.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

from backend.tests.llm_fakes import llm, message, no_sleep, rate_limited, text  # noqa: F401 - fixtures
from wcl_agent.llm import generation
from wcl_agent.llm.model_retry import ModelRateLimited, RetryPolicy
from wcl_agent.llm.provider import ModelRole

ONE = RetryPolicy(attempts=1)
TWO = RetryPolicy(attempts=2, initial_s=0, jitter_s=0)


# --- model per role and client per family -----------------------------------------------


async def test_anthropic_runs_the_fast_role_on_haiku_and_never_touches_genai(llm):
    llm.use("anthropic")
    api = llm.claude(message(text("hello")))
    genai = llm.genai()
    out = await generation.generate_text("hi", ModelRole.FAST, max_tokens=32, policy=ONE)
    assert out == "hello"
    [body] = api.bodies
    assert body["model"] == "claude-haiku-5-5"
    assert body["max_tokens"] == 32
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert genai.calls == []


async def test_anthropic_runs_the_report_role_on_sonnet(llm):
    llm.use("anthropic")
    api = llm.claude(message(text("## Summary")))
    await generation.generate_text("p", ModelRole.REPORT, max_tokens=16_384, policy=ONE)
    assert api.bodies[0]["model"] == "claude-sonnet-5-5"


async def test_vertex_runs_the_fast_role_on_gemini_and_never_touches_claude(llm):
    llm.use("vertex")
    api = llm.claude()
    genai = llm.genai(SimpleNamespace(text="hola"))
    out = await generation.generate_text("hi", ModelRole.FAST, max_tokens=32, policy=ONE)
    assert out == "hola"
    [call] = genai.calls
    assert call.model == "gemini-3.6-flash"
    assert call.contents == "hi"
    assert api.bodies == []


# --- request shapes ---------------------------------------------------------------------


async def test_claude_never_gets_a_temperature(llm):
    llm.use("anthropic")
    api = llm.claude(message(text("t")))
    await generation.generate_text("p", ModelRole.FAST, max_tokens=32, policy=ONE, temperature=0.2)
    assert "temperature" not in api.bodies[0]


async def test_thinking_off_disables_thinking_on_haiku(llm):
    # Clarify Q2: Haiku accepts thinking "disabled" at its default effort.
    llm.use("anthropic")
    api = llm.claude(message(text("t")))
    await generation.generate_text("p", ModelRole.FAST, max_tokens=32, policy=ONE, thinking=False)
    body = api.bodies[0]
    assert body["thinking"] == {"type": "disabled"}
    assert "output_config" not in body


async def test_thinking_off_lowers_effort_on_other_claude_models(llm, monkeypatch):
    # Clarify Q2: Sonnet and Opus 5.5 reject "disabled"; they get the lowest effort instead.
    llm.use("anthropic")
    monkeypatch.setenv("WCL_SUGGEST_MODEL", "claude-sonnet-5-5")
    api = llm.claude(message(text("t"), model="claude-sonnet-5-5"))
    await generation.generate_text("p", ModelRole.FAST, max_tokens=32, policy=ONE, thinking=False)
    body = api.bodies[0]
    assert body["model"] == "claude-sonnet-5-5"
    assert body["output_config"] == {"effort": "low"}
    assert "thinking" not in body


async def test_thinking_on_sends_no_thinking_or_effort(llm):
    llm.use("anthropic")
    api = llm.claude(message(text("t")))
    await generation.generate_text("p", ModelRole.REPORT, max_tokens=64, policy=ONE)
    assert "thinking" not in api.bodies[0] and "output_config" not in api.bodies[0]


async def test_gemini_config_carries_only_what_the_call_site_asked_for(llm):
    llm.use("vertex")
    genai = llm.genai(SimpleNamespace(text="a"), SimpleNamespace(text="b"))
    await generation.generate_text("p", ModelRole.FAST, max_tokens=32, policy=ONE, temperature=0.2, thinking=False)
    await generation.generate_text("p", ModelRole.REPORT, max_tokens=16_384, policy=ONE)
    titles, report = (c.config for c in genai.calls)
    assert (titles.max_output_tokens, titles.temperature, titles.thinking_config.thinking_budget) == (32, 0.2, 0)
    assert report.max_output_tokens == 16_384
    assert report.temperature is None and report.thinking_config is None


async def test_text_blocks_are_joined_and_other_blocks_skipped(llm):
    llm.use("anthropic")
    llm.claude(message({"type": "thinking", "thinking": "", "signature": "s"}, text("a"), text("b")))
    assert await generation.generate_text("p", ModelRole.FAST, max_tokens=32, policy=ONE) == "ab"


async def test_a_refusal_raises(llm):
    llm.use("anthropic")
    llm.claude(message(stop_reason="refusal"))
    with pytest.raises(generation.ModelRefused):
        await generation.generate_text("p", ModelRole.FAST, max_tokens=32, policy=ONE)


# --- the shared retry loop --------------------------------------------------------------


async def test_a_claude_rate_limit_is_retried_by_the_policy(llm, no_sleep):
    llm.use("anthropic")
    api = llm.claude(rate_limited(), message(text("ok")))
    assert await generation.generate_text("p", ModelRole.FAST, max_tokens=32, policy=TWO) == "ok"
    assert len(api.bodies) == 2


async def test_one_attempt_fails_fast_on_a_rate_limit(llm, no_sleep):
    llm.use("anthropic")
    api = llm.claude(rate_limited(), message(text("never")))
    with pytest.raises(ModelRateLimited):
        await generation.generate_text("p", ModelRole.FAST, max_tokens=32, policy=ONE)
    assert len(api.bodies) == 1


async def test_a_gemini_rate_limit_is_retried_by_the_policy(llm, no_sleep):
    llm.use("vertex")
    busy = genai_errors.APIError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}})
    genai = llm.genai(busy, SimpleNamespace(text="ok"))
    assert await generation.generate_text("p", ModelRole.FAST, max_tokens=32, policy=TWO) == "ok"
    assert len(genai.calls) == 2


async def test_clients_are_built_once_per_process(monkeypatch):
    built = []
    monkeypatch.setattr(generation.provider, "genai_client", lambda: built.append(1) or object())
    generation._genai_client.cache_clear()
    try:
        assert generation._genai_client() is generation._genai_client()
        assert built == [1]
    finally:
        generation._genai_client.cache_clear()
