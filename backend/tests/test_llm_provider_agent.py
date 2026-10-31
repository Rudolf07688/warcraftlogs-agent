"""Feature 032 (sc-249 AC 3, FR-013): the ADK agent's Claude runs on the active provider.

Real ``AsyncAnthropic`` / ``AsyncAnthropicVertex`` clients built by the provider layer, on an
``httpx2.MockTransport`` that scripts the API's SSE answers: nothing leaves the process. The
turn goes through the real ``agent_runner.stream_response`` and ``build_agent``.
"""

from __future__ import annotations

import json

import anthropic
import httpx2
import pytest
from google.adk.models.anthropic_llm import AnthropicLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from backend.app import agent_runner
from backend.app import greeting as greeting_mod
from wcl_agent.agent import build_agent
from wcl_agent.capabilities import ToolGroup
from wcl_agent.llm import model_retry, provider
from wcl_agent.llm.model_retry import THINKING_BINDING_BETA, RetryingClaude, RetryPolicy
from wcl_agent.llm.provider import ModelRole

SENTINEL_KEY = "sk-ant-test-SENTINEL-agent-42"
CLAUDE = "claude-sonnet-5-5"


# --- scripted Anthropic API -----------------------------------------------------------------


def _sse(*events: dict) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def _message_start(model: str) -> dict:
    return {
        "type": "message_start",
        "message": {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 1},
        },
    }


def text_answer(text: str, model: str = CLAUDE) -> bytes:
    return _sse(
        _message_start(model),
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 5}},
        {"type": "message_stop"},
    )


def tool_call(name: str, model: str = CLAUDE) -> bytes:
    return _sse(
        _message_start(model),
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "tool_use", "id": "toolu_1", "name": name, "input": {}},
        },
        {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": "{}"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None}, "usage": {"output_tokens": 5}},
        {"type": "message_stop"},
    )


class ScriptedApi:
    """A mock transport that answers each request with the next scripted response."""

    def __init__(self, *responses: bytes | tuple[int, dict]) -> None:
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, tuple):
            status, headers = item
            return httpx2.Response(status, headers=headers, json={"type": "error", "error": {"type": "rate_limit_error", "message": "busy"}})
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=item)

    def bodies(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests]


# --- fixtures -------------------------------------------------------------------------------


@pytest.fixture
def use_provider(monkeypatch):
    def install(value: str, *, key: str | None = None) -> None:
        monkeypatch.setenv("WCL_LLM_PROVIDER", value)
        if key is None:
            monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        else:
            monkeypatch.setenv("ANTHROPIC_API_KEY", key)
        provider.active_provider.cache_clear()

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-1")
    monkeypatch.delenv("WCL_MODEL_LOCATION", raising=False)
    yield install
    provider.active_provider.cache_clear()


async def ping() -> dict:
    """Health check."""
    return {"status": "ok"}


@pytest.fixture
def scripted(monkeypatch):
    """Route the provider-built Claude client through a scripted transport, and run the turn
    on a fresh in-memory runner built by the real ``build_agent``."""

    def install(api: ScriptedApi, **client_kwargs) -> ScriptedApi:
        real = provider.async_anthropic_client

        def build(**kwargs):
            http = anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(api))
            return real(http_client=http, **client_kwargs, **kwargs)

        monkeypatch.setattr(model_retry, "async_anthropic_client", build)
        session_service = InMemorySessionService()
        monkeypatch.setattr(agent_runner, "_session_service", session_service)
        policy = RetryPolicy(initial_s=0, jitter_s=0)

        def runner(model: str) -> Runner:
            agent = build_agent(model, retry=policy, extra_groups=(ToolGroup("Test", (ping,)),))
            return Runner(agent=agent, app_name=agent_runner.APP_NAME, session_service=session_service)

        monkeypatch.setattr(agent_runner, "_get_runner", runner)
        return api

    return install


async def _turn(model: str, text: str = "hi") -> list[dict]:
    return [r async for r in agent_runner.stream_response(model, f"s-{model}", text)]


# --- client selection -----------------------------------------------------------------------


def test_anthropic_provider_gives_claude_the_api_client(use_provider):
    use_provider("anthropic", key=SENTINEL_KEY)
    client = RetryingClaude(model=CLAUDE)._anthropic_client
    assert type(client) is anthropic.AsyncAnthropic
    assert client.max_retries == 0


def test_vertex_provider_gives_claude_the_vertex_client(use_provider):
    use_provider("vertex")
    client = RetryingClaude(model=CLAUDE)._anthropic_client
    assert type(client) is anthropic.AsyncAnthropicVertex
    assert client.region == "global" and client.max_retries == 0


# --- a full turn on the Anthropic API -------------------------------------------------------


async def test_chat_turn_with_a_tool_round_runs_on_the_anthropic_api(use_provider, scripted):
    use_provider("anthropic", key=SENTINEL_KEY)
    api = scripted(ScriptedApi(tool_call("ping"), text_answer("All quiet.")))

    records = await _turn(CLAUDE, "ping the server")

    assert [r["name"] for r in records if r["type"] == "tool_end"] == ["ping"]
    assert "".join(r["text"] for r in records if r["type"] == "token") == "All quiet."
    assert len(api.requests) == 2
    for request, body in zip(api.requests, api.bodies(), strict=True):
        assert request.url.host == "api.anthropic.com" and request.url.path == "/v1/messages"
        assert request.headers["x-api-key"] == SENTINEL_KEY
        assert body["model"] == CLAUDE
        assert "ping" in {t["name"] for t in body["tools"]}


async def test_claude_requests_use_adaptive_thinking_and_drop_stale_blocks(use_provider, scripted):
    use_provider("anthropic", key=SENTINEL_KEY)
    api = scripted(ScriptedApi(text_answer("Hello.")))

    await _turn(CLAUDE)

    (body,) = api.bodies()
    assert body["thinking"] == {
        "type": "adaptive",
        "display": "summarized",
        "block_binding": {"prefix_mismatch_behavior": "drop_block"},
    }
    assert THINKING_BINDING_BETA in api.requests[0].headers["anthropic-beta"]


async def test_rate_limit_is_retried_by_the_shared_loop(use_provider, scripted):
    use_provider("anthropic", key=SENTINEL_KEY)
    api = scripted(ScriptedApi((429, {"retry-after": "0"}), text_answer("Back.")))

    records = await _turn(CLAUDE)

    assert [r["type"] for r in records if r["type"] == "model_retry"] == ["model_retry"]
    assert "".join(r["text"] for r in records if r["type"] == "token") == "Back."
    assert len(api.requests) == 2  # the SDK's own retries are off: only our loop retried


async def test_greeting_runs_on_the_greeting_role_model(use_provider, scripted):
    use_provider("anthropic", key=SENTINEL_KEY)
    api = scripted(ScriptedApi(text_answer("Well met!", model="claude-haiku-5-5")))

    text = await greeting_mod._generate_greeting(provider.role_model(ModelRole.GREETING))

    assert text == "Well met!"
    assert api.bodies()[0]["model"] == "claude-haiku-5-5"


async def test_claude_on_vertex_works_again(use_provider, scripted):
    """The same turn on Vertex: before 032 ADK rejected the agent's thinking config."""
    use_provider("vertex")
    api = scripted(ScriptedApi(text_answer("From Vertex.")), access_token="fake-token")

    records = await _turn(CLAUDE)

    assert "".join(r["text"] for r in records if r["type"] == "token") == "From Vertex."
    (request,) = api.requests
    assert request.url.host == "aiplatform.googleapis.com"
    assert f"/models/{CLAUDE}:streamRawPredict" in request.url.path
    assert THINKING_BINDING_BETA in request.headers["anthropic-beta"]
    assert json.loads(request.content)["thinking"]["type"] == "adaptive"


# --- the agent's thinking configuration -----------------------------------------------------


def test_thinking_budget_is_adaptive_for_claude_only():
    assert build_agent(CLAUDE).planner.thinking_config.thinking_budget == -1
    gemini = build_agent("gemini-3.6-flash").planner.thinking_config
    assert gemini.include_thoughts is True and gemini.thinking_budget is None


def test_adk_still_has_the_hooks_retrying_claude_overrides():
    """Pin: an ADK upgrade that renames these would silently drop drop_block or our client."""
    assert callable(getattr(AnthropicLlm, "_build_anthropic_kwargs", None))
    assert "_anthropic_client" in vars(AnthropicLlm)
    assert "_build_anthropic_kwargs" in vars(RetryingClaude)
    assert "_anthropic_client" in vars(RetryingClaude)
