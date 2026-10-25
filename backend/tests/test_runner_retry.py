"""Feature 011: stream_response turn plumbing — queue merge, stats log, cancellation.

Driven with synthetic ADK events like test_grounding.py (no Vertex needed).
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from backend.app import agent_runner
from wcl_agent.llm.model_retry import ModelRateLimited, current_turn


def _text_event(text: str, *, partial: bool = False):
    """A final text event by default; ``partial=True`` makes a streamed token event."""
    ev = SimpleNamespace(
        grounding_metadata=None,
        content=SimpleNamespace(
            parts=[SimpleNamespace(function_call=None, function_response=None, thought=False, text=text)]
        ),
        partial=partial,
    )
    ev.is_final_response = lambda: not partial
    return ev


class _Runner:
    """Fake ADK runner whose behaviour is a coroutine function receiving the stats."""

    def __init__(self, script):
        self._script = script

    async def run_async(self, **kwargs):
        async for ev in self._script(current_turn.get()):
            yield ev


def _install(monkeypatch, script):
    monkeypatch.setattr(agent_runner, "_get_runner", lambda model: _Runner(script))

    async def _noop(_session_id, _user_id=None):
        return None

    monkeypatch.setattr(agent_runner, "_ensure_session", _noop)


def _stats_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("turn stats")]


async def test_records_in_order_and_stats_line_answered(monkeypatch, caplog):
    async def script(_stats):
        yield _text_event("hello")

    _install(monkeypatch, script)
    with caplog.at_level(logging.INFO, logger="backend.app.agent_runner"):
        out = [r async for r in agent_runner.stream_response("gemini-3.6-flash", "s", "hi")]
    assert out == [{"type": "token", "text": "hello"}]
    (line,) = _stats_lines(caplog)
    assert "model=gemini-3.6-flash" in line
    assert "requests=0 rounds=0 retries=0" in line and "outcome=answered" in line
    assert current_turn.get() is None  # reset after the turn


async def test_notify_record_is_yielded_while_producer_sleeps(monkeypatch):
    async def script(stats):
        assert stats is not None and stats.retry_enabled
        stats.emit({"type": "model_retry", "attempt": 1, "max_attempts": 5, "wait_s": 0.1})
        await asyncio.sleep(0.05)
        yield _text_event("after")

    _install(monkeypatch, script)
    out = [r async for r in agent_runner.stream_response("m", "s", "hi")]
    assert out[0]["type"] == "model_retry"
    assert out[1] == {"type": "token", "text": "after"}


async def test_retry_flag_reaches_turn_stats(monkeypatch):
    seen = {}

    async def script(stats):
        seen["enabled"] = stats.retry_enabled
        yield _text_event("x")

    _install(monkeypatch, script)
    [r async for r in agent_runner.stream_response("m", "s", "hi", retry=False)]
    assert seen["enabled"] is False


async def test_early_close_cancels_producer_and_logs_abandoned(monkeypatch, caplog):
    cancelled = asyncio.Event()

    async def script(_stats):
        yield _text_event("first", partial=True)  # streamed token: yielded immediately
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        yield _text_event("never", partial=True)  # pragma: no cover

    _install(monkeypatch, script)
    gen = agent_runner.stream_response("m", "s", "hi")
    with caplog.at_level(logging.INFO, logger="backend.app.agent_runner"):
        first = await gen.__anext__()
        assert first["text"] == "first"
        await gen.aclose()
    assert cancelled.is_set()
    (line,) = _stats_lines(caplog)
    assert "outcome=abandoned" in line


async def test_producer_error_propagates_and_logs_error(monkeypatch, caplog):
    async def script(_stats):
        raise RuntimeError("vertex down")
        yield  # pragma: no cover - makes this an async generator

    _install(monkeypatch, script)
    with caplog.at_level(logging.INFO, logger="backend.app.agent_runner"):
        with pytest.raises(RuntimeError, match="vertex down"):
            [r async for r in agent_runner.stream_response("m", "s", "hi")]
    (line,) = _stats_lines(caplog)
    assert "outcome=error" in line


async def test_rate_limited_outcome(monkeypatch, caplog):
    async def script(stats):
        stats.retries = 3
        stats.waited_s = 12.0
        raise ModelRateLimited(4, 12.0, RuntimeError("429"))
        yield  # pragma: no cover

    _install(monkeypatch, script)
    with caplog.at_level(logging.INFO, logger="backend.app.agent_runner"):
        with pytest.raises(ModelRateLimited):
            [r async for r in agent_runner.stream_response("m", "s", "hi")]
    (line,) = _stats_lines(caplog)
    assert "retries=3 waited_s=12.0 outcome=rate_limited" in line
