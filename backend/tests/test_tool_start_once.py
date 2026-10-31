"""sc-289: one tool call yields exactly one ``tool_start`` however many partial events repeat it.

The Anthropic stream emits a partial event for the call's start and one per argument chunk,
all with the same call id and no complete args; Gemini's progressive stream emits partials
that carry the call and then repeats it in the aggregated final event. ``_run_turn`` is
driven with synthetic ADK events (no model needed).
"""

from __future__ import annotations

import itertools
from types import SimpleNamespace

from backend.app import agent_runner


class _FakeRunner:
    def __init__(self, events):
        self._events = events

    async def run_async(self, **kwargs):
        for e in self._events:
            yield e


def _call(name: str, call_id: str | None, args: dict | None):
    return SimpleNamespace(
        function_call=SimpleNamespace(name=name, id=call_id, args=args),
        function_response=None,
        thought=False,
        text=None,
    )


def _response(name: str, call_id: str | None):
    return SimpleNamespace(
        function_call=None,
        function_response=SimpleNamespace(name=name, id=call_id, response={"status": "success"}),
        thought=False,
        text=None,
    )


def _event(*parts, partial=False):
    ev = SimpleNamespace(
        grounding_metadata=None, content=SimpleNamespace(parts=list(parts)), partial=partial
    )
    ev.is_final_response = lambda: False
    return ev


async def _collect(monkeypatch, events, clock=None):
    monkeypatch.setattr(agent_runner, "_get_runner", lambda model: _FakeRunner(events))

    async def _noop(_session_id, _user_id=None):
        return None

    monkeypatch.setattr(agent_runner, "_ensure_session", _noop)
    if clock is not None:
        monkeypatch.setattr(agent_runner.time, "monotonic", clock)
    frames = [f async for f in agent_runner.stream_response("m", "sess", "hi")]
    return [f for f in frames if f["type"] in ("tool_start", "tool_end")]


async def test_repeated_partials_of_one_call_start_once_with_final_args(monkeypatch):
    events = [
        _event(_call("propose_profile_changes", "c1", None), partial=True),
        *[_event(_call("propose_profile_changes", "c1", None), partial=True) for _ in range(20)],
        _event(_call("propose_profile_changes", "c1", {"changes": ["a"]})),  # aggregated final
        _event(_response("propose_profile_changes", "c1")),
    ]
    frames = await _collect(monkeypatch, events)
    starts = [f for f in frames if f["type"] == "tool_start"]
    assert len(starts) == 1
    assert starts[0]["args"] == {"changes": ["a"]}  # the complete args, not a fragment
    assert [f["type"] for f in frames] == ["tool_start", "tool_end"]
    assert frames[1]["args"] == {"changes": ["a"]}


async def test_two_distinct_calls_of_the_same_tool_start_twice(monkeypatch):
    events = [
        _event(_call("get_report_table", "c1", None), partial=True),
        _event(_call("get_report_table", "c2", None), partial=True),
        _event(
            _call("get_report_table", "c1", {"report_code": "A"}),
            _call("get_report_table", "c2", {"report_code": "B"}),
        ),
        _event(_response("get_report_table", "c1"), _response("get_report_table", "c2")),
    ]
    frames = await _collect(monkeypatch, events)
    starts = [f for f in frames if f["type"] == "tool_start"]
    assert [s["args"]["report_code"] for s in starts] == ["A", "B"]
    assert sum(1 for f in frames if f["type"] == "tool_end") == 2


async def test_call_without_an_id_does_not_flood(monkeypatch):
    # Partials never start a card (id or not); an id-less complete call starts once.
    events = [
        _event(_call("get_report_table", None, None), partial=True),
        _event(_call("get_report_table", None, None), partial=True),
        _event(_call("get_report_table", None, {"report_code": "A"})),
        _event(_response("get_report_table", None)),
    ]
    frames = await _collect(monkeypatch, events)
    starts = [f for f in frames if f["type"] == "tool_start"]
    assert len(starts) == 1 and starts[0]["args"] == {"report_code": "A"}
    ends = [f for f in frames if f["type"] == "tool_end"]
    assert len(ends) == 1 and "ms" not in ends[0]  # no id, nothing to correlate


async def test_non_partial_stream_is_unchanged(monkeypatch):
    # Vertex-style: the call arrives once, complete, in a non-partial event.
    events = [
        _event(_call("get_report_table", "c1", {"report_code": "A"})),
        _event(_response("get_report_table", "c1")),
    ]
    frames = await _collect(monkeypatch, events)
    assert [f["type"] for f in frames] == ["tool_start", "tool_end"]
    assert frames[0]["args"] == {"report_code": "A"}


async def test_the_same_complete_call_repeated_starts_once_and_keeps_its_first_clock(monkeypatch):
    events = [
        _event(_call("get_report_table", "c1", {"report_code": "A"})),
        _event(_call("get_report_table", "c1", {"report_code": "A"})),  # repeated, same id
        _event(_response("get_report_table", "c1")),
    ]
    ticks = itertools.count(0, 2)  # 0 s, 2 s, ...: a restart on the repeat would shorten ms
    frames = await _collect(monkeypatch, events, clock=lambda: float(next(ticks)))
    assert [f["type"] for f in frames] == ["tool_start", "tool_end"]
    assert frames[1]["ms"] == 2000
