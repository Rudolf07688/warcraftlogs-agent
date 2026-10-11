# Quickstart: Agent Rate-Limit Relief

**Feature**: 011-agent-rate-limit-relief | **Date**: 2026-10-11

## Run

```bash
docker compose up --build          # or: uv run uvicorn backend.app.main:app --reload
```

Optional overrides in `.env` (defaults shown):

```
WCL_MODEL_RETRY_ATTEMPTS=5
WCL_MODEL_RETRY_INITIAL_S=2.0
WCL_MODEL_RETRY_MAX_S=30.0
WCL_MODEL_RETRY_BUDGET_S=90.0
WCL_TURN_ROUND_CAP=6
```

## Verify US1 — a rate-limited turn recovers

1. Set a tiny budget to make the behaviour easy to observe without a real limit:
   `WCL_MODEL_RETRY_ATTEMPTS=3 WCL_MODEL_RETRY_INITIAL_S=5`.
2. Run the unit tests that drive the wrapper with a fake model raising 429 twice:
   `uv run pytest backend/tests/test_model_retry.py -q`.
3. In the browser, trigger a real limit by sending several broad questions quickly on
   the default model. Expect the status line to read "Model busy — retrying (1 of 5)…"
   and the answer to arrive afterwards with no error.
4. Force exhaustion (`WCL_MODEL_RETRY_ATTEMPTS=1`) and hit the limit again: expect the
   red message "The model is rate-limited right now. Please try again in about a
   minute.", the composer re-enabled, and the conversation still usable. Reload: no
   half-written agent reply is in the history.

## Verify US2 — fewer requests on the raid kickoff (SC-002)

Measurement uses the per-turn log line. Do the baseline **before** applying the
prompt changes (the counter lands first):

```bash
docker compose logs -f backend | grep "turn stats"
```

1. Pick three tracked reports. For each, on each supported model, click
   "investigate" and note `requests=` from the log line. Record the median.
2. Apply the prompt and kickoff changes, repeat. Target: median down by ≥ 1/3, same
   bosses and headline findings in the answer.
3. Ask a one-lookup question ("what's the kill time on boss X in report Y?") and
   confirm `requests=2` (one call plus one round), unchanged from before (SC-006).

## Verify US3 — helper calls step aside

1. With `WCL_MODEL_RETRY_ATTEMPTS=1` and a provider limit active, open a new chat:
   it opens empty, no error. Send a message whose answer completes: it renders with
   no follow-up chips and no error.
2. Unit tests: `uv run pytest backend/tests/test_greeting.py backend/tests/test_suggestions.py -q`.

## Full checks

```bash
uv run pytest -q
cd frontend && npx tsc -b
```
