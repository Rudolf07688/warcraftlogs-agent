"""Feature 016: model discovery from the Vertex Model Garden catalog.

The catalog fixtures are the live global listings recorded on 2026-10-18
(``fixtures/model_catalog_{google,anthropic}.json``). The global Anthropic listing no
longer carries the legacy ``claude-3-opus`` (only regional listings do), so the tests add
it by hand. No test touches the network: listings come from the fixtures and every probe
call is a fake.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from google.genai import errors as genai_errors

from backend.app import main
from backend.app.config import Settings
from backend.app.greeting import GREETING_MODEL
from backend.tests.test_wcl_cache import DeadRedis
from wcl_agent import cache, vertex
from wcl_agent import models as models_mod
from wcl_agent.cache import CacheFamily, FamilyConfig, family_ttl, keys
from wcl_agent.cache_models import ClassResult, ModelCatalog
from wcl_agent.models import (
    Candidate,
    ClassSetting,
    ProbeOutcome,
    candidates_by_class,
    check_model,
    choose_default,
    classes_signature,
    classify,
    missing_fixed_models,
    pick_per_class,
)
from wcl_agent.vertex import CatalogEntry, CatalogUnavailable

FIXTURES = Path(__file__).parent / "fixtures"
GEMINI = [ClassSetting("google", "pro", 2), ClassSetting("google", "flash", 2),
          ClassSetting("google", "flash-lite", 2)]
CLAUDE = [ClassSetting("anthropic", "haiku", 1), ClassSetting("anthropic", "sonnet", 1),
          ClassSetting("anthropic", "opus", 1)]
CLASSES = [*GEMINI, *CLAUDE]
LEGACY_OPUS = CatalogEntry("anthropic", "claude-3-opus", "default", "GA")

# Newest first, GA before preview on a tie: the per-class table in plan.md / the source doc.
EXPECTED_CANDIDATES = {
    ("google", "pro"): ["gemini-3.1-pro-preview", "gemini-2.5-pro"],
    ("google", "flash"): ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash",
                          "gemini-3.5-flash", "gemini-3-flash-preview", "gemini-2.5-flash"],
    ("google", "flash-lite"): ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite",
                               "gemini-2.5-flash-lite"],
    ("anthropic", "haiku"): ["claude-haiku-5-5", "claude-haiku-4-5@20251001"],
    ("anthropic", "sonnet"): ["claude-sonnet-5-5", "claude-sonnet-5", "claude-sonnet-4-6"],
    ("anthropic", "opus"): ["claude-opus-5-5", "claude-opus-5", "claude-opus-4-8",
                            "claude-opus-4-7", "claude-opus-4-6", "claude-opus-4-5@20251101"],
}
SERVED = ["gemini-3.1-pro-preview", "gemini-2.5-pro", "gemini-3.8-flash", "gemini-3.7-flash",
          "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "claude-haiku-5-5",
          "claude-sonnet-5-5", "claude-opus-5-5"]


def fixture_entries(publisher: str) -> list[CatalogEntry]:
    rows = json.loads((FIXTURES / f"model_catalog_{publisher}.json").read_text())["publisherModels"]
    return [
        CatalogEntry(publisher, r["name"].rsplit("/", 1)[-1], r.get("versionId"), r.get("launchStage"))
        for r in rows
    ]


CATALOG = {"google": fixture_entries("google"), "anthropic": [*fixture_entries("anthropic"), LEGACY_OPUS]}


def http_error(publisher: str, status: int) -> Exception:
    """A provider refusal shaped the way each SDK raises it."""
    if publisher == "google":
        return genai_errors.APIError(status, {"error": {"message": "refused", "status": str(status)}})
    response = httpx.Response(status, request=httpx.Request("POST", "https://vertex.test"))
    return anthropic.APIStatusError("refused", response=response, body=None)


class FakeProbes:
    """Stands in for ``_call_gemini`` / ``_call_anthropic``; ``plan`` maps id → errors in turn."""

    def __init__(self, plan: dict[str, list[int]] | None = None) -> None:
        self.plan = {k: list(v) for k, v in (plan or {}).items()}
        self.calls: list[str] = []

    def caller(self, publisher: str):
        def call(client, model_id):
            self.calls.append(model_id)
            statuses = self.plan.get(model_id)
            if statuses:
                status = statuses.pop(0) if len(statuses) > 1 else statuses[0]
                raise http_error(publisher, status)

        return call


@pytest.fixture(autouse=True)
def _vertex(monkeypatch):
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")


@pytest.fixture
def catalog(monkeypatch):
    """Fixture listings, clients that build, and probes that pass unless told otherwise."""
    monkeypatch.setattr(models_mod, "_make_gemini_client", lambda: object())
    monkeypatch.setattr(models_mod, "_make_anthropic_client", lambda: object())
    monkeypatch.setattr(models_mod, "_QUOTA_RETRY_S", 0)
    listed: list[str] = []

    def list_models(publisher):
        listed.append(publisher)
        return CATALOG[publisher]

    monkeypatch.setattr(vertex, "list_publisher_models", list_models)

    def install(plan: dict[str, list[int]] | None = None) -> FakeProbes:
        probes = FakeProbes(plan)
        monkeypatch.setattr(models_mod, "_call_gemini", probes.caller("google"))
        monkeypatch.setattr(models_mod, "_call_anthropic", probes.caller("anthropic"))
        probes.listed = listed  # type: ignore[attr-defined]
        return probes

    return install


def discover(**overrides) -> ModelCatalog:
    kwargs = dict(
        mode="catalog",
        gemini_ids=["gemini-static"],
        anthropic_ids=[],
        configured_default="not-served",
        fallback_models=["gemini-fallback"],
        gemini_classes=GEMINI,
        anthropic_classes=CLAUDE,
    )
    kwargs.update(overrides)
    return models_mod.discover_models(**kwargs)


# --- US1: classification -------------------------------------------------------------------


def test_candidates_per_class_match_the_plan():
    found = candidates_by_class([*CATALOG["google"], *CATALOG["anthropic"]], CLASSES)
    assert {k: [c.model_id for c in v] for k, v in found.items()} == EXPECTED_CANDIDATES


def test_non_chat_experimental_and_legacy_models_are_dropped():
    found = candidates_by_class([*CATALOG["google"], *CATALOG["anthropic"]], CLASSES)
    ids = {c.model_id for cands in found.values() for c in cands}
    for dropped in ("gemini-2.5-pro-exp-03-25", "gemini-2.5-pro-tts", "gemini-3.1-flash-image",
                    "gemini-live-2.5-flash-native-audio", "gemini-embedding-2", "gemini-4-argon",
                    "gemini-omni-1.1-flash-preview", "gemini-2.5-flash-preview-04-17",
                    "gemini-1.5-pro-002", "gemini-3.5-transcribe", "claude-fable-5-1",
                    "claude-3-opus"):
        assert dropped not in ids
    # flash-lite is never read as flash
    assert all("lite" not in c.model_id for c in found[("google", "flash")])


def test_experimental_stage_is_dropped_and_missing_stage_kept():
    exp = CatalogEntry("google", "gemini-9.9-flash", "default", "EXPERIMENTAL")
    unknown = CatalogEntry("google", "gemini-9.9-flash", "default", None)
    assert classify(exp, GEMINI) is None
    assert classify(unknown, GEMINI) == Candidate("google", "flash", (9, 9), False, "gemini-9.9-flash")


def test_versions_compare_numerically_and_ga_beats_preview():
    entries = [
        CatalogEntry("google", "gemini-3.9-pro", "default", "GA"),
        CatalogEntry("google", "gemini-3-pro", "default", "GA"),
        CatalogEntry("google", "gemini-3.10-pro-preview", "default", "PUBLIC_PREVIEW"),
        CatalogEntry("google", "gemini-3.1-pro", "default", "GA"),
        CatalogEntry("google", "gemini-3.10-pro", "default", "GA"),
    ]
    found = candidates_by_class(entries, GEMINI)[("google", "pro")]
    assert [c.model_id for c in found] == [
        "gemini-3.10-pro", "gemini-3.10-pro-preview", "gemini-3.9-pro", "gemini-3.1-pro", "gemini-3-pro",
    ]


def test_claude_callable_ids_follow_the_version_id():
    assert classify(CatalogEntry("anthropic", "claude-opus-5-5", "default", "GA"), CLAUDE).model_id == (
        "claude-opus-5-5"
    )
    assert classify(CatalogEntry("anthropic", "claude-haiku-4-5", "20251001", "GA"), CLAUDE).model_id == (
        "claude-haiku-4-5@20251001"
    )


def test_unconfigured_classes_are_ignored():
    entry = CatalogEntry("anthropic", "claude-opus-5-5", "default", "GA")
    assert classify(entry, [ClassSetting("anthropic", "haiku", 1)]) is None


# --- US1: selection ------------------------------------------------------------------------


def _cands(*ids: str) -> list[Candidate]:
    return [Candidate("anthropic", "haiku", (9 - i, 0), False, mid) for i, mid in enumerate(ids)]


def test_pick_keeps_the_newest_that_pass():
    setting = ClassSetting("google", "flash", 2)
    cands = [Candidate("google", "flash", (3, 9 - i), False, f"m{i}") for i in range(4)]
    result = pick_per_class(setting, cands, dict.fromkeys(["m0", "m1", "m2", "m3"], ProbeOutcome.PASSED))
    assert result == ClassResult(publisher="google", cls="flash", models=["m0", "m1"], reason=None)


def test_choose_default():
    classes = [ClassResult(publisher="google", cls="pro", models=["p"]),
               ClassResult(publisher="google", cls="flash", models=["f1", "f2"])]
    assert choose_default(["p", "f1", "f2"], "f2", classes) == "f2"
    assert choose_default(["p", "f1", "f2"], "gone", classes) == "f1"
    assert choose_default(["p"], "gone", classes[:1]) == "p"


def test_catalog_path_serves_the_newest_per_class_in_class_order(catalog, caplog):
    probes = catalog()
    with caplog.at_level(logging.INFO, logger="wcl_agent.models"):
        result = discover()
    assert result.models == SERVED
    assert result.source == "catalog" and result.degraded is False
    assert result.default == "gemini-3.8-flash"
    assert sorted(probes.listed) == ["anthropic", "google"]
    # only the newest keep + 2 per class are probed
    expected_probes = [mid for (pub, cls), ids in EXPECTED_CANDIDATES.items()
                       for mid in ids[: next(s.keep for s in CLASSES if (s.publisher, s.name) == (pub, cls)) + 2]]
    assert sorted(probes.calls) == sorted(expected_probes)
    assert len(probes.calls) == 17
    # every callable catalog id is listed, bare and dated
    for mid in ("gemini-4-argon", "claude-haiku-4-5", "claude-haiku-4-5@20251001", "claude-3-opus"):
        assert mid in result.listed
    lines = [r.getMessage() for r in caplog.records]
    assert "gemini pro: gemini-3.1-pro-preview, gemini-2.5-pro" in lines
    assert "gemini flash: gemini-3.8-flash, gemini-3.7-flash" in lines
    assert "claude opus: claude-opus-5-5" in lines


def test_configured_default_wins_when_served(catalog):
    catalog()
    assert discover(configured_default="gemini-2.5-pro").default == "gemini-2.5-pro"


# --- US2: probe outcomes -------------------------------------------------------------------


@pytest.fixture
def sleeps(monkeypatch):
    waited: list[float] = []
    monkeypatch.setattr(models_mod.time, "sleep", waited.append)
    return waited


def _call(*errors: BaseException | None):
    pending = list(errors)

    def call():
        error = pending.pop(0) if pending else None
        if error is not None:
            raise error

    return call


@pytest.mark.parametrize("publisher", ["google", "anthropic"])
@pytest.mark.parametrize("status", [404, 403])
def test_not_found_means_not_enabled(publisher, status, sleeps):
    assert check_model(_call(http_error(publisher, status))) is ProbeOutcome.NOT_ENABLED
    assert sleeps == []


@pytest.mark.parametrize("publisher", ["google", "anthropic"])
def test_persistent_429_means_no_quota_after_one_retry(publisher, sleeps):
    err = http_error(publisher, 429)
    assert check_model(_call(err, err)) is ProbeOutcome.NO_QUOTA
    assert sleeps == [2]


def test_429_then_success_passes(sleeps):
    assert check_model(_call(http_error("google", 429), None)) is ProbeOutcome.PASSED
    assert sleeps == [2]


@pytest.mark.parametrize(
    "error",
    [http_error("google", 400), http_error("google", 503), http_error("anthropic", 529),
     TimeoutError("slow"), RuntimeError("boom")],
)
def test_other_errors_fail(error, sleeps):
    assert check_model(_call(error)) is ProbeOutcome.FAILED
    assert sleeps == []


def test_success_passes(sleeps):
    assert check_model(_call(None)) is ProbeOutcome.PASSED


def test_probes_carry_a_tool_declaration():
    seen: list[dict] = []
    gemini = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: seen.append(kw)))
    claude = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: seen.append(kw)))

    models_mod._call_gemini(gemini, "gemini-x")
    config = seen[0]["config"]
    assert [d.name for d in config.tools[0].function_declarations] == ["ping"]
    assert config.max_output_tokens == 1 and config.http_options.timeout == 10_000

    models_mod._call_anthropic(claude, "claude-x")
    assert [t["name"] for t in seen[1]["tools"]] == ["ping"]
    assert seen[1]["max_tokens"] == 1 and seen[1]["timeout"] == 10

    assert models_mod._probe_gemini(gemini, "gemini-x") is True
    broken = SimpleNamespace(messages=SimpleNamespace(create=_raise))
    assert models_mod._probe_anthropic(broken, "claude-x") is False


def _raise(**kwargs):
    raise RuntimeError("refused")


def test_walk_skips_not_enabled_and_stops_at_no_quota():
    haiku = ClassSetting("anthropic", "haiku", 1)
    result = pick_per_class(haiku, _cands("h55", "h45"), {"h55": ProbeOutcome.NOT_ENABLED,
                                                          "h45": ProbeOutcome.PASSED})
    assert result.models == ["h45"] and result.reason is None

    two = ClassSetting("anthropic", "haiku", 2)
    outcomes = {"a": ProbeOutcome.PASSED, "b": ProbeOutcome.NO_QUOTA, "c": ProbeOutcome.PASSED}
    result = pick_per_class(two, _cands("a", "b", "c"), outcomes)
    assert result.models == ["a"] and result.reason == "no_quota"  # c is ignored

    result = pick_per_class(haiku, _cands("a", "b"), dict.fromkeys("ab", ProbeOutcome.NOT_ENABLED))
    assert result.models == [] and result.reason == "not_enabled"
    assert pick_per_class(haiku, [], {}).reason == "no_candidates"


def test_haiku_falls_back_and_sonnet_has_no_quota(catalog, caplog):
    catalog({"claude-haiku-5-5": [404], **{m: [429] for m in EXPECTED_CANDIDATES[("anthropic", "sonnet")]}})
    with caplog.at_level(logging.INFO, logger="wcl_agent.models"):
        result = discover()
    assert "claude-haiku-4-5@20251001" in result.models
    assert not any("sonnet" in m for m in result.models)
    lines = [r.getMessage() for r in caplog.records]
    assert "claude sonnet: no quota (429)" in lines
    assert "claude haiku: claude-haiku-4-5@20251001" in lines


# --- US3: never empty ----------------------------------------------------------------------


@pytest.mark.parametrize("failing", ["google", "anthropic"])
def test_listing_failure_probes_the_static_lists(monkeypatch, caplog, failing):
    def list_models(publisher):
        if publisher == failing:
            raise CatalogUnavailable("403 forbidden")
        return CATALOG[publisher]

    monkeypatch.setattr(vertex, "list_publisher_models", list_models)
    monkeypatch.setattr(models_mod, "_make_gemini_client", lambda: object())
    monkeypatch.setattr(models_mod, "_probe_gemini", lambda client, mid: True)
    with caplog.at_level(logging.WARNING, logger="wcl_agent.models"):
        result = discover(gemini_ids=["gemini-a", "gemini-b"], configured_default="gemini-b")
    assert result.source == "fallback" and result.degraded is False
    assert result.models == ["gemini-a", "gemini-b"] and result.default == "gemini-b"
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "model catalog unavailable" in warnings[0]


def test_listing_failure_and_nothing_static_passes_is_degraded(monkeypatch):
    def unavailable(publisher):
        raise CatalogUnavailable("timeout")

    monkeypatch.setattr(vertex, "list_publisher_models", unavailable)
    monkeypatch.setattr(models_mod, "_make_gemini_client", lambda: object())
    monkeypatch.setattr(models_mod, "_probe_gemini", lambda client, mid: False)
    result = discover(fallback_models=["gemini-a", "gemini-b"], configured_default="gemini-b")
    assert result.source == "degraded" and result.degraded is True
    assert result.models == ["gemini-a", "gemini-b"] and result.default == "gemini-b"


def test_catalog_with_nothing_passing_is_degraded(catalog):
    every = [m for ids in EXPECTED_CANDIDATES.values() for m in ids]
    catalog(dict.fromkeys(every, [500]))
    result = discover()
    assert result.degraded is True and result.models == ["gemini-fallback"]
    assert result.listed  # the listing worked: fixed-model warnings still have their data


def test_static_mode_never_lists_the_catalog(monkeypatch):
    monkeypatch.setattr(vertex, "list_publisher_models", lambda p: pytest.fail("listed"))
    monkeypatch.setattr(models_mod, "_make_gemini_client", lambda: object())
    monkeypatch.setattr(models_mod, "_probe_gemini", lambda client, mid: True)
    result = discover(mode="static")
    assert result.source == "static" and result.models == ["gemini-static"]


def test_catalog_mode_without_vertex_probes_the_static_lists(monkeypatch):
    """QA BUG-001: the API-key setup has no Model Garden to list."""
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")
    monkeypatch.setattr(vertex, "list_publisher_models", lambda p: pytest.fail("listed"))
    monkeypatch.setattr(models_mod, "_make_gemini_client", lambda: object())
    monkeypatch.setattr(models_mod, "_probe_gemini", lambda client, mid: True)
    result = discover()
    assert result.source == "static" and result.models == ["gemini-static"]


def test_discovery_settings_are_validated(caplog):
    with caplog.at_level(logging.WARNING):
        assert Settings(wcl_model_discovery="bogus").model_discovery_mode == "catalog"
        assert Settings(wcl_model_discovery="Static").model_discovery_mode == "static"
        gemini = Settings(wcl_gemini_classes="pro:2,ultra:1,flash:0,flash-lite:x").gemini_classes
    assert gemini == [ClassSetting("google", "pro", 2)]
    assert sum("ignoring model class setting" in r.getMessage() for r in caplog.records) == 3
    assert sum("WCL_MODEL_DISCOVERY" in r.getMessage() for r in caplog.records) == 1
    assert Settings(wcl_anthropic_classes="").anthropic_classes == []
    assert Settings().gemini_classes == GEMINI and Settings().anthropic_classes == CLAUDE


# --- US5: the shared cache -----------------------------------------------------------------


def test_model_catalog_family(monkeypatch):
    assert cache.FAMILIES[CacheFamily.MODEL_CATALOG] == FamilyConfig(21600, 0.50)
    assert family_ttl(CacheFamily.MODEL_CATALOG) == 21600
    monkeypatch.setenv("WCL_CACHE_TTL_MODEL_CATALOG", "60")
    assert family_ttl(CacheFamily.MODEL_CATALOG) == 60
    assert keys.model_catalog("proj", "global", "sig") == "ext:models:v1:proj:global:sig"


def test_classes_signature_tracks_every_setting(monkeypatch):
    base = classes_signature(GEMINI, CLAUDE)
    assert base == "g=pro2.flash2.flash-lite2;a=haiku1.sonnet1.opus1;s=GA.PUBLIC_PREVIEW"
    assert classes_signature(list(GEMINI), list(CLAUDE)) == base
    assert classes_signature(GEMINI[:2], CLAUDE) != base
    assert classes_signature([ClassSetting("google", "pro", 3), *GEMINI[1:]], CLAUDE) != base
    assert classes_signature(GEMINI, []) != base
    monkeypatch.setattr(models_mod, "ALLOWED_STAGES", frozenset({"GA"}))
    assert classes_signature(GEMINI, CLAUDE) != base


def test_transient_gaps_are_flagged():
    """QA BUG-005: only errors a later boot may not see again shorten the cache life."""
    setting = ClassSetting("google", "pro", 2)
    outcomes = {"a": ProbeOutcome.FAILED, "b": ProbeOutcome.PASSED, "c": ProbeOutcome.PASSED}
    demoted = pick_per_class(setting, _cands("a", "b", "c"), outcomes)
    assert demoted.models == ["b", "c"] and demoted.failed == ["a"]
    assert models_mod.has_transient_gaps([demoted])
    gemini_429 = ClassResult(publisher="google", cls="flash", reason="no_quota")
    claude_429 = ClassResult(publisher="anthropic", cls="sonnet", reason="no_quota")
    not_enabled = ClassResult(publisher="anthropic", cls="haiku", models=["h"], reason=None)
    assert models_mod.has_transient_gaps([gemini_429])
    assert not models_mod.has_transient_gaps([claude_429, not_enabled])


def test_catalog_id_shapes():
    """QA SEC-002: a cached value must look like something discovery serves."""
    for ok in ("gemini-3.8-flash", "gemini-3.1-pro-preview", "claude-opus-5-5", "claude-haiku-4-5@20251001"):
        assert models_mod.is_catalog_id(ok)
    for bad in ("projects/x/locations/global/endpoints/1", "gemini-3.8-flash@x", "claude-opus-5-5@evil",
                "gpt-5", ""):
        assert not models_mod.is_catalog_id(bad)


def catalog_result(source: str = "catalog", **overrides) -> ModelCatalog:
    fields = dict(
        models=["gemini-3.8-flash", "gemini-3.7-flash"],
        default="gemini-3.8-flash",
        degraded=source == "degraded",
        source=source,
        classes=[ClassResult(publisher="google", cls="flash", models=["gemini-3.8-flash", "gemini-3.7-flash"])],
        listed=["gemini-3.8-flash", "gemini-3.7-flash"],
        fetched_at=datetime.now(UTC),
    )
    fields.update(overrides)
    return ModelCatalog(**fields)


@pytest.fixture
def boot(monkeypatch):
    """``main._load_models`` with a counting fake discovery; returns a runner."""
    calls: list[dict] = []
    result = {"value": catalog_result()}

    def fake_discover(**kwargs):
        calls.append(kwargs)
        return result["value"]

    monkeypatch.setattr(main, "discover_models", fake_discover)
    monkeypatch.setattr(main, "project_id", lambda: "proj")
    monkeypatch.setattr(main.settings, "wcl_model_discovery", "catalog")
    monkeypatch.delenv("WCL_MODEL_LOCATION", raising=False)

    async def run():
        app = SimpleNamespace(state=SimpleNamespace())
        catalog, cached = await main._load_models(app)
        assert app.state.models == catalog.models and app.state.default_model == catalog.default
        return catalog, cached

    run.calls = calls  # type: ignore[attr-defined]
    run.result = result  # type: ignore[attr-defined]
    return run


async def test_boot_miss_stores_and_hit_skips_discovery(boot, fake_redis):
    first, cached = await boot()
    assert cached is False and len(boot.calls) == 1
    assert boot.calls[0]["mode"] == "catalog" and boot.calls[0]["gemini_classes"]
    key = keys.model_catalog("proj", "global", classes_signature(main.settings.gemini_classes,
                                                                  main.settings.anthropic_classes))
    assert 21600 <= await fake_redis.ttl(key) <= 21600 * 1.1
    second, cached = await boot()
    assert cached is True and len(boot.calls) == 1 and second == first
    detail = f"{len(second.models)} models ({second.source}" + (", cached)" if cached else ")")
    assert detail == "2 models (catalog, cached)"


async def test_boot_changed_classes_miss_the_cache(boot, fake_redis, monkeypatch):
    await boot()
    monkeypatch.setattr(main.settings, "wcl_gemini_classes", "pro:1")
    await boot()
    assert len(boot.calls) == 2


@pytest.mark.parametrize("source", ["fallback", "degraded"])
async def test_boot_never_stores_fallback_or_degraded(boot, fake_redis, source):
    boot.result["value"] = catalog_result(source, classes=[], listed=[])
    await boot()
    await boot()
    assert len(boot.calls) == 2
    assert await fake_redis.keys("ext:models:*") == []


async def test_boot_ttl_zero_stores_nothing(boot, fake_redis, monkeypatch):
    monkeypatch.setenv("WCL_CACHE_TTL_MODEL_CATALOG", "0")
    await boot()
    await boot()
    assert len(boot.calls) == 2


async def test_boot_unsettled_result_is_kept_briefly(boot, fake_redis):
    """QA BUG-005: one transient probe failure is not pinned for 6 h."""
    boot.result["value"] = catalog_result(
        classes=[ClassResult(publisher="google", cls="flash", models=["gemini-3.7-flash"],
                             failed=["gemini-3.8-flash"])],
        models=["gemini-3.7-flash"], default="gemini-3.7-flash",
    )
    await boot()
    (key,) = await fake_redis.keys("ext:models:*")
    assert 0 < await fake_redis.ttl(key) <= 600 * 1.1  # family jitter


async def test_boot_default_follows_the_current_setting(boot, fake_redis, monkeypatch):
    """QA BUG-004: a cached value doesn't pin the default of the boot that stored it."""
    monkeypatch.setattr(main.settings, "wcl_default_model", "gone")
    first, _ = await boot()
    assert first.default == "gemini-3.8-flash"
    monkeypatch.setattr(main.settings, "wcl_default_model", "gemini-3.7-flash")
    second, cached = await boot()
    assert cached is True and second.default == "gemini-3.7-flash"


async def test_boot_rediscovers_a_tampered_cache_entry(boot, fake_redis, caplog):
    """QA SEC-002: ids outside discovery's shape are never served from the cache."""
    key = keys.model_catalog("proj", "global", classes_signature(main.settings.gemini_classes,
                                                                  main.settings.anthropic_classes))
    evil = "projects/attacker/locations/global/endpoints/1"
    await fake_redis.set(key, catalog_result(models=[evil], default=evil, classes=[]).model_dump_json())
    with caplog.at_level(logging.WARNING):
        catalog, cached = await boot()
    assert evil not in catalog.models and cached is False and len(boot.calls) == 1
    assert any("unexpected ids" in r.getMessage() for r in caplog.records)


async def test_boot_survives_a_malformed_redis_url(boot, monkeypatch):
    """QA BUG-003: a REDIS_URL without a scheme fails open instead of failing the boot."""
    monkeypatch.setenv("REDIS_URL", "localhost:6379")
    catalog, cached = await boot()
    assert catalog.models and cached is False and len(boot.calls) == 1


async def test_boot_survives_redis_down(boot, monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://nowhere:6379/0")
    monkeypatch.setattr(cache, "_make_redis", lambda url: DeadRedis())
    catalog, cached = await boot()
    assert catalog.models and cached is False and len(boot.calls) == 1


async def test_boot_static_mode_bypasses_the_cache(boot, monkeypatch):
    monkeypatch.setattr(main.settings, "wcl_model_discovery", "static")

    async def no_cache(*args, **kwargs):
        pytest.fail("static mode used the cache")

    monkeypatch.setattr(main, "get_or_load", no_cache)
    boot.result["value"] = catalog_result("static", classes=[], listed=[])
    catalog, cached = await boot()
    assert boot.calls[0]["mode"] == "static" and cached is False


# --- US6: what was picked and why ----------------------------------------------------------


def test_missing_fixed_models():
    listed = ["gemini-3.8-flash", "claude-haiku-4-5", "claude-haiku-4-5@20251001", "claude-opus-5-5"]
    fixed = {"A": "gemini-3.8-flash", "B": "gemini-1.0-retired", "C": "claude-haiku-4-5@20251001",
             "D": "claude-opus-5-5@20990101", "E": ""}
    assert missing_fixed_models(fixed, listed) == [("B", "gemini-1.0-retired")]
    assert missing_fixed_models({"C": "claude-haiku-4-5"}, ["claude-haiku-4-5@20251001"]) == []
    assert missing_fixed_models(fixed, []) == []


async def test_boot_logs_picks_and_retired_fixed_models_on_hit_and_miss(boot, fake_redis, monkeypatch, caplog):
    monkeypatch.setattr(main.settings, "wcl_report_model", "gemini-1.0-retired")
    fixed_ok = [main.settings.wcl_guide_model, main.settings.wcl_guide_review_model, GREETING_MODEL]
    boot.result["value"] = catalog_result(listed=["gemini-3.8-flash", "gemini-3.7-flash", *fixed_ok])
    for expect_cached in (False, True):
        caplog.clear()
        with caplog.at_level(logging.INFO):
            _, cached = await boot()
        assert cached is expect_cached
        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings == ["WCL_REPORT_MODEL=gemini-1.0-retired is not in the model catalog; it may be retired"]
        if cached:  # the miss logged its lines inside discover_models (faked here)
            assert "gemini flash: gemini-3.8-flash, gemini-3.7-flash" in [r.getMessage() for r in caplog.records]
