"""079: prompt caching (sc-568) and the output budget (sc-567) on the Claude chat path.

Real provider-built clients on the scripted transport of ``test_llm_provider_agent``: the turn
goes through ``agent_runner.stream_response`` and ``build_agent``; nothing leaves the process.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from google.adk.models.llm_request import LlmRequest
from google.genai import types as genai_types

from backend.tests.test_llm_provider_agent import (  # noqa: F401 - fixtures used by name
    CLAUDE,
    SENTINEL_KEY,
    ScriptedApi,
    _message_start,
    _sse,
    _turn,
    scripted,
    text_answer,
    tool_call,
    use_provider,
)
from wcl_agent import agent as agent_mod
from wcl_agent.llm import model_retry
from wcl_agent.llm.model_retry import (
    CLAUDE_MAX_TOKENS,
    CLAUDE_NONSTREAM_MAX_TOKENS,
    RetryingClaude,
    TurnStats,
    current_turn,
)


class TurnApi(ScriptedApi):
    """Also notes the turn each request was made in."""

    def __call__(self, request):
        self.turns = [*getattr(self, "turns", []), current_turn.get()]
        return super().__call__(request)


def thinking_cutoff() -> bytes:
    """A streamed call whose thinking used the whole output budget: no text, no tool call."""
    return _sse(
        _message_start(CLAUDE),
        {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "", "signature": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "Comparing every boss..."}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "sig"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "max_tokens", "stop_sequence": None}, "usage": {"output_tokens": CLAUDE_MAX_TOKENS}},
        {"type": "message_stop"},
    )


def _uncached(value):
    """The request with its cache markers removed: they are not part of the cached prefix."""
    if isinstance(value, dict):
        return {k: _uncached(v) for k, v in value.items() if k != "cache_control"}
    if isinstance(value, list):
        return [_uncached(v) for v in value]
    return value


@pytest.fixture
def ticking_clock(monkeypatch):
    """Each instruction build is a minute later, as across a long turn."""
    start = datetime(2026, 11, 7, 20, 0, tzinfo=UTC)
    calls = iter(range(100))

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return start + timedelta(minutes=next(calls))

    monkeypatch.setattr(agent_mod, "datetime", Clock)


# --- sc-568: the second call of a turn reads the first one's prompt from the cache -----------


@pytest.mark.parametrize("provider_name", ["anthropic", "vertex"])
async def test_later_calls_of_a_turn_extend_the_cached_prefix(use_provider, scripted, ticking_clock, provider_name):
    use_provider(provider_name, key=SENTINEL_KEY if provider_name == "anthropic" else None)
    client_kwargs = {"access_token": "fake-token"} if provider_name == "vertex" else {}
    api = scripted(ScriptedApi(tool_call("ping"), text_answer("All quiet.")), **client_kwargs)

    records = await _turn(CLAUDE, "ping the server")

    assert "".join(r["text"] for r in records if r["type"] == "token") == "All quiet."
    first, second = api.bodies()
    for body in (first, second):
        assert body["tools"][-1]["cache_control"] == {"type": "ephemeral"}
        head = body["system"][0]
        assert head["cache_control"] == {"type": "ephemeral"}
        # 087: the time block leads the turn's user message, after the history, not the system.
        assert "<CURRENT_TIME>" not in json.dumps(body["system"])
        assert body["messages"][0]["content"][0]["text"].startswith("<CURRENT_TIME>")
        assert body["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    # The first request, breakpoint at its end, is a prefix of the second although the clock
    # moved between them: the time block stays the turn's first.
    assert "2026-11-07 20:00 UTC" in second["messages"][0]["content"][0]["text"]
    assert _uncached(second["tools"]) == _uncached(first["tools"])
    assert _uncached(second["system"]) == _uncached(first["system"])
    n = len(first["messages"])
    assert _uncached(second["messages"][:n]) == _uncached(first["messages"])


async def test_turn_stats_get_the_full_prompt_and_the_cache_reads(use_provider, scripted, monkeypatch):
    use_provider("anthropic", key=SENTINEL_KEY)
    answer = text_answer("Cached.").decode()
    start = _message_start(CLAUDE)
    cached_start = copy.deepcopy(start)
    cached_start["message"]["usage"] = {
        "input_tokens": 500,
        "cache_read_input_tokens": 60_000,
        "cache_creation_input_tokens": 1_000,
        "output_tokens": 1,
    }
    answer = answer.replace(json.dumps(start), json.dumps(cached_start)).encode()
    scripted(ScriptedApi(answer))
    seen: list[tuple] = []
    real = TurnStats.record_prompt_tokens
    monkeypatch.setattr(
        TurnStats, "record_prompt_tokens", lambda self, count, cached=None: (seen.append((count, cached)), real(self, count, cached))
    )

    await _turn(CLAUDE)

    assert seen == [(61_500, 60_000)]


# --- sc-567: room for the answer after thinking, and one re-run when there is none ----------


async def test_a_streamed_chat_request_carries_the_raised_output_limit(use_provider, scripted):
    use_provider("anthropic", key=SENTINEL_KEY)
    api = scripted(ScriptedApi(text_answer("Hello.")))

    await _turn(CLAUDE)

    assert api.bodies()[0]["max_tokens"] == CLAUDE_MAX_TOKENS == 32_000


async def test_a_non_streamed_request_stays_under_the_sdk_streaming_limit(use_provider):
    """The CLI calls without streaming; the SDK refuses such a request above ~21k tokens."""
    use_provider("anthropic", key=SENTINEL_KEY)
    bodies: list[dict] = []

    def handler(request):
        bodies.append(json.loads(request.content))
        message = _message_start(CLAUDE)["message"] | {
            "content": [{"type": "text", "text": "Hi."}],
            "stop_reason": "end_turn",
        }
        return httpx2.Response(200, json=message)

    import anthropic

    client = anthropic.AsyncAnthropic(
        api_key=SENTINEL_KEY, http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler))
    )
    model = RetryingClaude(model=CLAUDE, client=client)
    request = LlmRequest(
        model=CLAUDE, contents=[genai_types.Content(role="user", parts=[genai_types.Part(text="hi")])]
    )

    responses = [r async for r in model.generate_content_async(request, stream=False)]

    assert responses[-1].content.parts[0].text == "Hi."
    assert bodies[0]["max_tokens"] == CLAUDE_NONSTREAM_MAX_TOKENS


async def test_a_thinking_only_cutoff_is_rerun_once_at_low_effort(use_provider, scripted, caplog):
    use_provider("anthropic", key=SENTINEL_KEY)
    api = scripted(TurnApi(thinking_cutoff(), text_answer("Here is the overview.")))

    records = await _turn(CLAUDE, "overview of every boss")

    # The answer arrives once; the cut-off call's thoughts never become answer text.
    assert "".join(r["text"] for r in records if r["type"] == "token") == "Here is the overview."
    first, second = api.bodies()
    assert "output_config" not in first
    assert second["output_config"] == {"effort": "low"}
    assert second["thinking"]["display"] == "summarized"  # contract:claude-thinking-summaries
    assert second["max_tokens"] == CLAUDE_MAX_TOKENS
    assert api.turns[-1].budget_retries == 1
    assert "ended on max_tokens with no answer" in caplog.text


async def test_the_rerun_happens_only_once(use_provider, scripted):
    use_provider("anthropic", key=SENTINEL_KEY)
    api = scripted(TurnApi(thinking_cutoff(), thinking_cutoff()))

    records = await _turn(CLAUDE)

    assert len(api.requests) == 2
    assert not [r for r in records if r["type"] == "token"]
    assert api.turns[-1].budget_retries == 1


@pytest.fixture(autouse=True)
def _reset_rate_limit_memory():
    model_retry.forget_rate_limits()
    yield
    model_retry.forget_rate_limits()
