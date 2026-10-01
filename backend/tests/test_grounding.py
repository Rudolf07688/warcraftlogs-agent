"""US3 tests: grounding frame emission + graceful degradation.

stream_response is driven with synthetic ADK events (no Vertex needed) to assert
the grounding signal surfaces, and that non-grounding turns emit nothing extra.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app import agent_runner
from wcl_agent.agent import WEB_SEARCH_AGENT_NAME


class _FakeRunner:
    def __init__(self, events):
        self._events = events

    async def run_async(self, **kwargs):
        for e in self._events:
            yield e


def _text_part(text: str):
    return SimpleNamespace(function_call=None, function_response=None, thought=False, text=text)


def _call_part(name: str, call_id: str = "1", args: dict | None = None):
    return SimpleNamespace(
        function_call=SimpleNamespace(name=name, id=call_id, args=args or {}),
        function_response=None,
        thought=False,
        text=None,
    )


def _event(parts=None, grounding_metadata=None, partial=False, final=False):
    ev = SimpleNamespace(
        grounding_metadata=grounding_metadata,
        content=SimpleNamespace(parts=parts) if parts is not None else None,
        partial=partial,
    )
    ev.is_final_response = lambda: final
    return ev


def _grounding_meta(title="Patch 11.2 notes", uri="https://example.com"):
    return SimpleNamespace(
        grounding_chunks=[SimpleNamespace(web=SimpleNamespace(title=title, uri=uri))]
    )


async def _collect(monkeypatch, events):
    monkeypatch.setattr(agent_runner, "_get_runner", lambda model: _FakeRunner(events))

    async def _noop(_session_id):
        return None

    monkeypatch.setattr(agent_runner, "_ensure_session", _noop)
    return [f async for f in agent_runner.stream_response("gemini-3.6-flash", "sess", "hi")]


async def test_grounding_frame_from_metadata(monkeypatch):
    events = [
        _event(grounding_metadata=_grounding_meta()),
        _event(parts=[_text_part("Here is the current info.")], final=True),
    ]
    frames = await _collect(monkeypatch, events)
    grounding = [f for f in frames if f["type"] == "grounding"]
    assert len(grounding) == 1
    assert grounding[0]["used"] is True
    assert grounding[0]["sources"][0]["uri"] == "https://example.com"


async def test_grounding_frame_from_web_search_tool_call(monkeypatch):
    events = [
        _event(parts=[_call_part(WEB_SEARCH_AGENT_NAME)]),
        _event(parts=[_text_part("answer")], final=True),
    ]
    frames = await _collect(monkeypatch, events)
    grounding = [f for f in frames if f["type"] == "grounding"]
    assert len(grounding) == 1 and grounding[0]["used"] is True


async def test_grounding_emitted_once(monkeypatch):
    events = [
        _event(grounding_metadata=_grounding_meta()),
        _event(grounding_metadata=_grounding_meta()),
        _event(parts=[_text_part("answer")], final=True),
    ]
    frames = await _collect(monkeypatch, events)
    assert sum(1 for f in frames if f["type"] == "grounding") == 1


async def test_no_grounding_when_absent(monkeypatch):
    # Simulates a non-grounding (e.g. Anthropic) turn: plain answer, no web use.
    events = [_event(parts=[_text_part("answer from available data")], final=True)]
    frames = await _collect(monkeypatch, events)
    assert not any(f["type"] == "grounding" for f in frames)
    assert any(f["type"] == "token" for f in frames)
