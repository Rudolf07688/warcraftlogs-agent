"""Feature 033: model discovery on the Anthropic API, its busy-model fallback and the provider field.

Fakes only: the Models API is a scripted listing and every probe call is a stand-in.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from backend.app import main
from backend.app.config import Settings
from backend.app.model_state import fallback_model_for
from backend.tests.test_llm_provider_agent import scripted, use_provider  # noqa: F401 - fixtures
from backend.tests.test_model_discovery import FakeProbes, catalog_result
from wcl_agent.llm import models as models_mod
from wcl_agent.llm import provider
from wcl_agent.llm.model_retry import (
    ModelRateLimited,
    RetryPolicy,
    TurnStats,
    current_turn,
    generate_with_fallback,
)
from wcl_agent.llm.models import ClassSetting, class_label, model_class, sibling_model
from wcl_agent.llm.vertex import CatalogUnavailable

CLAUDE = [ClassSetting("anthropic", "haiku", 1), ClassSetting("anthropic", "sonnet", 2),
          ClassSetting("anthropic", "opus", 1)]
LISTING = [
    "claude-opus-5-5",
    "claude-opus-5-5-20260301",  # dated twin of an alias: the alias wins
    "claude-sonnet-5-5",
    "claude-sonnet-4-5-20250929",  # dated only
    "claude-haiku-4-5-20251001",
    "claude-3-opus-20240229",  # outside the naming: dropped from classes
    "claude-fable-5-1",
]


class FakeModelsApi:
    def __init__(self, ids: list[str] | Exception) -> None:
        self.ids = ids
        self.listed = 0

    def list(self, **kwargs):
        self.listed += 1
        if isinstance(self.ids, Exception):
            raise self.ids
        return iter(SimpleNamespace(id=i) for i in self.ids)


@pytest.fixture
def api(monkeypatch, use_provider):  # noqa: F811
    use_provider("anthropic", key="sk-test-key")
    monkeypatch.setattr(models_mod, "_QUOTA_RETRY_S", 0)
    monkeypatch.setattr(models_mod, "_make_anthropic_client", lambda: object())
    client = SimpleNamespace(models=FakeModelsApi(LISTING))
    monkeypatch.setattr(provider, "anthropic_client", lambda **kw: client)

    def install(plan=None, ids=None) -> FakeProbes:
        if ids is not None:
            client.models = FakeModelsApi(ids)
        probes = FakeProbes(plan)
        monkeypatch.setattr(models_mod, "_call_anthropic", probes.caller("anthropic"))
        probes.client = client  # type: ignore[attr-defined]
        return probes

    return install


def discover(**overrides):
    kwargs = dict(
        mode="catalog",
        gemini_ids=[],
        anthropic_ids=["claude-sonnet-5-5"],
        configured_default="claude-sonnet-5-5",
        fallback_models=["claude-sonnet-5-5"],
        gemini_classes=[],
        anthropic_classes=CLAUDE,
    )
    kwargs.update(overrides)
    return models_mod.discover_models(**kwargs)


# --- US1: catalog discovery --------------------------------------------------------------


def test_listing_is_classified_and_the_alias_wins(api):
    probes = api()
    result = discover()
    assert result.source == "catalog" and not result.degraded
    assert result.models == ["claude-haiku-4-5-20251001", "claude-sonnet-5-5", "claude-sonnet-4-5-20250929",
                             "claude-opus-5-5"]
    assert sorted(probes.calls) == sorted(result.models)  # one probe per kept candidate, no dated twin
    assert not any("gemini" in m or "fable" in m or "claude-3" in m for m in result.models)
    assert "claude-fable-5-1" in result.listed  # still known for the fixed-model check


def test_not_enabled_and_no_quota_probes(api):
    api({"claude-opus-5-5": [404], "claude-sonnet-5-5": [429], "claude-sonnet-4-5-20250929": [429]})
    result = discover()
    by_class = {c.cls: c for c in result.classes}
    assert by_class["opus"].reason == "not_enabled" and by_class["opus"].models == []
    assert by_class["sonnet"].reason == "no_quota"  # quota stops the whole class
    assert result.models == ["claude-haiku-4-5-20251001"]


def test_no_gemini_is_offered(api):
    api()
    result = discover(gemini_ids=["gemini-3.6-flash"])
    assert all(m.startswith("claude-") for m in result.models)


def test_static_mode_probes_the_api_form(api):
    probes = api()
    result = discover(mode="static", anthropic_ids=["claude-sonnet-5-5", "claude-haiku-4-5-20251001"])
    assert result.source == "static" and probes.client.models.listed == 0
    assert probes.calls == ["claude-sonnet-5-5", "claude-haiku-4-5-20251001"]


@pytest.mark.parametrize("ids", [anthropic.APIConnectionError(request=httpx.Request("GET", "https://x")),
                                 RuntimeError("boom"), []])
def test_listing_failure_or_empty_listing_falls_back_to_static(api, ids, caplog):
    api(ids=ids)
    with caplog.at_level(logging.WARNING, logger="wcl_agent.llm.models"):
        result = discover()
    assert result.source == "fallback" and not result.degraded
    assert result.models == ["claude-sonnet-5-5"]
    assert sum("model catalog unavailable" in r.getMessage() for r in caplog.records) == 1


def test_a_listing_error_never_carries_the_key(api):
    api(ids=RuntimeError("boom"))
    with pytest.raises(CatalogUnavailable) as err:
        models_mod._list_catalog()
    assert "sk-test-key" not in str(err.value)


# --- US2: id shapes and the sibling ------------------------------------------------------


def test_id_shapes_per_provider(use_provider):  # noqa: F811
    use_provider("anthropic", key="k")
    assert models_mod.is_catalog_id("claude-haiku-4-5-20251001")
    assert models_mod.is_catalog_id("claude-sonnet-5-5")
    assert not models_mod.is_catalog_id("claude-haiku-4-5@20251001")
    assert not models_mod.is_catalog_id("gemini-3.8-flash")
    use_provider("vertex")
    assert models_mod.is_catalog_id("claude-haiku-4-5@20251001")
    assert not models_mod.is_catalog_id("claude-haiku-4-5-20251001")


def test_dated_api_ids_have_a_class_and_a_sibling():
    served = ["claude-sonnet-5-5", "claude-sonnet-4-5-20250929", "claude-haiku-4-5-20251001"]
    assert model_class("claude-sonnet-4-5-20250929") == ("anthropic", "sonnet")
    assert class_label("claude-haiku-4-5-20251001") == "Claude haiku"
    assert sibling_model("claude-sonnet-5-5", served) == "claude-sonnet-4-5-20250929"
    assert sibling_model("claude-sonnet-4-5-20250929", served) == "claude-sonnet-5-5"
    assert sibling_model("claude-haiku-4-5-20251001", served) is None


def _status_error(status: int, retry_after: str | None) -> anthropic.APIStatusError:
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.test"), headers=headers)
    cls = anthropic.RateLimitError if status == 429 else anthropic.APIStatusError
    return cls("busy", response=response, body=None)


class _Request:
    def __init__(self, model: str) -> None:
        self.model, self.contents = model, []


async def _run(busy: set[str], status: int, retry_after: str | None, policy: RetryPolicy):
    seen: list[str] = []
    request = _Request("claude-sonnet-5-5")

    async def inner():
        seen.append(request.model)
        if request.model in busy:
            raise _status_error(status, retry_after)
        yield request.model

    stats = TurnStats(model="claude-sonnet-5-5", fallback_model="claude-sonnet-4-5-20250929")
    token = current_turn.set(stats)
    try:
        return [r async for r in generate_with_fallback(inner, request, policy)], seen, stats
    finally:
        current_turn.reset(token)


@pytest.fixture
def waits(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr("wcl_agent.llm.model_retry.asyncio.sleep", fake_sleep)
    return slept


@pytest.mark.parametrize("status", [429, 529])
async def test_busy_model_retries_with_the_hint_then_uses_the_sibling(status, waits):
    policy = RetryPolicy(attempts=2, budget_s=60.0)
    out, seen, stats = await _run({"claude-sonnet-5-5"}, status, "3", policy)
    assert out == ["claude-sonnet-4-5-20250929"]
    assert seen == ["claude-sonnet-5-5", "claude-sonnet-5-5", "claude-sonnet-4-5-20250929"]
    assert waits == [3.0] and stats.switched_to == "claude-sonnet-4-5-20250929"


async def test_a_hint_beyond_the_wait_budget_switches_at_once(waits):
    policy = RetryPolicy(attempts=5, budget_s=10.0)
    out, seen, _ = await _run({"claude-sonnet-5-5"}, 429, "120", policy)
    assert out == ["claude-sonnet-4-5-20250929"] and waits == []
    assert seen == ["claude-sonnet-5-5", "claude-sonnet-4-5-20250929"]


async def test_both_busy_raises_the_rate_limit_the_chat_shows_as_the_friendly_message(waits):
    policy = RetryPolicy(attempts=2, budget_s=60.0)
    with pytest.raises(ModelRateLimited):
        await _run({"claude-sonnet-5-5", "claude-sonnet-4-5-20250929"}, 529, "1", policy)


def test_fallback_model_for_api_ids(use_provider):  # noqa: F811
    use_provider("anthropic", key="k")
    app = SimpleNamespace(state=SimpleNamespace(models=["claude-sonnet-5-5", "claude-sonnet-4-5-20250929"]))
    assert fallback_model_for(app, "claude-sonnet-5-5") == "claude-sonnet-4-5-20250929"


# --- US3: the stored catalog is per provider ---------------------------------------------


@pytest.fixture
def boot(monkeypatch, fake_redis, use_provider):  # noqa: F811
    calls: list[dict] = []
    result = {"value": catalog_result()}

    def fake_discover(**kwargs):
        calls.append(kwargs)
        return result["value"]

    monkeypatch.setattr(main, "discover_models", fake_discover)
    monkeypatch.setattr(main, "project_id", lambda: "proj")
    monkeypatch.setattr(main, "model_location", lambda: "global")
    monkeypatch.setenv("WCL_MODEL_DISCOVERY", "catalog")

    async def run(provider_name: str, value=None):
        use_provider(provider_name, key="k" if provider_name == "anthropic" else None)
        if value is not None:
            result["value"] = value
        monkeypatch.setattr(main, "settings", Settings())
        return await main._load_models(SimpleNamespace(state=SimpleNamespace()))

    run.calls = calls  # type: ignore[attr-defined]
    return run


async def test_a_vertex_catalog_is_never_served_under_anthropic_or_the_reverse(boot):
    _, cached = await boot("vertex")
    assert cached is False
    _, cached = await boot("vertex")
    assert cached is True
    claude = catalog_result(models=["claude-sonnet-5-5"], default="claude-sonnet-5-5", classes=[],
                            listed=["claude-sonnet-5-5"])
    served, cached = await boot("anthropic", claude)
    assert cached is False and served.models == ["claude-sonnet-5-5"]
    assert all(not c["gemini_classes"] for c in boot.calls[1:])
    _, cached = await boot("anthropic")
    assert cached is True
    vertex_again, cached = await boot("vertex", catalog_result())
    assert cached is True and "gemini-3.8-flash" in vertex_again.models


async def test_cached_ids_in_the_other_providers_shape_are_rediscovered(boot, caplog):
    await boot("anthropic", catalog_result(models=["claude-haiku-4-5@20251001"], default="claude-haiku-4-5@20251001",
                                           classes=[]))
    with caplog.at_level(logging.WARNING, logger="backend.app.main"):
        await boot("anthropic", catalog_result(models=["claude-haiku-4-5-20251001"],
                                               default="claude-haiku-4-5-20251001", classes=[]))
    assert any("unexpected ids" in r.getMessage() for r in caplog.records)


# --- US4: the provider field -------------------------------------------------------------


@pytest.mark.parametrize("name", ["vertex", "anthropic"])
async def test_models_endpoint_names_the_provider_only(as_user, use_provider, name):  # noqa: F811
    use_provider(name, key="sk-test-key" if name == "anthropic" else None)
    body = (await as_user.client.get("/api/models")).json()
    assert body["provider"] == name
    assert "sk-test-key" not in str(body)


# --- US5: the startup summary line ---------------------------------------------------------


async def test_every_boot_logs_the_summary_line(boot, caplog):
    with caplog.at_level(logging.INFO, logger="backend.app.main"):
        await boot("vertex")
        await boot("vertex")
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("model discovery:")]
    assert lines == ["model discovery: 2 models from catalog (vertex)"] * 2
