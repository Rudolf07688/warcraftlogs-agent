"""Feature 054 (sc-404): one-shot model calls each leave one GenAI client span.

A chat title (the fast role) on Claude under both providers and on Gemini, through the real
``generation`` code on the provider fakes of feature 035. The span carries metadata only.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from opentelemetry.trace import SpanKind, StatusCode

from backend.app.services import conversation_titles
from backend.tests.llm_fakes import llm, message, rate_limited, text  # noqa: F401 - fixture
from backend.tests.test_telemetry_support import otel  # noqa: F401 - fixture
from wcl_agent.llm import generation, provider
from wcl_agent.llm.model_retry import RetryPolicy
from wcl_agent.llm.provider import ModelRole

QUESTION = "QUESTION-SENTINEL-054 who topped dps"
CLAUDE_FAST = "claude-haiku-5-5"


def _genai_title(value: str) -> SimpleNamespace:
    return SimpleNamespace(
        text=value,
        model_version="gemini-3.6-flash-001",
        usage_metadata=SimpleNamespace(prompt_token_count=31, candidates_token_count=4),
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="STOP"))],
    )


def _model_span(capture):
    [span] = [s for s in capture.spans() if s.kind is SpanKind.CLIENT]
    return span


@pytest.mark.parametrize(("active", "provider_name"), [("anthropic", "anthropic"), ("vertex", "gcp.vertex_ai")])
async def test_a_claude_title_call_shows_model_and_tokens(otel, llm, monkeypatch, active, provider_name):
    capture = otel(environment="dev")
    llm.use(active)
    monkeypatch.setenv(provider.ROLE_ENV[ModelRole.FAST], CLAUDE_FAST)
    llm.claude(message(text("A title"), model=CLAUDE_FAST))

    assert await conversation_titles.generate_title(QUESTION, "an answer") == "A title"

    span = _model_span(capture)
    assert span.name == f"chat {CLAUDE_FAST}"
    assert dict(span.attributes) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": provider_name,
        "gen_ai.request.model": CLAUDE_FAST,
        "gen_ai.response.model": CLAUDE_FAST,
        "gen_ai.usage.input_tokens": 1,
        "gen_ai.usage.output_tokens": 1,
        "gen_ai.response.finish_reasons": ("end_turn",),
    }


@pytest.mark.parametrize(("vertexai", "provider_name"), [("true", "gcp.vertex_ai"), ("", "gcp.gen_ai")])
async def test_a_gemini_title_call_shows_model_and_tokens(otel, llm, monkeypatch, vertexai, provider_name):
    capture = otel(environment="dev")
    llm.use("vertex")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", vertexai)
    llm.genai(_genai_title("A title"))

    assert await conversation_titles.generate_title(QUESTION, "an answer") == "A title"

    span = _model_span(capture)
    model = provider.role_model(ModelRole.FAST)
    assert span.name == f"chat {model}"
    assert span.attributes["gen_ai.provider.name"] == provider_name
    assert span.attributes["gen_ai.request.model"] == model
    assert span.attributes["gen_ai.response.model"] == "gemini-3.6-flash-001"
    assert (span.attributes["gen_ai.usage.input_tokens"], span.attributes["gen_ai.usage.output_tokens"]) == (31, 4)
    assert span.attributes["gen_ai.response.finish_reasons"] == ("stop",)
    assert QUESTION not in str(dict(span.attributes))  # metadata only, even in dev


async def test_embeddings_count_their_input_tokens(otel, llm):
    capture = otel(environment="dev")
    llm.use("vertex")

    async def embed_content(*, model, contents, config):
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1], statistics=SimpleNamespace(token_count=n)) for n in (3, 5)]
        )

    fake = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(embed_content=embed_content)))
    llm.monkeypatch.setattr(generation, "_genai_client", lambda: fake)

    await generation.embed_texts("text-embedding-x", ["a", "b"], task="RETRIEVAL_DOCUMENT", dimensions=1, policy=RetryPolicy())

    span = _model_span(capture)
    assert (span.name, span.attributes["gen_ai.operation.name"]) == ("embeddings text-embedding-x", "embeddings")
    assert span.attributes["gen_ai.usage.input_tokens"] == 8


async def test_a_failed_call_ends_the_span_with_an_error(otel, llm, monkeypatch):
    capture = otel(environment="dev")
    llm.use("anthropic")
    monkeypatch.setenv(provider.ROLE_ENV[ModelRole.FAST], CLAUDE_FAST)
    llm.claude((400, {"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}}))

    with pytest.raises(Exception):
        await generation.generate_text(QUESTION, ModelRole.FAST, max_tokens=10, policy=RetryPolicy(initial_s=0, jitter_s=0))

    span = _model_span(capture)
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["error.type"] == "BadRequestError"
