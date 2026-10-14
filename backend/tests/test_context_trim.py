"""PERF-004: large tool results from older turns are stubbed in the model request only."""

from __future__ import annotations

import copy

from google.adk.models.llm_request import LlmRequest
from google.genai import types

from wcl_agent.context_trim import (
    ELIDED_NOTE,
    compact_tool_response,
    trim_old_tool_results,
    user_turn_indices,
)
from wcl_agent.model_retry import RetryPolicy, TurnStats, current_turn, make_before_model_callback


def _big_result(tag: str) -> dict:
    return {
        "status": "success",
        "title": f"Report {tag}",
        "rows": [{"name": f"P{i}", "amount": i * 1000} for i in range(200)],
        "provenance": {"report_code": tag, "fight_id": 3},
        "completeness": {"has_more": False, "sample_size": 200},
    }


def _turn(tag: str, result: dict) -> list[types.Content]:
    return [
        types.Content(role="user", parts=[types.Part(text=f"question {tag}")]),
        types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(id=f"c{tag}", name="get_report_table", args={}))],
        ),
        types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=f"c{tag}", name="get_report_table", response=result
                    )
                )
            ],
        ),
        types.Content(role="model", parts=[types.Part(text=f"answer {tag}")]),
    ]


def _history() -> list[types.Content]:
    return _turn("A", _big_result("A")) + _turn("B", _big_result("B")) + _turn("C", _big_result("C"))


def _response(content: types.Content) -> dict:
    return content.parts[0].function_response.response


def test_only_turns_older_than_keep_are_stubbed():
    history = _history()
    request = LlmRequest(contents=list(history))

    replaced = trim_old_tool_results(request, keep=2, min_chars=1500)

    assert replaced == 1
    assert _response(request.contents[2])["_elided"] is True  # turn A: stubbed
    assert request.contents[6] is history[6]  # turn B (previous): untouched
    assert request.contents[10] is history[10]  # turn C (current): untouched


def test_stored_history_is_never_mutated():
    history = _history()
    snapshot = copy.deepcopy([c.model_dump() for c in history])
    original_content, original_response = history[2], _response(history[2])

    trim_old_tool_results(LlmRequest(contents=list(history)), keep=2, min_chars=1500)

    assert history[2] is original_content
    assert _response(history[2]) is original_response
    assert [c.model_dump() for c in history] == snapshot


def test_small_results_are_kept_and_short_histories_untouched():
    small = {"status": "success", "value": 1}
    history = _turn("A", small) + _turn("B", small) + _turn("C", small)
    request = LlmRequest(contents=list(history))
    assert trim_old_tool_results(request, keep=2, min_chars=1500) == 0
    assert request.contents == history

    two_turns = _turn("A", _big_result("A")) + _turn("B", _big_result("B"))
    assert trim_old_tool_results(LlmRequest(contents=two_turns), keep=2, min_chars=1500) == 0


def test_stub_keeps_the_evidence_envelope_and_is_deterministic():
    result = _big_result("A")
    stub = compact_tool_response(result)
    assert stub["status"] == "success"
    assert stub["provenance"] == {"report_code": "A", "fight_id": 3}
    assert stub["completeness"] == {"has_more": False, "sample_size": 200}
    assert stub["title"] == "Report A" and stub["rows_count"] == 200 and "rows" not in stub
    assert stub["_elided"] is True and stub["_note"] == ELIDED_NOTE
    assert len(stub["_preview"]) <= 600
    assert compact_tool_response(copy.deepcopy(result)) == stub  # same input, same stub


def test_turn_boundaries_ignore_tool_results():
    assert user_turn_indices(_history()) == [0, 4, 8]


def test_callback_trims_then_injects_the_preamble():
    callback = make_before_model_callback(RetryPolicy())
    stats = TurnStats(model="gemini-3.6-flash", preamble="CTX")
    token = current_turn.set(stats)
    try:
        request = LlmRequest(contents=_history())
        callback(None, request)
    finally:
        current_turn.reset(token)
    assert _response(request.contents[2])["_elided"] is True
    assert request.contents[8].parts[0].text == "CTX\n\n"  # the current turn's question
    assert stats.trimmed_results == 1


def test_callback_trims_without_a_turn_too():
    request = LlmRequest(contents=_history())
    make_before_model_callback(RetryPolicy())(None, request)  # CLI path: no TurnStats
    assert _response(request.contents[2])["_elided"] is True


def test_turn_stats_records_cached_tokens():
    stats = TurnStats(model="m")
    stats.record_prompt_tokens(5000, 3000)
    assert (stats.last_prompt_tokens, stats.last_cached_tokens) == (5000, 3000)
