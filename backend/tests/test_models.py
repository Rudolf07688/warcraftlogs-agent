"""US4 tests: startup model discovery/validation + the runtime model-state helper."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.model_state import get_model_state, is_valid_model
from wcl_agent import models as models_mod


def test_discover_keeps_responsive_and_excludes_bogus(monkeypatch):
    monkeypatch.setattr(models_mod, "_make_gemini_client", lambda: object())
    monkeypatch.setattr(
        models_mod, "_probe_gemini", lambda client, mid: mid == "gemini-good"
    )
    result = models_mod.discover_models(
        gemini_ids=["gemini-good", "gemini-bogus"],
        anthropic_ids=[],
        configured_default="gemini-good",
        fallback_models=["gemini-good"],
    )
    assert result == {"models": ["gemini-good"], "default": "gemini-good", "degraded": False}


def test_discover_default_falls_back_to_first_validated(monkeypatch):
    monkeypatch.setattr(models_mod, "_make_gemini_client", lambda: object())
    monkeypatch.setattr(models_mod, "_probe_gemini", lambda client, mid: True)
    result = models_mod.discover_models(
        gemini_ids=["gemini-a", "gemini-b"],
        anthropic_ids=[],
        configured_default="not-validated",
        fallback_models=["gemini-a"],
    )
    assert result["degraded"] is False
    assert result["default"] == "gemini-a"


def test_discover_degraded_when_infra_unavailable(monkeypatch):
    monkeypatch.setattr(models_mod, "_make_gemini_client", lambda: None)
    result = models_mod.discover_models(
        gemini_ids=["gemini-a"],
        anthropic_ids=[],
        configured_default="gemini-a",
        fallback_models=["gemini-a", "gemini-b"],
    )
    assert result["degraded"] is True
    assert result["models"] == ["gemini-a", "gemini-b"]  # never empty


def test_discover_degraded_when_nothing_validates(monkeypatch):
    monkeypatch.setattr(models_mod, "_make_gemini_client", lambda: object())
    monkeypatch.setattr(models_mod, "_probe_gemini", lambda client, mid: False)
    result = models_mod.discover_models(
        gemini_ids=["gemini-a"],
        anthropic_ids=[],
        configured_default="gemini-a",
        fallback_models=["gemini-a"],
    )
    assert result["degraded"] is True
    assert result["models"] == ["gemini-a"]


def test_model_state_uses_app_state_when_present():
    app = SimpleNamespace(
        state=SimpleNamespace(
            models=["m1", "m2"], default_model="m2", models_degraded=True
        )
    )
    models, default, degraded = get_model_state(app)
    assert models == ["m1", "m2"] and default == "m2" and degraded is True
    assert is_valid_model(app, "m1") and not is_valid_model(app, "nope")


def test_model_state_falls_back_to_config_before_startup():
    # No app.state model set -> falls back to configured allow-list, non-empty.
    app = SimpleNamespace(state=SimpleNamespace())
    models, default, _ = get_model_state(app)
    assert models and default in models
