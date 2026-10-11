# Data Model: Agent Rate-Limit Relief

**Feature**: 011-agent-rate-limit-relief | **Date**: 2026-10-11

No database change. Three in-process value objects and one new WebSocket frame.

## RetryPolicy (frozen dataclass, `wcl_agent/model_retry.py`)

Operator configuration for one process (FR-006). Built once per runner from
`Settings`; the CLI uses the defaults.

| Field | Type | Default | Rule |
|---|---|---|---|
| `attempts` | int | 5 | ≥ 1; `1` means no retry (used by the greeting) |
| `initial_s` | float | 2.0 | > 0 |
| `max_s` | float | 30.0 | ≥ `initial_s` |
| `budget_s` | float | 90.0 | total wall-clock the loop may spend waiting per request |
| `exp_base` | float | 2.0 | ≥ 1 |
| `jitter_s` | float | 1.0 | ≥ 0 |
| `round_cap` | int | 6 | ≥ 1; lookup rounds allowed before the wrap-up instruction |

Methods: `delay_for(attempt: int, hint_s: float | None) -> float` (R3).

## TurnStats (dataclass, `wcl_agent/model_retry.py`)

Per-turn tally and signal channel (FR-013). Created by `stream_response`, installed in
the `current_turn` ContextVar for the duration of the turn, logged once at the end.

| Field | Type | Meaning |
|---|---|---|
| `model` | str | model id of the turn |
| `model_requests` | int | model calls started this turn (incremented by `before_model_callback`) |
| `retries` | int | rate-limit retries performed this turn |
| `waited_s` | float | total time spent in retry sleeps |
| `outcome` | `"answered" \| "rate_limited" \| "error" \| "abandoned"` | set by `stream_response` on exit |
| `retry_enabled` | bool | false for helper calls (greeting) |
| `notify` | `Callable[[dict], None]` | pushes a record into the turn's output queue |

Derived: `tool_rounds = max(model_requests - 1, 0)`; `cap_reached = tool_rounds >= policy.round_cap`.

State transitions for `outcome`: `None → answered` (generator completed), `None →
rate_limited` (`ModelRateLimited` raised), `None → error` (any other exception),
`None → abandoned` (consumer cancelled the generator, e.g. WebSocket disconnect).

## ModelRateLimited (exception, `wcl_agent/model_retry.py`)

Raised by the model wrapper when the budget is exhausted (FR-004).

| Field | Type |
|---|---|
| `attempts` | int |
| `waited_s` | float |
| `last_error` | BaseException |

## ModelRetryFrame (Pydantic, `backend/app/schemas.py`)

Streamed to the client before each retry sleep (FR-003). Additive; older clients ignore
unknown frame types.

| Field | Type | Meaning |
|---|---|---|
| `type` | `Literal["model_retry"]` | |
| `attempt` | int | the retry about to be made (1-based) |
| `max_attempts` | int | `RetryPolicy.attempts` |
| `wait_s` | float | the sleep about to happen, rounded to 0.1 s |

Frontend mirror: `Frame` union in `frontend/src/api/wsClient.ts` gains
`{ type: "model_retry"; attempt: number; max_attempts: number; wait_s: number }`.

## ErrorFrame (existing) — new code

`code="rate_limited"` with the fixed plain-language message (FR-004). No schema change.
