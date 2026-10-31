"""Feature 032 at the app level: settings per provider, startup without a key, the key never
leaking, and chats on a model the active provider doesn't serve (sc-249 AC 1, 4, 6, 7).

Fakes only: the Anthropic API is a scripted mock transport (see test_llm_provider_agent.py).
"""

from __future__ import annotations

import json
import logging
import uuid
from types import SimpleNamespace

import pytest
from fastapi import WebSocketDisconnect

from backend.app import main
from backend.app.api import greeting as greeting_api
from backend.app.api import ws as ws_mod
from backend.app.config import Settings
from backend.app.schemas import ChatTurn
from backend.app.tenancy.context import RequestIdentity
from backend.tests.test_llm_provider_agent import (  # noqa: F401 - fixtures
    ScriptedApi,
    scripted,
    use_provider,
)
from wcl_agent.llm import provider
from wcl_agent.llm.provider import ROLE_ENV

SENTINEL_KEY = "sk-ant-test-SENTINEL-app-77"
CLAUDE_DEFAULTS = ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"]

# The owner's .env before the switch, as .env.example suggests it.
OWNER_ENV = {
    "WCL_DEFAULT_MODEL": "gemini-3.8-flash",
    "WCL_GUIDE_MODEL": "gemini-3.6-flash",
    "WCL_REPORT_MODEL": "gemini-3.6-flash",
    "WCL_GEMINI_MODELS": "gemini-3.6-flash,gemini-3.1-pro-preview",
    "WCL_ANTHROPIC_MODELS": "claude-sonnet-4@20250514",
    "WCL_MODELS": "gemini-3.6-flash,gemini-3.1-pro-preview",
    "WCL_MODEL_DISCOVERY": "catalog",
}
MODEL_ENV = (*ROLE_ENV.values(), "WCL_GEMINI_MODELS", "WCL_ANTHROPIC_MODELS", "WCL_MODELS", "WCL_MODEL_DISCOVERY")


@pytest.fixture
def env(monkeypatch, use_provider):  # noqa: F811 - the imported fixture
    """A clean model environment; returns a setter for the owner-style values."""
    for name in MODEL_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(provider, "_warned_roles", set())

    def set_env(values: dict[str, str]) -> None:
        for name, value in values.items():
            monkeypatch.setenv(name, value)

    return set_env


def _settings_view(s: Settings) -> dict:
    return {
        "roles": [
            s.wcl_default_model,
            s.wcl_report_model,
            s.wcl_guide_model,
            s.wcl_guide_review_model,
            s.wcl_suggest_model,
            s.wcl_greeting_model,
        ],
        "default_model": s.default_model,
        "model_list": s.model_list,
        "gemini_models": s.gemini_models,
        "anthropic_models": s.anthropic_models,
        "candidate_models": s.candidate_models,
        "model_discovery_mode": s.model_discovery_mode,
    }


# --- vertex is unchanged (scrum-master condition) ----------------------------------------------


@pytest.mark.parametrize("value", [None, "vertex"])
def test_vertex_settings_equal_the_pre_032_values(env, monkeypatch, use_provider, value):  # noqa: F811
    use_provider("vertex")
    if value is None:
        monkeypatch.delenv("WCL_LLM_PROVIDER")
        provider.active_provider.cache_clear()
    assert _settings_view(Settings()) == {
        "roles": [
            "gemini-3.6-flash",
            "gemini-3.6-flash",
            "gemini-3.7-flash",
            "gemini-3.1-pro-preview",
            "gemini-3.6-flash",  # suggestions.py's WCL_SUGGEST_MODEL default
            "gemini-3.5-flash-lite",  # greeting.py's former constant
        ],
        "default_model": "gemini-3.6-flash",
        "model_list": ["gemini-3.6-flash", "gemini-3.1-pro-preview"],
        "gemini_models": ["gemini-3.6-flash", "gemini-3.1-pro-preview"],
        "anthropic_models": [],
        "candidate_models": ["gemini-3.6-flash", "gemini-3.1-pro-preview"],
        "model_discovery_mode": "catalog",
    }
    env(OWNER_ENV)
    assert _settings_view(Settings()) == {
        "roles": [
            "gemini-3.8-flash",
            "gemini-3.6-flash",
            "gemini-3.6-flash",
            "gemini-3.1-pro-preview",
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite",
        ],
        "default_model": "gemini-3.8-flash",
        "model_list": ["gemini-3.6-flash", "gemini-3.1-pro-preview"],
        "gemini_models": ["gemini-3.6-flash", "gemini-3.1-pro-preview"],
        "anthropic_models": ["claude-sonnet-4@20250514"],
        "candidate_models": ["gemini-3.6-flash", "gemini-3.1-pro-preview", "claude-sonnet-4@20250514"],
        "model_discovery_mode": "catalog",
    }


# --- one .env line switches everything (AC 1, 5, 7) -------------------------------------------


def test_anthropic_settings_with_the_owners_vertex_env(env, use_provider, caplog):  # noqa: F811
    use_provider("anthropic", key=SENTINEL_KEY)
    env(OWNER_ENV)
    with caplog.at_level(logging.WARNING, logger="wcl_agent.llm.provider"):
        view = _settings_view(Settings())
    assert view == {
        "roles": [
            "claude-sonnet-5-5",
            "claude-sonnet-5-5",
            "claude-sonnet-5-5",
            "claude-opus-5-5",
            "claude-haiku-5-5",
            "claude-haiku-5-5",
        ],
        "default_model": "claude-sonnet-5-5",
        "model_list": CLAUDE_DEFAULTS,
        "gemini_models": [],
        "anthropic_models": ["claude-sonnet-4-20250514"],
        "candidate_models": ["claude-sonnet-4-20250514"],
        "model_discovery_mode": "static",
    }
    warned = sorted(r.getMessage().split("=")[0] for r in caplog.records)
    assert warned == ["WCL_DEFAULT_MODEL", "WCL_GUIDE_MODEL", "WCL_REPORT_MODEL"]


def test_explicit_claude_role_wins_under_anthropic(env, use_provider):  # noqa: F811
    use_provider("anthropic", key=SENTINEL_KEY)
    env({"WCL_GUIDE_REVIEW_MODEL": "claude-fable-5-1", "WCL_GREETING_MODEL": "claude-sonnet-5-5"})
    s = Settings()
    assert s.wcl_guide_review_model == "claude-fable-5-1"
    assert s.wcl_greeting_model == "claude-sonnet-5-5"


class _FakeProbeClient:
    def __init__(self) -> None:
        self.probed: list[str] = []
        self.messages = self

    def create(self, **kwargs):
        self.probed.append(kwargs["model"])
        return SimpleNamespace()


async def test_startup_discovery_probes_claude_through_the_provider(env, use_provider, monkeypatch):  # noqa: F811
    use_provider("anthropic", key=SENTINEL_KEY)
    env(OWNER_ENV)
    client = _FakeProbeClient()
    monkeypatch.setattr(provider, "anthropic_client", lambda **kwargs: client)
    monkeypatch.setattr(main, "settings", Settings())
    monkeypatch.setattr(main, "project_id", lambda: pytest.fail("the Vertex project was read"))

    def no_catalog(publisher):
        pytest.fail("the Vertex catalog was listed")

    monkeypatch.setattr("wcl_agent.llm.vertex.list_publisher_models", no_catalog)
    app = SimpleNamespace(state=SimpleNamespace())

    catalog, cached = await main._load_models(app)

    assert client.probed == ["claude-sonnet-4-20250514"]
    assert app.state.models == ["claude-sonnet-4-20250514"] and not app.state.models_degraded
    assert catalog.source == "static" and cached is False


# --- no key: one error, degraded models, no crash (AC 4) ----------------------------------------


class _BootTracker:
    """Runs only the steps under test; the others (DB, roster, guides) are skipped."""

    def __init__(self) -> None:
        self.ran: list[str] = []

    async def run(self, key, fn, *, optional=False, detail=None):
        if key not in ("models", "greeting"):
            return None
        self.ran.append(key)
        return await fn()

    def finish(self) -> None:
        self.finished = True

    def snapshot(self) -> dict:
        return {"elapsed_ms": 0}


async def test_boot_without_a_key_logs_one_error_and_serves_degraded_claude(env, use_provider, monkeypatch, caplog):  # noqa: F811
    use_provider("anthropic")
    monkeypatch.setattr(main, "settings", Settings())
    monkeypatch.setattr(main, "gc", SimpleNamespace(collect=lambda: None, freeze=lambda: None))
    app = SimpleNamespace(state=SimpleNamespace())
    tracker = _BootTracker()

    with caplog.at_level(logging.INFO):
        await main._boot(app, tracker)

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1 and "ANTHROPIC_API_KEY is not set" in errors[0].getMessage()
    assert "LLM provider: anthropic" in caplog.text
    assert tracker.ran == ["models", "greeting"] and tracker.finished
    assert app.state.models == CLAUDE_DEFAULTS and app.state.models_degraded
    assert not hasattr(app.state, "greeting_prime_task")


# --- the key never leaks (AC 4) -----------------------------------------------------------------


class _FakeSocket:
    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.frames.append(payload)


def _identity(authed) -> RequestIdentity:
    return RequestIdentity(
        user_id=authed.user_id,
        tenant_id=authed.tenant_id,
        membership_role="tenant_admin",
        is_platform_admin=False,
        session_id=uuid.uuid4(),
    )


def _quiet_socket(monkeypatch) -> None:
    async def no_suggestions(*args, **kwargs):
        return []

    monkeypatch.setattr(ws_mod, "generate_followups", no_suggestions)
    monkeypatch.setattr(ws_mod, "set_refresh_actor", lambda *_: None)


async def _chat_turn(authed, model: str) -> list[dict]:
    sock = _FakeSocket()
    task = await ws_mod._handle_turn(sock, ChatTurn(model=model, content="q"), _identity(authed))
    if task is not None:
        await task
    return sock.frames


async def test_the_key_never_reaches_logs_frames_or_responses(
    env, use_provider, scripted, as_user, patched_db, monkeypatch, caplog  # noqa: F811
):
    use_provider("anthropic", key=SENTINEL_KEY)
    unauthorized = (401, {})
    scripted(ScriptedApi(unauthorized, unauthorized))
    _quiet_socket(monkeypatch)
    monkeypatch.setattr(greeting_api, "GREETING_MODEL", "claude-haiku-5-5")

    with caplog.at_level(logging.DEBUG):
        frames = await _chat_turn(as_user, "claude-sonnet-5-5")
        responses = [
            await as_user.client.get("/api/models"),
            await as_user.client.get("/api/health"),
            await as_user.client.get("/api/greeting"),
        ]

    assert frames[-1]["type"] == "error" and frames[-1]["code"] == "agent_error"
    assert "401" in frames[-1]["message"]  # the SDK's error reached the player, minus the key
    exposed = [caplog.text, json.dumps(frames), *(r.text for r in responses)]
    exposed += [r.exc_text or "" for r in caplog.records]
    assert all(SENTINEL_KEY not in text for text in exposed)


async def test_a_turn_without_a_key_ends_with_a_plain_error(env, use_provider, as_user, patched_db, monkeypatch):  # noqa: F811
    use_provider("anthropic")
    _quiet_socket(monkeypatch)

    frames = await _chat_turn(as_user, "claude-sonnet-5-5")

    assert frames[-1]["code"] == "agent_error"
    assert "ANTHROPIC_API_KEY is not set" in frames[-1]["message"]
    assert "Traceback" not in frames[-1]["message"]


# --- chats on an unserved model continue on the default (AC 6, D4) --------------------------


class _FakeWebSocket:
    """Just enough of a WebSocket for ``ws.chat``: one turn, then the client leaves."""

    def __init__(self, app, *turns: dict) -> None:
        self.app = app
        self.headers = {"origin": "http://localhost:5173"}
        self.cookies = {}
        self.turns = list(turns)
        self.sent: list[dict] = []

    async def accept(self) -> None:
        pass

    async def close(self, code: int = 1000) -> None:
        pass

    async def receive_json(self) -> dict:
        if not self.turns:
            raise WebSocketDisconnect()
        return self.turns.pop(0)

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


async def _chat_models(monkeypatch, served: list[str], default: str, *models: str) -> tuple[list[str], list[dict]]:
    started: list[str] = []

    async def start(sock, turn, identity, *, fallback_model=None):
        started.append(turn.model)

    async def authenticated(_cookie):
        return SimpleNamespace(tenant_id=uuid.uuid4(), user_id=uuid.uuid4())

    monkeypatch.setattr(ws_mod, "origin_matches", lambda _origin: True)
    monkeypatch.setattr(ws_mod, "authenticate_session", authenticated)
    monkeypatch.setattr(ws_mod, "_start_turn", start)
    app = SimpleNamespace(state=SimpleNamespace(models=served, default_model=default))
    ws = _FakeWebSocket(app, *({"model": m, "content": "hi"} for m in models))
    await ws_mod.chat(ws)
    return started, ws.sent


async def test_ws_turn_on_an_unserved_model_runs_on_the_default(env, use_provider, monkeypatch):  # noqa: F811
    use_provider("anthropic", key=SENTINEL_KEY)
    served = ["claude-sonnet-5-5", "claude-sonnet-4-20250514"]

    started, sent = await _chat_models(
        monkeypatch, served, "claude-sonnet-5-5", "gemini-3.6-flash", "claude-sonnet-4@20250514", "claude-gone-1"
    )

    assert started == ["claude-sonnet-5-5", "claude-sonnet-4-20250514", "claude-sonnet-5-5"]
    assert sent == []  # no invalid_model frame


async def test_ws_turn_on_a_served_model_is_unchanged(env, use_provider, monkeypatch):  # noqa: F811
    use_provider("vertex")
    started, sent = await _chat_models(
        monkeypatch, ["gemini-3.6-flash", "gemini-3.1-pro-preview"], "gemini-3.6-flash", "gemini-3.1-pro-preview"
    )
    assert started == ["gemini-3.1-pro-preview"] and sent == []


async def test_rest_still_rejects_an_unserved_model(as_user):
    resp = await as_user.client.post("/api/conversations", json={"model": "gemini-0-retired"})
    assert resp.status_code == 400 and resp.json()["detail"] == "invalid_model"
