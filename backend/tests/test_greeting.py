"""US5: cached Barnaby greeting with graceful failure."""

from __future__ import annotations

import types

from backend.app import greeting as greeting_mod


def _make_app(**state) -> types.SimpleNamespace:
    return types.SimpleNamespace(state=types.SimpleNamespace(**state))


async def test_get_greeting_returns_cached_on_hit(monkeypatch):
    app = _make_app(greeting_cache={"m": "Well met, friend!"})

    async def _boom(*a, **k):  # must not be called on a cache hit
        raise AssertionError("should not generate on cache hit")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(greeting_mod, "stream_response", _boom)
    assert await greeting_mod.get_greeting(app, "m") == "Well met, friend!"


async def test_get_greeting_generation_failure_returns_empty(monkeypatch):
    app = _make_app()

    async def _failing(*a, **k):
        raise RuntimeError("no vertex")
        yield  # pragma: no cover

    monkeypatch.setattr(greeting_mod, "stream_response", _failing)
    assert await greeting_mod.get_greeting(app, "m") == ""
    assert "m" not in app.state.greeting_cache  # nothing cached on failure


async def test_get_greeting_generates_and_caches(monkeypatch):
    app = _make_app()

    async def _gen(model, session_id, text, scratch=None, **_kw):
        assert text == greeting_mod.GREETING_KICKOFF
        yield {"type": "token", "text": "Well "}
        yield {"type": "tool_start", "name": "noise"}  # ignored
        yield {"type": "token", "text": "met!"}

    monkeypatch.setattr(greeting_mod, "stream_response", _gen)
    assert await greeting_mod.get_greeting(app, "m") == "Well met!"
    assert app.state.greeting_cache["m"] == "Well met!"


# --- feature 011 / FR-012: the greeting never waits out a rate limit ----------------------

from wcl_agent.llm.model_retry import ModelRateLimited  # noqa: E402


async def test_generate_greeting_disables_retry(monkeypatch):
    seen: dict = {}

    async def _gen(model, session_id, text, *a, **kwargs):
        seen.update(kwargs)
        yield {"type": "token", "text": "Well met!"}

    monkeypatch.setattr(greeting_mod, "stream_response", _gen)
    assert await greeting_mod._generate_greeting("m") == "Well met!"
    assert seen.get("retry") is False


async def test_generate_greeting_rate_limited_returns_empty(monkeypatch):
    async def _limited(*a, **k):
        raise ModelRateLimited(1, 0.0, RuntimeError("429"))
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(greeting_mod, "stream_response", _limited)
    app = _make_app()
    assert await greeting_mod.get_greeting(app, "m") == ""
    assert "m" not in app.state.greeting_cache
