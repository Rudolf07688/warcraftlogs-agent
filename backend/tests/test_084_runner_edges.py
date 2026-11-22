"""084: the runner's side of the re-runs and the sc-582 status edge cases.

Synthetic ADK events through ``stream_response`` (no model), as in test_080_thinking_runner.
Also the producer side of contract:chat-status-records: the four record shapes, pinned.
"""

from __future__ import annotations

import logging

import anthropic
import httpx2
import pytest

from backend.app import agent_runner
from backend.app.agent_runner import _status_line
from backend.tests.test_080_thinking_runner import (
    CHAT_USER,
    _answer,
    _call,
    _Clock,
    _event,
    _lines,
    _records,
    _response,
    _Runner,
    _text,
    _thought,
)
from wcl_agent.llm import model_retry
from wcl_agent.llm.model_retry import RetryPolicy, TurnStats, current_turn


class _RerunRunner(_Runner):
    """Marks a model call's re-run (as the model wrapper does) where the script says ``"rerun"``."""

    async def run_async(self, **kwargs):
        for e in self._events:
            if e == "rerun":
                current_turn.get().budget_retries += 1
                continue
            yield e


# --- BUG-005: a re-run's thoughts are not spliced onto the cut-off call's ---------------------


async def test_a_reruns_status_line_comes_from_its_own_thoughts(monkeypatch):
    events = [
        _event(_thought("Weighing every boss on the list against "), partial=True),
        "rerun",
        _event(_thought("Short plan: compare the deaths."), partial=True),
        _event(_text("Deaths first."), final=True),
    ]
    records = await _run(monkeypatch, _RerunRunner(events))
    assert _lines(records) == ["Short plan: compare the deaths."]


async def _run(monkeypatch, runner) -> list[dict]:
    """``_records`` with a runner of the test's own."""
    monkeypatch.setattr(agent_runner, "_get_runner", lambda model: runner)
    monkeypatch.setattr(agent_runner, "_thinking_clock", _Clock(2.0))

    async def _noop(_session_id, _user_id=None):
        return None

    monkeypatch.setattr(agent_runner, "_ensure_session", _noop)
    return [r async for r in agent_runner.stream_response("m", "s", "hi", user_id=CHAT_USER)]


# --- BUG-006: retracted text comes back when the turn ends on a pending call -----------------


async def test_retracted_text_comes_back_when_the_turn_ends_with_a_call_pending(monkeypatch):
    events = [
        _event(_text("Her deaths came from Gravebound."), partial=True),
        _event(_call("c1")),  # never answered: ADK stopped, or a long-running tool
    ]
    records = await _records(monkeypatch, events)
    assert _lines(records, "interim") == ["Her deaths came from Gravebound."]
    # What the player saw comes back after the retraction; no no-answer message with a call pending.
    assert _answer(records) == "Her deaths came from Gravebound."
    assert not any(r.get("empty") for r in records if r["type"] == "token")


async def test_only_the_last_retracted_text_comes_back_on_a_pending_ending(monkeypatch):
    events = [
        _event(_text("Let me check."), partial=True),
        _event(_call("c1")),
        _event(_response("c1")),
        _event(_text("Nobody died."), partial=True),
        _event(_call("c2")),
    ]
    records = await _records(monkeypatch, events)
    assert _answer(records) == "Nobody died."


# --- SPEC L1: a heading line is a sentence ------------------------------------------------------


@pytest.mark.parametrize(
    "text, line",
    [
        ("**Analyzing the deaths**\nI am comparing the death times across pulls.", "Analyzing the deaths"),
        ("## Plan\nCompare the pulls one by one.", "Plan"),
        ("Done with damage.\n\n**Checking healing**\nThe healers", "Checking healing"),
        ("**Analyzing the deaths**\n\nI am comparing.", "I am comparing."),  # unchanged: latest paragraph
        ("**bold** move then more text.", "bold move then more text."),  # not a heading line
    ],
)
def test_a_heading_line_counts_as_a_sentence(text, line):
    assert _status_line(text) == line


def test_an_unfinished_heading_line_waits_for_its_line_end():
    assert _status_line("Done with damage.\n\n**Checking heal") == "Done with damage."


# --- sc-580 L2: the turn stats line shows the re-runs ----------------------------------------


async def test_the_turn_stats_line_shows_budget_and_empty_retries(monkeypatch, caplog):
    class Rerunning(_Runner):
        async def run_async(self, **kwargs):
            stats = current_turn.get()
            stats.budget_retries += 1
            stats.empty_retries += 2
            yield _event(_text("Ok."), final=True)

    caplog.set_level(logging.INFO, logger="backend.app.agent_runner")
    await _run(monkeypatch, Rerunning([]))
    (line,) = [r.getMessage() for r in caplog.records if r.getMessage().startswith("turn stats")]
    assert "budget_retries=1 empty_retries=2" in line


# --- contract:chat-status-records: the producer's four shapes ---------------------------------


def _shape(record: dict) -> dict:
    return {k: type(v).__name__ for k, v in record.items()}


async def test_thinking_and_interim_records_keep_their_shapes(monkeypatch):
    events = [
        _event(_thought("Comparing the pulls.\n\n"), partial=True),
        _event(_text("Let me check."), partial=True),
        _event(_call("c1")),
        _event(_response("c1")),
        _event(_text("Ok."), final=True),
    ]
    records = await _records(monkeypatch, events)
    shapes = {r["type"]: _shape(r) for r in records if r["type"] in ("thinking", "interim")}
    assert shapes == {"thinking": {"type": "str", "text": "str"}, "interim": {"type": "str", "text": "str"}}


async def test_model_retry_and_fallback_records_keep_their_shapes(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(model_retry.asyncio, "sleep", no_sleep)
    busy = anthropic.RateLimitError(
        "busy",
        response=httpx2.Response(429, headers={"retry-after": "4"}, request=httpx2.Request("POST", "https://x")),
        body=None,
    )
    records: list[dict] = []
    stats = TurnStats(model="claude-a", notify=records.append, fallback_model="claude-b")
    token = current_turn.set(stats)
    try:

        def inner():
            async def gen():
                if llm_request.model == "claude-a":
                    raise busy
                yield "ok"

            return gen()

        from google.adk.models.llm_request import LlmRequest

        llm_request = LlmRequest(model="claude-a", contents=[])
        out = [r async for r in model_retry.generate_with_fallback(inner, llm_request, RetryPolicy(attempts=5))]
    finally:
        current_turn.reset(token)
        model_retry.forget_rate_limits()
    assert out == ["ok"]
    retry = next(r for r in records if r["type"] == "model_retry")
    fallback = next(r for r in records if r["type"] == "model_fallback")
    # The contract's example: {"type":"model_retry","attempt":1,"max_attempts":5,"wait_s":4.0}
    assert retry == {"type": "model_retry", "attempt": 1, "max_attempts": 2, "wait_s": 4.0}
    assert _shape(retry) == {"type": "str", "attempt": "int", "max_attempts": "int", "wait_s": "float"}
    assert fallback == {"type": "model_fallback", "from_model": "claude-a", "to_model": "claude-b"}
