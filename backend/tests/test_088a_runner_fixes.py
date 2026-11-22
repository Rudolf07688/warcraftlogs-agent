"""088a: the runner fix round (BUG-001, BUG-003, BUG-007, BUG-008, PERF-001, PERF-007).

Model-wrapper tests fake the ADK parent (as in test_084_reruns); runner tests feed synthetic
events through ``stream_response`` (as in test_080_thinking_runner); the cache test replays
request bodies through test_087's ``simulate``.
"""

from __future__ import annotations

import json
import logging

from google.adk.models.anthropic_llm import AnthropicLlm
from google.adk.models.google_llm import Gemini
from google.genai import types

from backend.app import agent_runner
from backend.tests.test_080_thinking_runner import (
    _call,
    _event,
    _response,
    _Runner,
    _text,
)
from backend.tests.test_084_reruns import (
    GEMINI,
    MAX_TOKENS,
    Parent,
    _collect,
    _request,
    answer,
    clock,  # noqa: F401 - fixture used by name
    empty_stop,
    thought,
    turn,
)
from backend.tests.test_084_reruns import _response as _llm_response
from backend.tests.test_084_runner_edges import _run
from backend.tests.test_087_history_cache import (  # noqa: F401
    _ids,
    api,
    breakpoints,
    simulate,
    tenant,
)
from backend.tests.test_llm_provider_agent import (  # noqa: F401
    CLAUDE,
    _message_start,
    _sse,
    text_answer,
    use_provider,
)
from wcl_agent.llm.model_retry import (
    CUT_LINE,
    RetryingClaude,
    RetryingGemini,
    current_turn,
)


def _texts(responses, *, partial: bool) -> list[str]:
    return [
        p.text
        for r in responses
        if bool(r.partial) == partial and r.content
        for p in r.content.parts or []
        if p.text and not p.thought
    ]


def slow_text(clock, chunks, step_s=50.0, then=()):
    """A Claude stream sending ``chunks`` as answer text, each ``step_s`` later, then ``then``."""

    async def stream():
        for chunk in chunks:
            clock["t"] += step_s
            yield _llm_response(types.Part(text=chunk), partial=True)
        for item in then:
            clock["t"] += step_s
            yield item

    return stream


# --- BUG-001: a cut after answer text ends with one fixed closing line, counted -------------


async def test_a_call_cut_after_answer_text_ends_with_the_cut_line_and_counts_the_cut(clock, monkeypatch, caplog):
    parent = Parent(slow_text(clock, ["Overview: ", "boss one went ", "well, boss two ", "was"]), answer("again")).install(monkeypatch, AnthropicLlm)
    caplog.set_level(logging.WARNING, logger="wcl_agent.llm.model_retry")
    with turn(CLAUDE) as stats:
        out = await _collect(RetryingClaude(model=CLAUDE), _request(CLAUDE))

    assert parent.calls == 1  # no re-run after answer text
    streamed = _texts(out, partial=True)
    assert streamed[-1] == "\n\n" + CUT_LINE and streamed.count("\n\n" + CUT_LINE) == 1
    final = out[-1]
    assert not final.partial and final.finish_reason == MAX_TOKENS
    assert final.content.parts[0].text == "".join(streamed)  # the history keeps what the player saw
    assert stats.time_cuts == 1 and stats.budget_retries == 0
    assert any("cut off" in r.getMessage() for r in caplog.records)


async def test_a_progress_line_cut_with_its_tool_call_still_streaming_is_not_a_complete_answer(clock, monkeypatch):
    call_fragment = _llm_response(types.Part(function_call=types.FunctionCall(name="get_deaths", args={})), partial=True)
    parent = Parent(slow_text(clock, ["Let me pull the deaths for fight 3."], then=[call_fragment] * 5)).install(monkeypatch, AnthropicLlm)
    with turn(CLAUDE) as stats:
        out = await _collect(RetryingClaude(model=CLAUDE), _request(CLAUDE))

    assert parent.calls == 1
    final = out[-1]
    assert final.content.parts[0].text == "Let me pull the deaths for fight 3.\n\n" + CUT_LINE
    assert not any(p.function_call for p in final.content.parts)
    assert stats.time_cuts == 1


async def test_a_cut_rerun_after_answer_text_ends_with_the_cut_line(clock, monkeypatch):
    async def thinks():
        for _ in range(5):
            clock["t"] += 50.0
            yield thought("Comparing. ")

    Parent(thinks, slow_text(clock, ["Short ", "answer ", "that ", "runs", " long"])).install(monkeypatch, AnthropicLlm)
    with turn(CLAUDE) as stats:
        out = await _collect(RetryingClaude(model=CLAUDE), _request(CLAUDE))

    assert out[-1].content.parts[0].text.endswith("\n\n" + CUT_LINE)
    assert stats.budget_retries == 1 and stats.time_cuts == 1


async def test_the_turn_stats_line_counts_time_cuts(monkeypatch, caplog):
    class Cut(_Runner):
        async def run_async(self, **kwargs):
            current_turn.get().time_cuts += 1
            yield _event(_text("Half an answer\n\n" + CUT_LINE), final=True)

    caplog.set_level(logging.INFO, logger="backend.app.agent_runner")
    await _run(monkeypatch, Cut([]))
    (line,) = [r.getMessage() for r in caplog.records if r.getMessage().startswith("turn stats")]
    assert "time_cuts=1" in line


# --- BUG-008: whitespace is no answer text ---------------------------------------------------


async def test_a_cut_after_only_whitespace_text_gets_its_rerun(clock, monkeypatch):
    parent = Parent(slow_text(clock, ["\n\n", " ", "\n", " ", "\n"]), answer("The answer.")).install(monkeypatch, AnthropicLlm)
    with turn(CLAUDE) as stats:
        out = await _collect(RetryingClaude(model=CLAUDE), _request(CLAUDE))

    assert parent.calls == 2 and stats.budget_retries == 1 and stats.time_cuts == 0
    assert "The answer." in "".join(_texts(out, partial=False))


# --- BUG-007: a chunk in hand is never dropped -----------------------------------------------


async def test_a_final_response_that_arrives_past_the_bound_is_used_not_rerun(clock, monkeypatch):
    call = types.Part(function_call=types.FunctionCall(id="c1", name="get_deaths", args={"fight": 3}))
    final = _llm_response(call, finish=types.FinishReason.STOP, candidates=7)
    parent = Parent(slow_text(clock, [], step_s=181.0, then=[final])).install(monkeypatch, AnthropicLlm)
    with turn(CLAUDE) as stats:
        out = await _collect(RetryingClaude(model=CLAUDE), _request(CLAUDE))

    assert parent.calls == 1 and stats.budget_retries == 0
    assert out == [final]


# --- PERF-007: only the provider's time counts toward the bound ------------------------------


async def test_time_the_consumer_holds_a_chunk_does_not_count_toward_the_bound(clock, monkeypatch):
    async def fast():
        for chunk in ["One. ", "Two. ", "Three. ", "Four. ", "Five."]:
            clock["t"] += 1.0
            yield _llm_response(types.Part(text=chunk), partial=True)
        yield _llm_response(types.Part(text="One. Two. Three. Four. Five."), finish=types.FinishReason.STOP, candidates=9)

    parent = Parent(fast).install(monkeypatch, AnthropicLlm)
    out = []
    with turn(CLAUDE) as stats:
        async for response in RetryingClaude(model=CLAUDE).generate_content_async(_request(CLAUDE), stream=True):
            out.append(response)
            clock["t"] += 60.0  # a slow client: the runner holds each chunk a minute

    assert parent.calls == 1 and stats.time_cuts == 0 and stats.budget_retries == 0
    assert out[-1].content.parts[0].text == "One. Two. Three. Four. Five."


async def test_a_provider_that_stalls_past_the_bound_is_still_cut(clock, monkeypatch):
    """The bound still holds on the provider's own time, summed over its chunks."""
    parent = Parent(slow_text(clock, [], then=[thought("x")] * 10, step_s=40.0), answer("Low.")).install(monkeypatch, AnthropicLlm)
    with turn(CLAUDE) as stats:
        out = await _collect(RetryingClaude(model=CLAUDE), _request(CLAUDE))
    assert parent.calls == 2 and stats.budget_retries == 1
    assert len([r for r in out if r.partial and r.content.parts[0].thought]) == 5  # 200 s: cut at the next wait


# --- BUG-003: no Gemini empty-STOP re-run once the turn has answer text ---------------------


async def test_an_empty_gemini_stop_after_answer_text_ends_the_call_without_a_rerun(monkeypatch):
    parent = Parent(empty_stop(), answer("repeated")).install(monkeypatch, Gemini)
    with turn(GEMINI) as stats:
        stats.answer_shown = True  # the runner kept answer text (analysis + chart) earlier
        out = await _collect(RetryingGemini(model=GEMINI), _request(GEMINI))

    assert parent.calls == 1 and stats.empty_retries == 0 and stats.model_requests == 0
    assert not out[-1].partial and out[-1].finish_reason == types.FinishReason.STOP  # the held end goes out


async def test_the_runner_marks_answer_text_and_clears_it_when_retracted(monkeypatch):
    seen: list[bool] = []

    class Watching(_Runner):
        async def run_async(self, **kwargs):
            for e in self._events:
                yield e
                seen.append(current_turn.get().answer_shown)  # what the model wrapper would read next

    events = [
        _event(_text("  \n"), partial=True),  # whitespace: no answer (BUG-008)
        _event(_text("Let me check."), partial=True),
        _event(_call("c1")),  # retracted as progress
        _event(_response("c1")),
        _event(_text("x" * 800), partial=True),  # the analysis
        _event(_call("c2")),  # kept: over INTERIM_MAX_CHARS
        _event(_response("c2")),
    ]
    await _run(monkeypatch, Watching(events))
    assert seen == [False, True, False, False, True, True, True]


# --- PERF-001: heavy tool turns still read the stubbed history -------------------------------


def parallel_round(k: int) -> bytes:
    """A Claude response with a thinking block and ``k`` parallel tool calls."""
    events = [
        _message_start(CLAUDE),
        {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "", "signature": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "Plan."}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "sig"}},
        {"type": "content_block_stop", "index": 0},
    ]
    for i in range(1, k + 1):
        events += [
            {"type": "content_block_start", "index": i, "content_block": {"type": "tool_use", "id": f"toolu_{next(_ids)}", "name": "lookup", "input": {}}},
            {"type": "content_block_delta", "index": i, "delta": {"type": "input_json_delta", "partial_json": json.dumps({"n": i})}},
            {"type": "content_block_stop", "index": i},
        ]
    events += [
        {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None}, "usage": {"output_tokens": 5}},
        {"type": "message_stop"},
    ]
    return _sse(*events)


async def test_raid_overview_turns_of_44_blocks_read_the_stubbed_history_every_turn(api):
    """6 rounds of 3 parallel calls with thinking (~44 blocks a turn, over Claude's 20-block
    look-back): from turn 4 on every turn start reads the stubbed history (measure:088a: 0/10 before)."""
    preamble = tenant()
    for t in range(10):
        api.turn += 1
        api.script += [parallel_round(3) for _ in range(6)] + [text_answer(f"Answer {t}.")]
        async for _ in agent_runner.stream_response(CLAUDE, "s-u", f"overview {t}", context_preamble=preamble, user_id="u-1"):
            pass

    for body in api.bodies:
        assert len(breakpoints(body)) <= 4
    rows = simulate(api.bodies)
    starts = [i for i in range(len(rows)) if i == 0 or api.turn_of[i] != api.turn_of[i - 1]]
    head = sum(rows[0]["sizes"][: rows[0]["marks"][1] + 1])
    for t in range(3, 10):
        row, previous = rows[starts[t]], rows[starts[t - 1]]
        boundary = previous["marks"][-2]  # where the previous turn start ended its stubbed history
        assert row["read"] >= sum(row["sizes"][: boundary + 1]) > head
