# Research: Agent Rate-Limit Relief

**Feature**: 011-agent-rate-limit-relief | **Date**: 2026-10-11

All unknowns from the Technical Context are resolved below. Library facts were read from
the installed packages in `.venv` (google-adk 2.10.0, google-genai 2.25.0, anthropic
1.11.0), not from memory.

## R1. Where the retry lives: SDK-native vs. a thin ADK model wrapper

**Decision**: A thin wrapper around the two ADK model classes (`Gemini` and `Claude`)
that owns the retry loop, with the SDKs' own retries turned off. Module:
`wcl_agent/model_retry.py`.

**Rationale**:
- Both SDKs can retry natively: google-genai via `types.HttpRetryOptions(attempts,
  initial_delay, max_delay, exp_base, jitter, http_status_codes)` passed through ADK's
  `Gemini(retry_options=...)`, and the Anthropic SDK via `AsyncAnthropicVertex(max_retries=N)`
  passed as ADK's `Claude(client=...)`. That is the user's "native sdk settings" idea and it
  works, but a native retry is invisible to the application: nothing can emit the
  "busy, retrying" status (FR-003) or count retries (FR-013), and the two SDKs would
  back off on different schedules with no shared wait budget (FR-006).
- ADK exposes `BaseLlm.generate_content_async(llm_request, stream) -> AsyncGenerator
  [LlmResponse]` as the single model-call seam. Overriding it on a subclass gives one
  retry loop for both providers, with a hook to publish retry progress.
- With the wrapper owning the loop, the SDK retries must be disabled (`retry_options`
  unset for Gemini, which is the default; `max_retries=0` on the Anthropic client) so the
  waits do not nest and the budget stays exact.

**Alternatives considered**:
- *Native SDK retries only*: simplest, but fails FR-003/FR-013 and the shared budget.
  Rejected as the sole mechanism; recorded as the fallback if the wrapper proves
  fragile across ADK upgrades.
- *ADK `on_model_error_callback`*: fires when a model call raises and may return a
  replacement `LlmResponse`, but it cannot re-issue the request, so it cannot retry.
  Rejected.
- *Retry at the runner level by re-invoking `runner.run_async`*: would re-send the
  user message into the ADK session (duplicate turn in persisted context). Rejected.

## R2. Classifying a refusal as "rate limited" (FR-002)

**Decision**: `is_rate_limited(exc)` returns true for:
- google-genai `errors.APIError` with `code` 429, or 503 (Vertex "model overloaded"),
  or `status` in {`RESOURCE_EXHAUSTED`, `UNAVAILABLE`};
- Anthropic `RateLimitError` (429) and `OverloadedError` (529), and `APIStatusError`
  with `status_code` in {429, 529, 503}.
Everything else re-raises immediately.

**Rationale**: these are the only transient "try again" conditions; 400/401/403/404 and
500 are not fixed by waiting. The ADK Anthropic adapter re-raises the SDK's own
`RateLimitError` subclass, so isinstance checks on the Anthropic classes hold.

## R3. Backoff schedule and wait hint (FR-001, FR-007)

**Decision**: `RetryPolicy(attempts=5, initial_s=2.0, max_s=30.0, budget_s=90.0,
exp_base=2.0, jitter_s=1.0)` as a frozen dataclass. Delay for attempt *n* (1-based) is
`min(initial_s * exp_base**(n-1), max_s) + uniform(0, jitter_s)`. If the error carries a
`Retry-After` header (Anthropic `exc.response.headers`, genai `exc.response` when present)
that value replaces the computed delay. A retry is only scheduled if the delay fits in
the remaining budget; otherwise the loop stops and raises `ModelRateLimited`.

**Rationale**: matches the spec's defaults; the budget is the user-visible promise
("about 90 seconds at most"). Jitter avoids synchronised retries when two players hit
the limit together (edge case in spec).

## R4. Publishing retry progress to the turn (FR-003)

**Decision**: a `ContextVar[TurnStats | None]` (`current_turn`) set by
`agent_runner.stream_response` for the duration of a turn. `TurnStats` carries a
`notify(record)` callable and the counters. The model wrapper calls
`notify({"type": "model_retry", "attempt": n, "max_attempts": N, "wait_s": d})` before
each sleep. `stream_response` is restructured to pump ADK events into an
`asyncio.Queue` from a producer task, and the wrapper's notifications go into the same
queue, so a retry record is yielded to the WebSocket while the producer is asleep.

**Rationale**: ADK runs model calls and parallel tool calls in tasks spawned from the
turn's task; `ContextVar` values are copied into child tasks, so the wrapper always
finds the right turn. The queue merge is the only way to emit something while the ADK
generator is blocked in a sleep. Cancelling the producer task in the generator's
`finally` also gives the "client disconnected during a retry wait: stop retrying" edge
case for free.

**Alternatives considered**: a logging handler that watches SDK retry logs (fragile,
provider-specific); emitting status via ADK events (the wrapper cannot yield events
while sleeping before its first response). Rejected.

## R5. Counting requests and rounds, and the round cap (FR-011, FR-013)

**Decision**: an ADK `before_model_callback` registered in `build_agent` increments
`TurnStats.model_requests`; `tool_rounds = model_requests - 1`. When `tool_rounds`
reaches `RetryPolicy.round_cap` (default 6), the callback appends a wrap-up instruction
to the request (`llm_request.append_instructions([...])`): answer now with the evidence
gathered, state what was not investigated, do not call more tools. For Gemini it also
sets `config.tool_config.function_calling_config.mode = "NONE"` as a hard stop; the
Anthropic adapter does not map that field, so Claude relies on the instruction.
At the end of `stream_response` the stats are logged once:
`turn stats model=<id> requests=<n> rounds=<n> retries=<n> outcome=<answered|rate_limited|error|abandoned>`.

**Rationale**: `before_model_callback` fires exactly once per model request, so it is the
natural counter and the natural place to steer the last request. `append_instructions`
is ADK's supported way to add system text per request.

## R6. Keeping helper calls out of the retry path (FR-012)

**Decision**: `stream_response(..., retry: bool = True)`. The greeting passes
`retry=False` (its `TurnStats` has `attempts=1`, so the wrapper fails fast and the
greeting's existing "swallow and return empty" handling applies). `generate_followups`
already uses a bare genai client with no retry options and swallows all exceptions, so
it needs no change. Background spec-guide generation keeps the default (retrying is
fine off the user's turn).

## R7. Fewer model requests on broad first questions (FR-008 to FR-010)

**Decision**: prompt-only changes, no tool changes.
- `wcl_agent/agent.py` `INSTRUCTION` gains an `<EVIDENCE_PLAN>` section: for broad
  questions and raid investigations, plan in at most three stages (report-level data in
  one round; per-boss or per-player detail in one parallel round; optional one round of
  cast-level detail only if the question needs it), reuse evidence already in the
  conversation, and answer as soon as the question asked is answerable. The existing
  `<TOOLS>` sentence about parallel calls stays; the new section makes it the default
  shape rather than a hint.
- `backend/app/api/raids.py` `kickoff_prompt_for` asks for a bounded per-boss overview
  (headline finding per boss, biggest improvement opportunity, no cast-level detail
  unless a boss clearly warrants it), replacing the open-ended "investigate and highlight
  any …" wording.
- The round cap (R5) is the backstop for models that ignore the plan.

**Rationale**: the spec forbids removing capability; steering plus a cap is the smallest
change that lowers request counts. Measurement (SC-002) uses the new per-turn log line:
baseline first with the counter alone, then the prompt changes.

## R8. Surfacing the failure to the player (FR-004, FR-005)

**Decision**: the wrapper raises `ModelRateLimited(attempts, waited_s, last_error)`
when the budget is exhausted. `ws.py` catches it before the generic handler, sends
`ErrorFrame(code="rate_limited", message="The model is rate-limited right now. Please
try again in about a minute.")`, and does **not** call `_persist_partial`. The frontend
already renders `error` frames; no UI change beyond the new status label.

## R9. Configuration (FR-006)

**Decision**: five settings on `backend/app/config.py` `Settings`, env-overridable like
the rest: `wcl_model_retry_attempts=5`, `wcl_model_retry_initial_s=2.0`,
`wcl_model_retry_max_s=30.0`, `wcl_model_retry_budget_s=90.0`, `wcl_turn_round_cap=6`.
`agent_runner._get_runner` builds a `RetryPolicy` from them and passes it to
`build_agent(model, retry=policy)`. The CLI (`main.py`) uses the dataclass defaults.
`.env.example` documents them.
