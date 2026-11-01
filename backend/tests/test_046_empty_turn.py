"""A big-report turn always ends with something readable (046, sc-302).

``stream_response`` is driven with synthetic ADK events (no model): tools then an empty final
response end a chat turn with the no-answer message and ``outcome=empty``; interim text and the
answer are separate paragraphs; the turn-stats line counts tool calls (sc-339 AC4).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from backend.app import agent_runner
from backend.app.agent_runner import EMPTY_ANSWER_MESSAGE

CHAT_USER = "6f1c0a52-8a3e-4c55-9d43-1f7e0c3b2a10"  # a chat turn runs as its workspace


def _part(*, call=None, response=None, text=None):
    return SimpleNamespace(function_call=call, function_response=response, thought=False, text=text)


def _call(call_id: str):
    return _part(call=SimpleNamespace(name="get_report_table", id=call_id, args={"report_code": "R1"}))


def _response(call_id: str):
    return _part(response=SimpleNamespace(name="get_report_table", id=call_id, response={"status": "success"}))


def _event(*parts, partial=False, final=False):
    ev = SimpleNamespace(grounding_metadata=None, content=SimpleNamespace(parts=list(parts)), partial=partial)
    ev.is_final_response = lambda: final
    return ev


class _Runner:
    def __init__(self, events):
        self._events = events

    async def run_async(self, **kwargs):
        for e in self._events:
            yield e


async def _turn(monkeypatch, caplog, events, user_id=CHAT_USER):
    monkeypatch.setattr(agent_runner, "_get_runner", lambda model: _Runner(events))

    async def _noop(_session_id, _user_id=None):
        return None

    monkeypatch.setattr(agent_runner, "_ensure_session", _noop)
    with caplog.at_level(logging.INFO, logger="backend.app.agent_runner"):
        records = [r async for r in agent_runner.stream_response("m", "s", "hi", user_id=user_id)]
    (line,) = [r.getMessage() for r in caplog.records if r.getMessage().startswith("turn stats")]
    text = "".join(r["text"] for r in records if r["type"] == "token")
    return text, line


def _interim_then_tools():
    return [
        _event(_part(text="Let me get the totals."), partial=True),
        _event(_call("c1"), _call("c2")),
        _event(_response("c1"), _response("c2")),
    ]


async def test_tools_then_an_empty_final_end_with_the_no_answer_message(monkeypatch, caplog):
    events = [*_interim_then_tools(), _event(_part(text=""), final=True)]
    text, line = await _turn(monkeypatch, caplog, events)
    assert text == "Let me get the totals.\n\n" + EMPTY_ANSWER_MESSAGE  # never just the interim line
    assert "outcome=empty" in line and "outcome=answered" not in line
    assert "tool_calls=2" in line


async def test_a_turn_with_no_text_at_all_gets_the_message(monkeypatch, caplog):
    text, line = await _turn(monkeypatch, caplog, [_event(_part(text=" "), final=True)])
    assert text == EMPTY_ANSWER_MESSAGE
    assert "outcome=empty" in line and "tool_calls=0" in line


async def test_interim_text_and_the_answer_are_separate_paragraphs(monkeypatch, caplog):
    events = [
        *_interim_then_tools(),
        _event(_part(text="1. **Vagxsu**"), partial=True),
        _event(_part(text=" 1.2M DPS"), partial=True),
        _event(_part(text="1. **Vagxsu** 1.2M DPS"), final=True),  # the aggregated repeat
    ]
    text, line = await _turn(monkeypatch, caplog, events)
    assert text == "Let me get the totals.\n\n1. **Vagxsu** 1.2M DPS"
    assert "outcome=answered" in line


async def test_an_answer_only_in_the_final_event_after_streamed_interim_text_is_kept(monkeypatch, caplog):
    events = [*_interim_then_tools(), _event(_part(text="Vagxsu topped damage."), final=True)]
    text, line = await _turn(monkeypatch, caplog, events)
    assert text == "Let me get the totals.\n\nVagxsu topped damage."
    assert "outcome=answered" in line


async def test_a_normal_answer_is_unchanged(monkeypatch, caplog):
    events = [_event(_part(text="Hello"), partial=True), _event(_part(text="Hello"), final=True)]
    text, line = await _turn(monkeypatch, caplog, events)
    assert text == "Hello"
    assert "outcome=answered" in line and "tool_calls=0" in line


async def test_a_pending_tool_call_is_not_reported_as_empty(monkeypatch, caplog):
    text, line = await _turn(monkeypatch, caplog, [_event(_call("c9"))])
    assert text == ""
    assert "outcome=answered" in line and "tool_calls=1" in line


async def test_greeting_and_guide_turns_keep_an_empty_result(monkeypatch, caplog):
    # They run as the default local user: the message must never become a cached greeting
    # or a stored guild summary.
    events = [*_interim_then_tools(), _event(_part(text=""), final=True)]
    text, line = await _turn(monkeypatch, caplog, events, user_id=agent_runner.USER_ID)
    assert text == "Let me get the totals."
    assert "outcome=answered" in line
