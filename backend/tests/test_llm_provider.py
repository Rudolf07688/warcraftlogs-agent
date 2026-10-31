"""Feature 032: the provider layer (wcl_agent.llm.provider): switch, roles, id forms, clients."""

from __future__ import annotations

import logging

import pytest

from wcl_agent.llm import provider
from wcl_agent.llm.provider import ROLE_DEFAULTS, ROLE_ENV, LlmProviderNotConfigured, ModelRole

SENTINEL_KEY = "sk-ant-test-SENTINEL-0123456789"


@pytest.fixture
def use_provider(monkeypatch):
    """Switch the process's provider for one test (the value is cached per process)."""

    def install(value: str | None, *, key: str | None = None) -> None:
        if value is None:
            monkeypatch.delenv("WCL_LLM_PROVIDER", raising=False)
        else:
            monkeypatch.setenv("WCL_LLM_PROVIDER", value)
        if key is None:
            monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        else:
            monkeypatch.setenv("ANTHROPIC_API_KEY", key)
        provider.active_provider.cache_clear()

    for env in ROLE_ENV.values():
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setattr(provider, "_warned_roles", set())
    yield install
    provider.active_provider.cache_clear()


# --- the switch (AC 1) ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, "vertex"), ("", "vertex"), ("vertex", "vertex"), (" Anthropic ", "anthropic"), ("ANTHROPIC", "anthropic")],
)
def test_provider_values(use_provider, raw, expected):
    use_provider(raw)
    assert provider.active_provider() == expected


def test_unknown_provider_warns_once_and_uses_vertex(use_provider, caplog):
    use_provider("openai")
    with caplog.at_level(logging.WARNING, logger="wcl_agent.llm.provider"):
        assert provider.active_provider() == "vertex"
        assert provider.active_provider() == "vertex"
    warnings = [r for r in caplog.records if "WCL_LLM_PROVIDER" in r.getMessage()]
    assert len(warnings) == 1


# --- id forms (AC 5) ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("active", "model", "expected"),
    [
        ("anthropic", "claude-sonnet-4@20250514", "claude-sonnet-4-20250514"),
        ("anthropic", "claude-sonnet-4-20250514", "claude-sonnet-4-20250514"),
        ("anthropic", "claude-sonnet-5-5", "claude-sonnet-5-5"),
        ("vertex", "claude-sonnet-4-20250514", "claude-sonnet-4@20250514"),
        ("vertex", "claude-sonnet-4@20250514", "claude-sonnet-4@20250514"),
        ("vertex", "claude-opus-5-5", "claude-opus-5-5"),
        ("vertex", "gemini-3.6-flash", "gemini-3.6-flash"),
    ],
)
def test_to_provider_id(use_provider, active, model, expected):
    use_provider(active)
    assert provider.to_provider_id(model) == expected


def test_served_ids_filter_convert_and_dedupe(use_provider):
    ids = ["gemini-3.6-flash", "claude-sonnet-4@20250514", "claude-sonnet-4-20250514", " ", "claude-haiku-5-5"]
    use_provider("anthropic")
    assert provider.served_ids(ids) == ["claude-sonnet-4-20250514", "claude-haiku-5-5"]
    use_provider("vertex")
    assert provider.served_ids(ids) == ["gemini-3.6-flash", "claude-sonnet-4@20250514", "claude-haiku-5-5"]


def test_default_candidates(use_provider):
    use_provider("vertex")
    assert provider.default_candidates() == []
    use_provider("anthropic")
    assert provider.default_candidates() == ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"]


def test_model_catalog_on_both_providers(use_provider):
    use_provider("vertex")
    assert provider.has_model_catalog()
    use_provider("anthropic")
    assert provider.has_model_catalog()


# --- roles (AC 7) ---------------------------------------------------------------------------


@pytest.mark.parametrize("active", ["vertex", "anthropic"])
@pytest.mark.parametrize("role", list(ModelRole))
def test_unset_roles_use_the_provider_default(use_provider, active, role):
    use_provider(active)
    assert provider.role_model(role) == ROLE_DEFAULTS[active][role]


def test_anthropic_defaults_follow_d9(use_provider):
    use_provider("anthropic")
    assert {role: provider.role_model(role) for role in ModelRole} == {
        ModelRole.CHAT: "claude-sonnet-5-5",
        ModelRole.REPORT: "claude-sonnet-5-5",
        ModelRole.GUIDE: "claude-sonnet-5-5",
        ModelRole.GUIDE_REVIEW: "claude-opus-5-5",
        ModelRole.FAST: "claude-haiku-5-5",
        ModelRole.GREETING: "claude-haiku-5-5",
    }


def test_explicit_servable_value_wins(use_provider, monkeypatch):
    use_provider("anthropic")
    monkeypatch.setenv("WCL_REPORT_MODEL", "claude-opus-5-5")
    assert provider.role_model(ModelRole.REPORT) == "claude-opus-5-5"
    assert provider.role_model(ModelRole.GUIDE, explicit="claude-sonnet-4@20250514") == "claude-sonnet-4-20250514"
    use_provider("vertex")
    monkeypatch.setenv("WCL_REPORT_MODEL", "gemini-3.8-flash")
    assert provider.role_model(ModelRole.REPORT) == "gemini-3.8-flash"


def test_unservable_value_is_ignored_with_one_warning_per_role(use_provider, monkeypatch, caplog):
    use_provider("anthropic")
    monkeypatch.setenv("WCL_DEFAULT_MODEL", "gemini-3.6-flash")
    monkeypatch.setenv("WCL_GUIDE_MODEL", "gemini-3.7-flash")
    with caplog.at_level(logging.WARNING, logger="wcl_agent.llm.provider"):
        for _ in range(3):
            assert provider.role_model(ModelRole.CHAT) == "claude-sonnet-5-5"
            assert provider.role_model(ModelRole.GUIDE) == "claude-sonnet-5-5"
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 2
    assert "WCL_DEFAULT_MODEL=gemini-3.6-flash is not served by the anthropic provider" in messages[0]


def test_empty_explicit_value_counts_as_unset(use_provider):
    use_provider("anthropic")
    assert provider.role_model(ModelRole.FAST, explicit="  ") == "claude-haiku-5-5"


# --- credentials and clients (AC 3, 4) ------------------------------------------------------


def test_credentials_error(use_provider):
    use_provider("vertex")
    assert provider.credentials_error() is None
    use_provider("anthropic", key=SENTINEL_KEY)
    assert provider.credentials_error() is None
    use_provider("anthropic", key="  ")
    error = provider.credentials_error()
    assert error is not None and "ANTHROPIC_API_KEY" in error


def _capture(monkeypatch, name):
    import anthropic

    seen: dict = {}

    class Fake:
        def __init__(self, **kwargs) -> None:
            seen.update(kwargs)

    monkeypatch.setattr(anthropic, name, Fake)
    return seen


def test_anthropic_clients_use_the_api_key(use_provider, monkeypatch):
    use_provider("anthropic", key=SENTINEL_KEY)
    sync = _capture(monkeypatch, "Anthropic")
    aio = _capture(monkeypatch, "AsyncAnthropic")
    provider.anthropic_client(max_retries=0)
    provider.async_anthropic_client()
    assert sync == {"api_key": SENTINEL_KEY, "max_retries": 0}
    assert aio == {"api_key": SENTINEL_KEY}


def test_vertex_clients_use_project_and_location(use_provider, monkeypatch):
    use_provider("vertex")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-1")
    monkeypatch.delenv("WCL_MODEL_LOCATION", raising=False)
    sync = _capture(monkeypatch, "AnthropicVertex")
    aio = _capture(monkeypatch, "AsyncAnthropicVertex")
    provider.anthropic_client(max_retries=0)
    provider.async_anthropic_client()
    assert sync == {"project_id": "proj-1", "region": "global", "max_retries": 0}
    assert aio["project_id"] == "proj-1" and aio["region"] == "global"
    assert "default_headers" in aio  # ADK's tracking headers, as ADK's own Vertex client sends


@pytest.mark.parametrize("build", [provider.anthropic_client, provider.async_anthropic_client])
def test_missing_key_raises_a_key_free_error(use_provider, build):
    use_provider("anthropic")
    with pytest.raises(LlmProviderNotConfigured) as excinfo:
        build()
    assert "ANTHROPIC_API_KEY" in str(excinfo.value)


def test_real_clients_never_render_the_key(use_provider):
    use_provider("anthropic", key=SENTINEL_KEY)
    for client in (provider.anthropic_client(), provider.async_anthropic_client()):
        assert SENTINEL_KEY not in repr(client)
    assert SENTINEL_KEY not in repr(provider._api_key())
