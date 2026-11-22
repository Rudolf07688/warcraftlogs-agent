# Implementation Plan: Model re-runs and the runner

**Branch**: `084-model-reruns` | **Date**: 2026-11-22 | **Spec**: [spec.md](spec.md)

## Summary

One re-run per model call, of one kind: Gemini's empty STOP (sc-586), Claude's thinking-only
cut-off (079) and Claude's new 180 s time cut-off (sc-580). Each re-run counts as a model request
(so as a round toward `round_cap`) and in `budget_retries` / `empty_retries`, both on the turn
stats line. The runner resets a call's thought text when a re-run starts (BUG-005), gives back
retracted text on a pending-call ending (BUG-006), and treats a heading line as a sentence (SPEC L1).

## Technical Context

**Language/Version**: Python 3.14 (uv) | **Primary Dependencies**: google-adk (Gemini, Claude
adapters), anthropic SDK, FastAPI backend | **Storage**: none new | **Testing**: pytest
(asyncio), fake ADK parents and the scripted Anthropic transport of `test_llm_provider_agent`
| **Constraints**: record shapes frozen (contract:chat-status-records); cache layout code is
087's | **Scale**: per call: at most 2 requests of at most 180 s each (Claude, streamed).

## Constitution Check

- Reuse first: extends the 079 re-run in `RetryingClaude` and the `_clock` seam; no new module.
- Simplest design: a deadline wrapper around the parent's stream, one shared "watch" helper for
  both wrappers; no new metric instrument (PO decision:sc-580-metrics).
- Typed boundaries: `TurnStats` gains a typed counter; record dicts unchanged.
- Async: the bound uses `asyncio.timeout` in the calling task (no extra task, context kept).
PASS.

## Design

`wcl_agent/llm/model_retry.py`
- `TurnStats.empty_retries`, `TurnStats.reruns` (budget + empty), `_count_rerun(stats, kind)`:
  bumps the counter and `model_requests`.
- `CLAUDE_CALL_TIMEOUT_S = 180.0`, `ModelCallTimedOut`, `_within(gen, seconds)`: iterates a
  stream under a `_clock` deadline (checked before each chunk, `asyncio.timeout` while waiting),
  always `aclose()`s it.
- `_CallWatch` + `_watch(gen, watch, hold)`: passes responses on, holds back the one `hold`
  matches, notes answer text streamed, a final seen, and a time cut.
- `_empty_stop(response)`: final, STOP, no answer text, no function call, 0/None candidate tokens.
- `RetryingGemini.generate_content_async`: hold an empty stop, re-run once, second outcome stands.
- `RetryingClaude.generate_content_async`: streamed requests run under `_within`; a thinking-only
  cut-off or a time cut with no answer text gets the one low-effort re-run; a time cut after
  text (or a cut re-run) ends with `_cut_response(text)`.

`backend/app/agent_runner.py`
- turn stats line: `budget_retries=%d empty_retries=%d`.
- `_status_line`: heading lines become their own paragraph before the split.
- `_run_turn`: thought reset on `stats.reruns` change; held text restored on a pending-call
  ending.

## Project Structure

Files: `wcl_agent/llm/model_retry.py`, `backend/app/agent_runner.py`,
`backend/tests/test_084_reruns.py` (new), `backend/tests/test_084_runner_edges.py` (new).
`wcl_agent/agent.py` untouched (the planner block needs no change: the bound is not an effort cap).

## Complexity Tracking

None.
