"""Feature 016: the catalog listing and the one model location (wcl_agent.llm.vertex)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import requests

from wcl_agent.llm import vertex
from wcl_agent.llm.vertex import CatalogEntry, CatalogUnavailable

ROOT = Path(__file__).resolve().parents[2]


class FakeResponse:
    def __init__(self, body=None, status: int = 200, bad_json: bool = False) -> None:
        self.body = body
        self.status = status
        self.bad_json = bad_json

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise requests.HTTPError(f"{self.status} error")

    def json(self):
        if self.bad_json:
            raise ValueError("not json")
        return self.body


class FakeSession:
    def __init__(self, *responses: FakeResponse | Exception) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def get(self, url, *, params, headers, timeout):
        self.calls.append({"url": url, "params": dict(params), "headers": headers, "timeout": timeout})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def session(monkeypatch):
    def install(*responses):
        fake = FakeSession(*responses)
        monkeypatch.setattr(vertex, "_session", lambda: fake)
        return fake

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-1")
    return install


def test_listing_follows_pages_and_parses_names(session):
    fake = session(
        FakeResponse(
            {
                "publisherModels": [
                    {"name": "publishers/anthropic/models/claude-haiku-4-5", "versionId": "20251001",
                     "launchStage": "GA"},
                ],
                "nextPageToken": "p2",
            }
        ),
        FakeResponse({"publisherModels": [{"name": "publishers/anthropic/models/claude-opus-5-5"}]}),
    )
    entries = vertex.list_publisher_models("anthropic")
    assert entries == [
        CatalogEntry("anthropic", "claude-haiku-4-5", "20251001", "GA"),
        CatalogEntry("anthropic", "claude-opus-5-5", None, None),
    ]
    assert [c["params"] for c in fake.calls] == [{"pageSize": 100}, {"pageSize": 100, "pageToken": "p2"}]
    assert all(c["headers"] == {"x-goog-user-project": "proj-1"} for c in fake.calls)
    assert all(c["timeout"] == 10 for c in fake.calls)
    assert fake.calls[0]["url"].endswith("/v1beta1/publishers/anthropic/models")


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse({}, status=403),
        requests.ConnectionError("unreachable"),
        FakeResponse(bad_json=True),
        FakeResponse({"publisherModels": [{"versionId": "default"}]}),  # no name
    ],
)
def test_listing_failures_raise_catalog_unavailable(session, response):
    session(response)
    with pytest.raises(CatalogUnavailable):
        vertex.list_publisher_models("google")


def test_auth_failure_raises_catalog_unavailable(monkeypatch):
    def no_credentials():
        raise RuntimeError("no ADC")

    monkeypatch.setattr(vertex, "_session", no_credentials)
    with pytest.raises(CatalogUnavailable):
        vertex.list_publisher_models("google")


def test_model_location_defaults_to_global(monkeypatch):
    monkeypatch.delenv("WCL_MODEL_LOCATION", raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "europe-west1")
    assert vertex.model_location() == "global"
    monkeypatch.setenv("WCL_MODEL_LOCATION", "eu")
    assert vertex.model_location() == "eu"


# --- US4: every model client runs at the model location ----------------------------------


@pytest.fixture
def regional(monkeypatch):
    """GOOGLE_CLOUD_LOCATION names a region that serves no current model."""
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "europe-west1")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-1")
    monkeypatch.delenv("WCL_MODEL_LOCATION", raising=False)


def _capture(monkeypatch, module, name):
    seen: dict = {}

    class Fake:
        def __init__(self, **kwargs) -> None:
            seen.update(kwargs)

    monkeypatch.setattr(module, name, Fake)
    return seen


def test_client_factories_use_the_model_location(regional, monkeypatch):
    import anthropic
    from google import genai

    g = _capture(monkeypatch, genai, "Client")
    a = _capture(monkeypatch, anthropic, "AnthropicVertex")
    aa = _capture(monkeypatch, anthropic, "AsyncAnthropicVertex")
    vertex.genai_client()
    vertex.anthropic_client(max_retries=0)
    vertex.async_anthropic_client(default_headers={"x": "y"})
    assert g == {"vertexai": True, "project": "proj-1", "location": "global"}
    assert a == {"project_id": "proj-1", "region": "global", "max_retries": 0}
    assert aa == {"project_id": "proj-1", "region": "global", "default_headers": {"x": "y"}}

    monkeypatch.setenv("WCL_MODEL_LOCATION", "eu")
    vertex.genai_client()
    assert g["location"] == "eu"


def test_adk_models_use_the_model_location(regional):
    from wcl_agent.agent import _build_web_search_tool
    from wcl_agent.llm.model_retry import RetryingClaude, RetryingGemini

    expected = {"vertexai": True, "location": "global"}
    gemini = RetryingGemini(model="gemini-3.8-flash")
    assert gemini.client_kwargs == expected
    assert gemini.api_client._api_client.location == "global"

    claude = RetryingClaude(model="claude-opus-5-5")._anthropic_client
    assert claude.region == "global" and claude.max_retries == 0

    search_model = _build_web_search_tool("gemini-3.8-flash").agent.model
    assert type(search_model).__name__ == "Gemini"  # plain, not a retrying one
    assert search_model.client_kwargs == expected


def test_api_key_setup_gets_plain_clients(monkeypatch):
    """QA BUG-001: GOOGLE_GENAI_USE_VERTEXAI=FALSE + GOOGLE_API_KEY still works."""
    from google import genai

    from wcl_agent.llm.model_retry import RetryingGemini

    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")
    g = _capture(monkeypatch, genai, "Client")
    vertex.genai_client()
    assert g == {}
    assert vertex.adk_client_kwargs() == {}
    assert not RetryingGemini(model="gemini-3.8-flash").client_kwargs


def test_no_model_client_is_built_outside_vertex():
    pattern = re.compile(r"genai\.Client\(|AnthropicVertex\(")
    offenders = [
        f"{path.relative_to(ROOT)}:{n}"
        for base in ("wcl_agent", "backend/app")
        for path in (ROOT / base).rglob("*.py")
        if path != ROOT / "wcl_agent" / "llm" / "vertex.py"
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if pattern.search(line)
    ]
    assert offenders == []
