"""080: thinking status lines and interim text, at the runner (sc-569, sc-572 structural).

Drives ``stream_response`` with synthetic ADK events (no model), like test_046. Model text is
untrusted, so the hostile thought texts are checked on the record the socket would send.
"""

from __future__ import annotations

import unicodedata
from types import SimpleNamespace

import pytest
from google.genai import types

from backend.app import agent_runner
from backend.app.agent_runner import STATUS_LINE_CHARS

CHAT_USER = "6f1c0a52-8a3e-4c55-9d43-1f7e0c3b2a10"
ROOT = "wcl_agent"


def _thought(text: str):
    return SimpleNamespace(function_call=None, function_response=None, thought=True, text=text)


def _text(text: str):
    return SimpleNamespace(function_call=None, function_response=None, thought=False, text=text)


def _call(call_id: str):
    call = SimpleNamespace(name="get_report_participants", id=call_id, args={"report_code": "aB3xY9"})
    return SimpleNamespace(function_call=call, function_response=None, thought=False, text=None)


def _response(call_id: str, status: str = "error"):
    response = SimpleNamespace(name="get_report_participants", id=call_id, response={"status": status})
    return SimpleNamespace(function_call=None, function_response=response, thought=False, text=None)


def _event(*parts, partial=False, final=False, author=ROOT):
    ev = SimpleNamespace(
        grounding_metadata=None, content=SimpleNamespace(parts=list(parts)), partial=partial, author=author
    )
    ev.is_final_response = lambda: final
    return ev


class _Runner:
    agent = SimpleNamespace(name=ROOT)

    def __init__(self, events):
        self._events = events

    async def run_async(self, **kwargs):
        for e in self._events:
            yield e


class _Clock:
    """A fake clock for the throttle; each event advances it by ``step`` seconds."""

    def __init__(self, step: float) -> None:
        self.now, self.step = 100.0, step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


async def _records(monkeypatch, events, user_id=CHAT_USER, step=2.0) -> list[dict]:
    monkeypatch.setattr(agent_runner, "_get_runner", lambda model: _Runner(events))
    monkeypatch.setattr(agent_runner, "_thinking_clock", _Clock(step))

    async def _noop(_session_id, _user_id=None):
        return None

    monkeypatch.setattr(agent_runner, "_ensure_session", _noop)
    return [r async for r in agent_runner.stream_response("m", "s", "hi", user_id=user_id)]


def _answer(records) -> str:
    last = max((i for i, r in enumerate(records) if r["type"] == "interim"), default=-1)
    return "".join(r["text"] for r in records[last + 1 :] if r["type"] == "token")


def _lines(records, kind="thinking") -> list[str]:
    return [r["text"] for r in records if r["type"] == kind]


# --- sc-569: hostile thought text ---------------------------------------------------------

HOSTILE = [
    "<img src=x onerror=alert(1)>",
    "[x](javascript:alert(1))",
    "**bold** move",
    "```html\n<script>alert(1)</script>\n```",
    "x" * 10_000,
    "first\nsecond\r\nthird\tfourth",
    "\x1b[31mred\x1b[0m and \x1b]0;title\x07 done",
    "safe ‮evil‬ ⁦iso⁩ zero​width \x00\x07\x7f",
]


@pytest.mark.parametrize("text", HOSTILE)
async def test_a_hostile_thought_becomes_one_plain_capped_line(monkeypatch, text):
    records = await _records(monkeypatch, [_event(_thought(text), final=True), _event(_text("Ok."), final=True)])
    (line,) = _lines(records)
    assert 0 < len(line) <= STATUS_LINE_CHARS + 1  # 80 plus the ellipsis
    assert not any(unicodedata.category(ch) in ("Cc", "Cf") for ch in line)  # no newline, ESC, bidi
    assert "**" not in line and "`" not in line
    assert line == " ".join(line.split())
    assert _answer(records) == "Ok."  # the thought never reaches the answer


async def test_a_long_thought_without_a_sentence_end_is_capped_while_it_streams(monkeypatch):
    chunks = [_event(_thought("y" * 1000), partial=True) for _ in range(10)]
    records = await _records(monkeypatch, [*chunks, _event(_text("Ok."), final=True)])
    assert _lines(records) == ["y" * STATUS_LINE_CHARS + "…"]


async def test_the_status_is_the_first_sentence_of_the_latest_paragraph(monkeypatch):
    events = [
        _event(_thought("**Checking the deaths**\n\n"), partial=True),
        _event(_thought("I'm comparing the death times. Then the "), partial=True),
        _event(_thought("buffs."), partial=True),
        _event(_text("Ok."), final=True),
    ]
    records = await _records(monkeypatch, events)
    assert _lines(records) == ["Checking the deaths", "I'm comparing the death times."]


# --- sc-569: when status lines are sent ----------------------------------------------------


async def test_status_lines_are_throttled_to_one_a_second(monkeypatch):
    sentences = [f"Step {i} is under way." for i in range(6)]
    events = [_event(_thought(s + "\n\n"), partial=True) for s in sentences]
    # The fake clock moves 0.4 s per thought: a line at 0.4 s, then at 1.6 s; 2.0 and 2.4 s
    # fall within a second of it.
    records = await _records(monkeypatch, [*events, _event(_text("Ok."), final=True)], step=0.4)
    assert _lines(records) == ["Step 0 is under way.", "Step 3 is under way."]


async def test_no_status_once_the_answer_has_started(monkeypatch):
    events = [
        _event(_thought("Looking at the pulls.\n\n"), partial=True),
        _event(_text("Vagxsu"), partial=True),
        _event(_thought("A late thought about buffs.\n\n"), partial=True),
        _event(_text(" topped damage."), partial=True),
        _event(_thought("Looking at the pulls. A late thought."), _text("Vagxsu topped damage."), final=True),
    ]
    records = await _records(monkeypatch, events)
    assert _lines(records) == ["Looking at the pulls."]
    assert records.index({"type": "thinking", "text": "Looking at the pulls."}) < records.index(
        {"type": "token", "text": "Vagxsu"}
    )


async def test_a_sub_agents_thoughts_give_no_status(monkeypatch):
    events = [
        _event(_thought("Searching the web for the boss.\n\n"), partial=True, author="web_search"),
        _event(_text("Ok."), final=True),
    ]
    assert _lines(await _records(monkeypatch, events)) == []


async def test_the_claude_contract_example_yields_a_status_line(monkeypatch):
    # contract:claude-thinking-summaries: a streamed partial event with a thought=True Part.
    part = types.Part(text="I am comparing the death times...", thought=True)
    events = [_event(part, partial=True), _event(_text("Ok."), final=True)]
    assert _lines(await _records(monkeypatch, events)) == ["I am comparing the death times..."]


async def test_the_final_thought_is_used_only_when_nothing_streamed(monkeypatch):
    # Claude (Vera #53): the call's final event repeats the whole summary; Gemini may send
    # thoughts only there.
    streamed = [
        _event(_thought("Reading the fight."), partial=True),
        _event(_thought("Reading the fight. Then the deaths."), _call("c1")),
    ]
    records = await _records(monkeypatch, [*streamed, _event(_response("c1")), _event(_text("Ok."), final=True)])
    assert _lines(records) == ["Reading the fight."]
    only_final = [_event(_thought("Reading the fight."), _call("c1"))]
    records = await _records(monkeypatch, [*only_final, _event(_response("c1")), _event(_text("Ok."), final=True)])
    assert _lines(records) == ["Reading the fight."]


async def test_each_round_starts_its_status_afresh(monkeypatch):
    events = [
        _event(_thought("Reading the fight.\n\n"), partial=True),
        _event(_call("c1")),
        _event(_response("c1")),
        _event(_thought("Reading the fight.\n\n"), partial=True),
        _event(_text("Ok."), final=True),
    ]
    assert _lines(await _records(monkeypatch, events)) == ["Reading the fight.", "Reading the fight."]


# --- sc-572: interim text ------------------------------------------------------------------

TROUBLESHOOTING = [
    "Warcraft Logs is throwing server errors on report aB3xY9's player lists.",
    " I'll retry with her own boss history (source 4471).",
]


async def test_text_before_a_tool_call_is_retracted_and_shown_as_status(monkeypatch):
    events = [
        *[_event(_text(t), partial=True) for t in TROUBLESHOOTING],
        _event(_text("".join(TROUBLESHOOTING)), _call("c1")),
        _event(_response("c1", "success")),
        _event(_text("Her deaths came from "), partial=True),
        _event(_text("Gravebound."), partial=True),
        _event(_text("Her deaths came from Gravebound."), final=True),
    ]
    records = await _records(monkeypatch, events)
    kinds = [r["type"] for r in records]
    assert kinds.index("interim") < kinds.index("tool_start")
    assert _lines(records, "interim") == [TROUBLESHOOTING[0]]
    answer = _answer(records)
    assert answer == "Her deaths came from Gravebound."  # no paragraph join, no troubleshooting
    assert "aB3xY9" not in answer and "retry" not in answer and "4471" not in answer


async def test_text_after_a_call_in_the_same_round_is_retracted_at_its_result(monkeypatch):
    events = [
        _event(_call("c1"), _text("Hold on, retrying report aB3xY9.")),
        _event(_text("Hold on, retrying report aB3xY9."), partial=True),
        _event(_response("c1")),
        _event(_text("Done."), final=True),
    ]
    records = await _records(monkeypatch, events)
    kinds = [r["type"] for r in records]
    assert kinds.index("interim") < kinds.index("tool_end")
    assert _answer(records) == "Done."


async def test_status_resumes_after_a_retraction(monkeypatch):
    events = [
        _event(_text("Let me check."), partial=True),
        _event(_call("c1")),
        _event(_response("c1")),
        _event(_thought("Comparing the pulls.\n\n"), partial=True),
        _event(_text("Ok."), final=True),
    ]
    assert _lines(await _records(monkeypatch, events)) == ["Comparing the pulls."]


# --- Greeting, guide jobs and evals: unchanged ---------------------------------------------


async def test_the_default_local_user_gets_todays_records(monkeypatch):
    events = [
        _event(_thought("Reading the fight.\n\n"), partial=True),
        _event(_text("Let me get the totals."), partial=True),
        _event(_call("c1")),
        _event(_response("c1", "success")),
        _event(_text("Vagxsu topped damage."), final=True),
    ]
    records = await _records(monkeypatch, events, user_id=agent_runner.USER_ID)
    assert [r for r in records if r["type"] in ("token", "thinking", "interim")] == [
        {"type": "token", "text": "Let me get the totals."},
        {"type": "token", "text": "\n\nVagxsu topped damage."},
    ]
