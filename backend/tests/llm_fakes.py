"""Fakes for the LLM providers (feature 035): a scripted Anthropic transport and a genai stub.

Claude runs on the real client the provider layer builds (``AsyncAnthropic`` under
``anthropic``, ``AsyncAnthropicVertex`` under ``vertex``) with a mock transport underneath, so
tests see the request bodies as sent and the SDK parses the scripted replies. No live calls.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest

from wcl_agent.llm import generation, provider

SENTINEL_KEY = "sk-ant-test-SENTINEL-035"


# --- Messages API replies ---------------------------------------------------------------


def text(value: str) -> dict:
    return {"type": "text", "text": value}


def message(*content: dict, stop_reason: str = "end_turn", model: str = "claude-haiku-5-5") -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": list(content),
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def server_tool_use(name: str = "web_search", tool_id: str = "srvtoolu_1") -> dict:
    return {"type": "server_tool_use", "id": tool_id, "name": name, "input": {"query": "spec"}}


def search_results(*results: tuple[str, str], tool_id: str = "srvtoolu_1") -> dict:
    """A ``web_search_tool_result`` with ``(title, url)`` results."""
    return {
        "type": "web_search_tool_result",
        "tool_use_id": tool_id,
        "content": [
            {"type": "web_search_result", "title": title, "url": url, "encrypted_content": "enc", "page_age": None}
            for title, url in results
        ],
    }


def search_error(code: str, tool_id: str = "srvtoolu_1") -> dict:
    return {
        "type": "web_search_tool_result",
        "tool_use_id": tool_id,
        "content": {"type": "web_search_tool_result_error", "error_code": code},
    }


def fetch_result(url: str, title: str, tool_id: str = "srvtoolu_2") -> dict:
    return {
        "type": "web_fetch_tool_result",
        "tool_use_id": tool_id,
        "content": {
            "type": "web_fetch_result",
            "url": url,
            "retrieved_at": None,
            "content": {
                "type": "document",
                "source": {"type": "text", "media_type": "text/plain", "data": "page"},
                "title": title,
                "citations": None,
            },
        },
    }


def rate_limited() -> tuple[int, dict]:
    return 429, {"type": "error", "error": {"type": "rate_limit_error", "message": "busy"}}


def web_search_not_enabled() -> tuple[int, dict]:
    return 400, {
        "type": "error",
        "error": {"type": "invalid_request_error", "message": "Web search is not enabled for this organization."},
    }


class ScriptedClaude:
    """Answers each Messages API request with the next scripted reply (a message dict, or
    ``(status, error body)``) and records the request bodies and hosts."""

    def __init__(self, *replies: dict | tuple[int, dict]) -> None:
        self.replies = list(replies)
        self.bodies: list[dict] = []
        self.hosts: list[str] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.bodies.append(json.loads(request.content))
        self.hosts.append(request.url.host)
        assert self.replies, "unexpected Claude request"
        item = self.replies.pop(0)
        if isinstance(item, tuple):
            status, body = item
            return httpx2.Response(status, json=body)
        return httpx2.Response(200, json=item)


class FakeGenai:
    """``client.aio.models.generate_content`` returning or raising each scripted item in turn."""

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.calls: list[SimpleNamespace] = []
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._generate))

    async def _generate(self, *, model: str, contents: Any, config: Any) -> Any:
        self.calls.append(SimpleNamespace(model=model, contents=contents, config=config))
        assert self.replies, "unexpected genai request"
        item = self.replies.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def gemini_reply(value: str, sources: tuple[tuple[str, str], ...] = ()) -> SimpleNamespace:
    """A genai response with grounding chunks for ``(title, uri)`` sources."""
    chunks = [SimpleNamespace(web=SimpleNamespace(title=t, uri=u)) for t, u in sources]
    gm = SimpleNamespace(grounding_chunks=chunks)
    return SimpleNamespace(text=value, candidates=[SimpleNamespace(grounding_metadata=gm)])


# --- fixtures ---------------------------------------------------------------------------


class _Llm:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.monkeypatch = monkeypatch

    def use(self, value: str) -> None:
        """Switch the provider for this test (with a key under ``anthropic``, no role overrides)."""
        self.monkeypatch.setenv("WCL_LLM_PROVIDER", value)
        self.monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL_KEY)
        self.monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-1")
        for env in provider.ROLE_ENV.values():
            self.monkeypatch.delenv(env, raising=False)
        provider.active_provider.cache_clear()

    def claude(self, *replies: dict | tuple[int, dict]) -> ScriptedClaude:
        """Route the provider's Claude client through a scripted transport."""
        api = ScriptedClaude(*replies)

        def build() -> Any:
            http = anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(api))
            extra = {} if provider.active_provider() == "anthropic" else {"access_token": "test-token"}
            return provider.async_anthropic_client(http_client=http, max_retries=0, **extra)

        self.monkeypatch.setattr(generation, "_claude_client", build)
        return api

    def genai(self, *replies: Any) -> FakeGenai:
        fake = FakeGenai(*replies)
        self.monkeypatch.setattr(generation, "_genai_client", lambda: fake)
        return fake


@pytest.fixture
def llm(monkeypatch):
    """Provider switch plus Claude and genai fakes; by default both fakes reject any call."""
    helper = _Llm(monkeypatch)
    helper.claude()
    helper.genai()
    yield helper
    provider.active_provider.cache_clear()


@pytest.fixture
def no_sleep(monkeypatch):
    async def _no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("wcl_agent.llm.model_retry.asyncio.sleep", _no_sleep)
