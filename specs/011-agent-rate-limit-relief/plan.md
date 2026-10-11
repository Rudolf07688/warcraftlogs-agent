# Implementation Plan: Agent Rate-Limit Relief

**Branch**: `011-agent-rate-limit-relief` | **Date**: 2026-10-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/011-agent-rate-limit-relief/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Broad first questions and the one-click raid investigation make the agent do many
lookup rounds, each another model request, which exhausts the provider's per-minute
allowance; today that aborts the turn with a raw error. The fix has two halves:
(1) a thin retry wrapper around the two ADK model classes that waits with bounded
exponential backoff on rate-limit refusals, publishes "retrying" progress to the
WebSocket, and fails with a plain-language error when the budget is spent; and (2) fewer
requests in the first place via an evidence-plan section in the agent instruction, a
bounded raid-kickoff prompt, and a per-turn lookup-round cap enforced from an ADK
`before_model_callback`. Helper calls (greeting, follow-ups) never retry. A per-turn
stats line in the logs is the measurement source. No schema, auth or tool changes.

## Technical Context

**Language/Version**: Python 3.14 (backend, agent); TypeScript / React 19 (frontend status label only)

**Primary Dependencies**: google-adk 2.10.0 (`BaseLlm`, `Gemini`, `Claude`, `before_model_callback`, `LlmRequest.append_instructions`), google-genai 2.25.0 (`errors.APIError`), anthropic 1.11.0 (`RateLimitError`, `OverloadedError`, `AsyncAnthropicVertex(max_retries=0)`), FastAPI WebSocket layer, pydantic / pydantic-settings

**Storage**: N/A (no DB change; `TurnStats` is in-memory, logged once)

**Testing**: pytest + pytest-asyncio (`asyncio_mode=auto`), httpx `ASGITransport`; fake `BaseLlm` subclasses and the existing synthetic-ADK-event fakes in `backend/tests/test_grounding.py`; `tsc -b` for the frontend

**Target Platform**: Linux containers via docker compose (backend + Vite dev server)

**Project Type**: web application (FastAPI backend + ADK agent package + React frontend)

**Performance Goals**: a rate-limited turn survives refusals of up to ~30 s with zero errors (SC-001); "retrying" status visible within 2 s of the first refusal (SC-004); median model requests for the raid kickoff down ≥ 1/3 (SC-002)

**Constraints**: retry only on rate-limit / overloaded refusals (FR-002); total wait per model request ≤ configured budget (default 90 s); no retry before any response chunk has been consumed (a mid-stream failure re-raises to avoid duplicated text); helper calls fail fast; short questions unchanged (FR-014)

**Scale/Scope**: single process, a handful of concurrent players; ~6 backend files touched, 1 new module, 2 frontend files, 2 new test files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|---|---|---|
| I. Strict DRY & Reuse-First | PASS | One retry loop for both providers (`wcl_agent/model_retry.py`); classification, delay and stats live there and are imported by `agent.py`, `agent_runner.py`, `ws.py`. Reuses ADK's `append_instructions`, the existing `ErrorFrame`, the existing status line and `toolLabels.ts`. No parallel retry in the frontend. |
| II. Methodical, Step-Wise Delivery | PASS | Ordered slices: policy + wrapper + tests → runner queue merge + stats log → WS/frontend status → helper opt-out → prompt steering + round cap → config + docs. Baseline measurement is taken after the counter lands and before the prompt change. |
| III. Simplicity First (YAGNI) | PASS | No new service, queue system or persistence. One ContextVar, one dataclass, one frame type. SDK-native retry was evaluated (research R1) and rejected only because it cannot satisfy FR-003/FR-013. No Complexity Tracking entries needed. |
| IV. Typed Data Contracts | PASS | `RetryPolicy`, `TurnStats` are dataclasses (internal); `ModelRetryFrame` is a Pydantic model (boundary); settings are pydantic-settings fields. |
| V. Async Python Backend | PASS | Retry sleeps are `asyncio.sleep`; the queue merge keeps the WS handler non-blocking; no blocking calls added. |
| VI. Repo Awareness via GitNexus | PASS (with CRITICAL-risk warning) | `impact --direction upstream` run during planning: `stream_response` **CRITICAL** (3 direct callers, 7 processes), `build_agent` **CRITICAL** (2 direct, 5 processes), `_get_runner` **CRITICAL** (1 direct, 6 processes), `kickoff_prompt_for` LOW (1 caller, `investigate_raid`). Affected processes: `_handle_turn`/`chat` (ws), `greeting`, `lifespan` (greeting prime), `_run_spec_guide`, `ensure_spec_guide`, `schedule_guild_summary` (services/guide). Mitigation: every signature change is additive and keyword-only with today's behaviour as default (`stream_response(..., retry=True)`, `build_agent(model, retry=None)`), record shapes yielded by `stream_response` are unchanged (new `model_retry` record is additive), and the full suite plus `test_grounding.py` / `test_parallel_tools.py` guard the restructure. The index is 1 commit behind HEAD: re-run `analyze` before implementation, re-run `impact` before each edit, `detect_changes` before each commit. |

**Post-design re-check (Phase 1)**: unchanged, all PASS. The only design-time addition
was the producer-task/queue restructure of `stream_response` (research R4), which is
the minimum needed to emit a frame while ADK is asleep and also simplifies the
disconnect-during-retry edge case.

## Project Structure

### Documentation (this feature)

```text
specs/011-agent-rate-limit-relief/
├── plan.md              # This file
├── spec.md
├── research.md          # Phase 0: R1–R9 decisions
├── data-model.md        # Phase 1: RetryPolicy, TurnStats, ModelRateLimited, ModelRetryFrame
├── quickstart.md        # Phase 1: run + verify each story, measurement procedure
├── contracts/
│   └── websocket-and-config.md   # model_retry frame, rate_limited error, env vars, log line
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
wcl_agent/
├── model_retry.py       # NEW: RetryPolicy, TurnStats, current_turn ContextVar,
│                        #      ModelRateLimited, is_rate_limited(), RetryingGemini,
│                        #      RetryingClaude, before_model_callback factory (count + cap)
└── agent.py             # build_agent(model, retry: RetryPolicy | None): wraps the model,
                         #   registers the callback; INSTRUCTION gains <EVIDENCE_PLAN>

backend/app/
├── agent_runner.py      # stream_response(..., retry=True): TurnStats in ContextVar,
│                        #   producer task + asyncio.Queue merge, outcome + "turn stats" log
├── api/ws.py            # forward model_retry records; catch ModelRateLimited →
│                        #   ErrorFrame(code="rate_limited"), no partial persist
├── api/raids.py         # kickoff_prompt_for(): bounded per-boss overview wording
├── greeting.py          # stream_response(..., retry=False)
├── schemas.py           # ModelRetryFrame
└── config.py            # wcl_model_retry_* and wcl_turn_round_cap settings

frontend/src/
├── api/wsClient.ts      # Frame union: model_retry
├── toolLabels.ts        # retryLabel(attempt, max)
└── App.tsx              # case "model_retry": setStatus(retryLabel(...))

backend/tests/
├── test_model_retry.py  # NEW: classification, delay/budget/hint, wrapper retry paths,
│                        #      callback counting + cap, TurnStats outcomes
├── test_runner_retry.py # NEW: stream_response yields model_retry records while the fake
│                        #      runner sleeps; cancellation stops retries; stats log line
└── test_ws_*.py         # extend existing WS tests: rate_limited error frame, no partial

.env.example             # document the five new variables
```

**Structure Decision**: web application layout already in place (backend / wcl_agent /
frontend). Retry mechanics live in `wcl_agent` because `build_agent` is shared by the
backend and the CLI; the backend owns configuration, the WebSocket contract and the
per-turn stats log.

## Design Notes (from research)

1. **Model wrapper** (R1–R3): `RetryingGemini(Gemini)` and `RetryingClaude(Claude)`
   override `generate_content_async`. Loop: attempt the underlying generator; if an
   exception passes `is_rate_limited` and nothing has been yielded yet and attempts
   remain and the next delay fits the budget, `notify(model_retry)`, `asyncio.sleep`,
   increment `TurnStats.retries`, retry; otherwise raise `ModelRateLimited` (budget
   spent) or re-raise (not a rate limit, or mid-stream). `RetryingClaude` constructs
   `AsyncAnthropicVertex(..., max_retries=0)` so the SDK does not nest its own waits;
   `RetryingGemini` leaves `retry_options` unset (no SDK retry).
2. **Turn plumbing** (R4): `stream_response` creates `TurnStats`, sets `current_turn`,
   runs the ADK iteration in a producer task that pushes records into an
   `asyncio.Queue`; `notify` pushes into the same queue; the generator drains the queue
   until a sentinel. `finally`: cancel the producer if still running (client went
   away → outcome `abandoned`), log the stats line, reset the ContextVar.
3. **Counting and cap** (R5): the `before_model_callback` reads `current_turn`; absent
   (CLI, tests) it is a no-op. On cap: `append_instructions([WRAP_UP_INSTRUCTION])` and,
   for Gemini, function-calling mode `NONE`.
4. **Helper opt-out** (R6): `retry=False` → `TurnStats.retry_enabled=False` → the
   wrapper treats attempts as 1. `generate_followups` unchanged.
5. **Steering** (R7): `<EVIDENCE_PLAN>` in `INSTRUCTION`; kickoff wording in
   `raids.py`. Both are text-only edits with existing tests to extend
   (`test_prompt_contract.py` asserts instruction sections).
6. **Failure surface** (R8): `ws.py` `except ModelRateLimited` before the generic
   handler; `ErrorFrame(code="rate_limited", ...)`; skip `_persist_partial`.
7. **Config** (R9): settings → `RetryPolicy` in `_get_runner`; runners are cached per
   model, so a policy change needs a restart (documented).

## Risks and mitigations

- **Three CRITICAL-risk hub symbols are edited** (`stream_response`, `build_agent`,
  `_get_runner`; see Constitution Check VI). They feed the chat turn, the greeting, the
  startup greeting prime, and background spec-guide / guild-summary generation. All
  changes are additive with defaults preserving current behaviour; the background guide
  jobs keep `retry=True` (a retry off the user's turn is harmless) and only the greeting
  opts out. Verification order: unit tests on the wrapper → runner tests with the fake
  runner → full suite → manual quickstart steps.

- **ADK internals drift** (`generate_content_async` signature, `Claude` client field):
  pinned versions in `uv.lock`; the wrapper is ~60 lines and `test_model_retry.py`
  drives it with a fake `BaseLlm`, so a break is caught by tests, not in production.
  Fallback recorded in research R1 (native SDK retries without status).
- **Mid-stream rate limit**: not retried (would duplicate streamed text); surfaces as
  `rate_limited` only if no chunk was consumed, else as `agent_error`. Rare for the
  answer request; acceptable and documented.
- **Prompt steering is probabilistic**: the round cap is the deterministic backstop;
  SC-002 is measured, not assumed, via the stats log.
- **Queue restructure of `stream_response`**: the existing synthetic-event tests
  (`test_grounding.py`, `test_parallel_tools.py`) must pass unchanged; they are the
  regression net for the producer/queue change.

## Complexity Tracking

No constitution violations; table intentionally empty.
