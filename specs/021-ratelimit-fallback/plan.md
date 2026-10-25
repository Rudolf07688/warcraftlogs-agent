# Implementation Plan: Rate-Limit Fallback to the Sibling Model

**Branch**: `021-ratelimit-fallback` | **Date**: 2026-10-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/021-ratelimit-fallback/spec.md`

## Summary

When a chat turn's model is still rate limited after the feature 011 retries, the turn
continues on the other served model of the same class. The fallback is per request,
inside the two ADK model wrappers. When a request raises `ModelRateLimited` (raised
only when nothing streamed), the wrapper points `llm_request.model` at the sibling and
runs the same request again. ADK reads the model id from the request on both providers
(research R2), so nothing else changes. The turn's `TurnStats` holds the sibling and
whether the switch was used. That allows exactly one switch, and routes the turn's later
requests to the sibling. Only the chat socket sets a sibling, which a pure
`sibling_model()` computes from the served set. Every helper path keeps today's
behaviour. A new typed `model_fallback` frame drives a status line and a note under the
reply. No database, dependency or migration change. `generate_with_retry` and
`make_before_model_callback` are untouched.

## Technical Context

**Language/Version**: Python 3.14 (backend, agent); TypeScript / React 19 (frontend notice)

**Primary Dependencies**: google-adk 2.10.0 (`Gemini`, `Claude`, `LlmRequest`), google-genai
(`errors.APIError`, `types.Part.thought_signature`), anthropic (`RateLimitError`), FastAPI
WebSocket layer, pydantic

**Storage**: N/A (per-turn, in memory; the notice is not persisted, Q1 = A)

**Testing**: pytest + pytest-asyncio (`asyncio_mode=auto`); fake genai and Anthropic clients
injected through the ADK models' `client` field, so the real ADK request path runs up to the
client call; the existing `_FakeSocket` + SQLite `as_user` pattern from
`test_ws_rate_limit.py`; `npm run build` for the frontend

**Target Platform**: Linux containers (backend + Vite dev server)

**Project Type**: web application (FastAPI backend + ADK agent package + React frontend)

**Performance Goals**: no added latency on the happy path (one attribute check per request);
a switch costs no extra wait beyond the retries already spent on the original model

**Constraints**: switch only before anything of the failing request was yielded; at most
one switch per turn; helper calls never switch; existing retry/runner/ws/greeting/guide
tests unchanged and green (scrum master condition)

**Scale/Scope**: 5 backend files edited (+1 held by 022), 2 new test files, 4 frontend
files (3 held by 022 or needing a product owner exception), 1 line in ai_guide

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|---|---|---|
| I. Strict DRY & Reuse-First | PASS | Reuses `generate_with_retry` unchanged for both the original and the sibling attempt, `ModelRateLimited`, `TurnStats.emit`, the `current_turn` ContextVar, the discovery regexes (`_GEMINI_RE` / `_CLAUDE_RE`) for classification, `model_state.get_model_state` for the served set, `RATE_LIMITED_MESSAGE`, and `user_turn_indices` (context_trim) to find the current turn. The frontend note reuses the existing note pattern under agent replies. One fallback helper serves both wrappers. |
| II. Methodical, Step-Wise Delivery | PASS | Slices: (1) `sibling_model` + tests; (2) `TurnStats` fields + `generate_with_fallback` + wrapper wiring + Gemini/Claude fake-client tests; (3) runner keyword + stats log; (4) ws plumbing + frame (after the `schemas.py` grant) + ws tests; (5) frontend notice (after the grants). Each slice runs the full pytest suite. |
| III. Simplicity First (YAGNI) | PASS | No new module, setting, service or persistence. A per-request switch instead of a turn re-run avoids session surgery (research R1). The thought-signature guard (R5) is about 15 lines and protects the one moment the feature exists for; it is recorded in Complexity Tracking. |
| IV. Typed Data Contracts | PASS | `ModelFallbackFrame` (Pydantic) at the socket boundary; `TurnStats` stays a dataclass; the frontend `Frame` union and `Message` get typed members. |
| V. Async Python Backend | PASS | No blocking work added; the switch reuses the async retry loop. |
| VI. Repo Awareness via GitNexus | PASS (CRITICAL/HIGH warnings accepted with mitigations) | Worktree re-indexed with `--force` at cc3c783. `stream_response` **CRITICAL** (callers `ws._handle_turn`, `greeting._generate_greeting`, `services/guide._stream_text`, `evals/guides/coaching.run_case`): only a keyword-only `fallback_model=None` is added. `generate_with_retry` **CRITICAL** (`conversation_titles.generate_title`, `guide_pipeline/llm._generate`, both wrappers): **not changed**. `make_before_model_callback` **HIGH** (`build_agent`): **not changed**. `RetryingGemini`/`RetryingClaude`/`TurnStats` MEDIUM: defaulted fields only, and the wrapper bodies delegate to a new helper. `_handle_turn` LOW. Scrum master accepted these on condition that `test_model_retry`, `test_runner_retry`, `test_ws_rate_limit`, the greeting and the guide tests are unchanged and green. `impact` re-run before each edit, `detect_changes` before each commit. |
| VII. shadcn/ui via MCP | PASS (search at implementation) | The only UI is a one-line note under an agent reply. The registry will be searched (badge / alert / item) through the MCP before writing it. The expected outcome is to reuse the existing `grounding-note` markup, because a registry Badge or Alert would look different from the "Used web search" and "Interrupted" notes beside it. If so, that reason is recorded here at implementation. |
| VIII. Backlog Sync | PASS | sc-164 is In Progress; it moves to Under Review only on the scrum master's word. No `todo.md` edit (scrum master owns it). |

**Post-design re-check (Phase 1)**: unchanged, all PASS.

## Design

### 1. Sibling (`wcl_agent/llm/models.py`, `backend/app/model_state.py`)

- `model_class(model_id) -> tuple[str, str] | None` and
  `sibling_model(model, served) -> str | None` (data-model.md). Pure; no I/O.
- `class_label(model_id) -> str | None`: "Gemini flash" / "Claude sonnet", for the
  "Both <class> models …" message.
- `model_state.fallback_model_for(app, model) -> str | None`:
  `sibling_model(model, get_model_state(app)[0])`.

### 2. Per-request fallback (`wcl_agent/llm/model_retry.py`)

- `TurnStats`: `fallback_model`, `switched_to`, `switch_index` (all default `None`).
- New `generate_with_fallback(inner, llm_request, policy)`:
  1. `stats = current_turn.get()`; `own = stats is not None and llm_request.model == stats.model`.
  2. If `own` and `stats.switched_to`, route the request: set `llm_request.model` to the
     sibling and clear foreign Gemini signatures (step 5) before the first attempt.
  3. `async for r in generate_with_retry(inner, policy): yield r`, then return.
  4. On `ModelRateLimited`: re-raise unless `own`, `stats.fallback_model` is set and
     `stats.switched_to is None`. Otherwise set `switched_to` and `switch_index`, log a
     warning, `stats.emit({"type": "model_fallback", "from_model", "to_model"})`, route
     the request, and run `generate_with_retry` again. Its `ModelRateLimited` propagates.
  5. Routing to a Gemini sibling replaces `thought_signature` on parts in
     `contents[turn_start:switch_index]` (where `turn_start = user_turn_indices(contents)[-1]`)
     with `b"skip_thought_signature_validator"`, on new `Content`/`Part` copies (research
     R5). Claude requests are left as they are.
- `RetryingGemini.generate_content_async` and `RetryingClaude.generate_content_async`
  call `generate_with_fallback(lambda: super(...).generate_content_async(llm_request, stream), llm_request, self.policy)`
  in place of `generate_with_retry(...)`. The lambda reads `llm_request.model` per attempt
  (research R2: `google_llm.py:241,297-298,354-355`; `anthropic_llm.py:1022,1119-1122,1158-1164`).
- `generate_with_retry` and `make_before_model_callback` are not edited. The callback runs
  once per request before the wrapper, so a switched request is counted once and keeps
  the preamble that was already injected.

### 3. Runner (`backend/app/agent_runner.py`)

- `stream_response(..., fallback_model: str | None = None)` (keyword-only) passes it to
  `TurnStats`. The docstring adds the `model_fallback` record.
- The turn stats line appends `fallback=<switched_to or ->`. It goes at the end, so the
  substrings that existing tests assert are unchanged.

### 4. Socket (`backend/app/api/ws.py`, `backend/app/schemas.py`)

- `chat()` computes `fallback_model_for(ws.app, turn.model)` next to `is_valid_model` and
  passes it through `_start_turn(..., fallback_model=)` into
  `_handle_turn(..., fallback_model=None)` and on to `stream_response`. Existing tests
  that call `_handle_turn(sock, turn, identity)` keep working.
- Forward `kind == "model_fallback"` as `ModelFallbackFrame(**record)`, and remember
  that this turn switched (a local flag set from the record).
- Rate-limited branch (Q4, product owner split): no partial is persisted, as today. The
  message is `RATE_LIMITED_MESSAGE` (feature 011, unchanged) when the turn did not switch,
  and `BOTH_RATE_LIMITED_MESSAGE.format(label=class_label(turn.model))` ("Both Gemini
  flash models are rate-limited right now. Please try again in about a minute.") when it
  did. Both keep the code `rate_limited`, since the frontend shows `error.message` as is
  and needs no distinction. The flag comes from the record the socket already sees, so
  `ModelRateLimited` and the runner stay unchanged.
- The title hook, suggestions and `DoneFrame` are untouched.

### 5. Frontend

- `api/wsClient.ts`: `| { type: "model_fallback"; from_model: string; to_model: string }`.
- `types.ts`: `Message.fallback?: { from: string; to: string }`.
- `toolLabels.ts`: `fallbackLabel(from, to)` next to `retryLabel` (the status text).
- `App.tsx`: a `pendingFallbackRef`. On the frame, set the status to `fallbackLabel` and
  remember it. On `done`, attach it to the agent message. Reset it on `done` and `error`.
- `components/MessageList.tsx`: a note under the agent reply when `m.fallback` is set:
  "Answered by X (Y was rate-limited)", in the same markup as the "Used web search" note.

## File list (ownership request)

| File | Change | Ownership |
|---|---|---|
| `wcl_agent/llm/models.py` | `model_class`, `sibling_model`, `class_label` | tentative grant (021) |
| `wcl_agent/llm/model_retry.py` | `TurnStats` fields, `generate_with_fallback`, signature guard, wrapper bodies | tentative grant (021) |
| `backend/app/model_state.py` | `fallback_model_for` | tentative grant (021) |
| `backend/app/agent_runner.py` | `fallback_model` keyword, stats line | tentative grant (021) |
| `backend/app/api/ws.py` | plumb `fallback_model`, forward frame, split rate-limit message | tentative grant (021) |
| `backend/app/schemas.py` | append `ModelFallbackFrame` | **held by 022**, needed for slice 4 |
| `backend/tests/test_model_fallback.py` (new) | sibling, wrappers (Gemini + Anthropic fake clients), runner | new |
| `backend/tests/test_model_fallback_ws.py` (new) | socket: frame forwarded, one stored reply, both rate-limit messages, next turn works | new |
| `backend/tests/test_model_fallback_history.py` (new) | SC-007: a real ADK `Runner` + `InMemorySessionService` + `RetryingGemini` over a fake client: tool round on A, 429, switch to B; session events hold the turn exactly once | new |
| `frontend/src/api/wsClient.ts` | `Frame` member | tentative grant (021) |
| `frontend/src/types.ts` | `Message.fallback` | **held by 022** |
| `frontend/src/App.tsx` | frame handler, attach on done | **held by 022** |
| `frontend/src/components/MessageList.tsx` | the note | allowed by the product owner (granted with this list) |
| `frontend/src/toolLabels.ts` | `fallbackLabel` | unlisted, request |
| `documentation/ai_guide.md` | one line at the `model_retry.py` entry (line 111) | request (1 line) |
| `specs/021-ratelimit-fallback/**` | spec artifacts | 021 |

No `pyproject.toml`/lockfile change and no migration.

## Project Structure

### Documentation (this feature)

```text
specs/021-ratelimit-fallback/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/websocket-model-fallback.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
wcl_agent/llm/
├── model_retry.py       # TurnStats fields, generate_with_fallback, wrappers
└── models.py            # model_class, sibling_model
backend/app/
├── agent_runner.py      # stream_response(fallback_model=)
├── model_state.py       # fallback_model_for
├── schemas.py           # ModelFallbackFrame
└── api/ws.py            # plumbing + frame
backend/tests/
├── test_model_fallback.py
└── test_model_fallback_ws.py
frontend/src/
├── api/wsClient.ts
├── types.ts
├── toolLabels.ts
├── App.tsx
└── components/MessageList.tsx
```

**Structure Decision**: Existing web-app layout; no new modules. The fallback sits next
to the retry loop it extends, and the sibling rule sits next to the class rules it reuses.

## Risks

- **Thought signatures (R5)**: the bypass value follows Google's documented guidance but
  can't be confirmed without a live Vertex call. It is in the owner's manual check
  (quickstart step 4).
- **Claude thinking blocks across versions**: not handled, because no Claude class has a
  sibling today (decision 7). If an operator configures `sonnet:2`, a switch after tool
  calls might be rejected. That would end in an agent error, not a loop.
- **File holds**: slices 4 and 5 wait for 022 to release `schemas.py`, `types.ts` and
  `App.tsx`, and for the product owner's `MessageList.tsx` decision. Slices 1–3 don't
  depend on them.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Gemini thought-signature guard (research R5): when a request is routed to the Gemini sibling, the current turn's pre-switch parts get Google's documented bypass value `skip_thought_signature_validator` in place of their `thought_signature`, on `Content`/`Part` copies only | Gemini 3 validates the current turn's function-call signatures, so a sibling may reject (400) a request carrying another version's signatures exactly when the fallback is needed. The guard is non-obvious, and it can't be verified without live Vertex: it is an owner live-check item (quickstart step 4). A test shows the stored session events are not mutated (only the request's copies change) | No guard: risks the fallback failing after any tool round. Dropping the parts: loses the turn's evidence. Re-running the turn from scratch on the sibling: duplicates history (R1) |
