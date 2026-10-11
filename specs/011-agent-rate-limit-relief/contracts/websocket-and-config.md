# Contracts: Agent Rate-Limit Relief

**Feature**: 011-agent-rate-limit-relief | **Date**: 2026-10-11

## 1. WebSocket stream (`/ws`) — additive frames

### New frame: `model_retry`

Sent by the server zero or more times during a turn, each time immediately before the
backend sleeps ahead of a rate-limit retry.

```json
{ "type": "model_retry", "attempt": 2, "max_attempts": 5, "wait_s": 4.3 }
```

- `attempt`: 1-based index of the retry about to be made.
- `max_attempts`: configured ceiling, so the client can show "2 of 5".
- `wait_s`: seconds the server is about to wait.

Ordering: may appear between any two existing frames of a turn (after `meta`, before
`done`/`error`). Never appears after `done` or `error`. Clients that do not recognise it
must ignore it.

Client behaviour (reference implementation, `App.tsx`): set the in-turn status line to
the retry label (`toolLabels.ts: retryLabel(attempt, max)`); the next `tool_start`,
`token` or terminal frame replaces it as today.

### Existing frame: `error` — new `code`

```json
{ "type": "error", "code": "rate_limited",
  "message": "The model is rate-limited right now. Please try again in about a minute." }
```

Emitted when the retry budget is exhausted. Guarantees:
- no `token` frames were emitted after the last `model_retry` for this turn;
- no partial agent message is persisted for the turn (the user message is);
- the socket stays open and the next user message is processed normally.

All other failures keep `code="agent_error"` and today's behaviour.

## 2. Operator configuration (environment / `.env`)

| Variable | Default | Meaning |
|---|---|---|
| `WCL_MODEL_RETRY_ATTEMPTS` | `5` | attempts per model request, including the first |
| `WCL_MODEL_RETRY_INITIAL_S` | `2.0` | first retry delay |
| `WCL_MODEL_RETRY_MAX_S` | `30.0` | delay ceiling |
| `WCL_MODEL_RETRY_BUDGET_S` | `90.0` | total wait per model request before giving up |
| `WCL_TURN_ROUND_CAP` | `6` | lookup rounds before the wrap-up instruction |

Read by `backend/app/config.py` (pydantic-settings, same prefixing as existing
`WCL_*` keys) and documented in `.env.example`.

## 3. Operator log line (per turn)

One `INFO` record at the end of every turn, from `backend.app.agent_runner`:

```
turn stats model=gemini-3.6-flash requests=4 rounds=3 retries=1 waited_s=4.3 outcome=answered
```

`outcome` ∈ `answered | rate_limited | error | abandoned`. This is the measurement
source for SC-002 and SC-005.

## 4. Agent kickoff wording (server-owned)

`GET/POST /api/raids/{code}/investigate` still returns `kickoff_prompt`; its wording
changes to a bounded per-boss overview request. The field name, type and the
"client sends it as a normal first turn" flow are unchanged.
