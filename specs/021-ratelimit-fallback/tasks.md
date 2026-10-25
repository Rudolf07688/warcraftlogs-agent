# Tasks: Rate-Limit Fallback to the Sibling Model (021)

**Input**: Design documents from `/specs/021-ratelimit-fallback/`
(plan.md, spec.md, research.md, data-model.md, contracts/websocket-model-fallback.md, quickstart.md)

**Tests**: Required (brief AC 5: fake 429s on the Gemini and the Anthropic paths, no live Vertex).

**Verification per slice**: `uv run --extra test pytest -q` (baseline at cc3c783: 1008 passed /
3 skipped / 1 deselected) and, for frontend tasks, `npm run build` in `frontend/`. Before each
symbol edit run GitNexus `impact` upstream; `detect_changes` before each commit.

**Unchanged by contract (scrum master condition)**: `generate_with_retry`,
`make_before_model_callback`, and the tests `test_model_retry.py`, `test_runner_retry.py`,
`test_ws_rate_limit.py`, the greeting and the guide tests.

## Phase 1: Setup

- [ ] T001 Confirm the baseline in the worktree: `uv run --extra test pytest -q` green, and record the counts in specs/021-ratelimit-fallback/checkpoint.md

## Phase 2: Foundational (blocks every story)

- [ ] T002 Add `model_class(model_id) -> tuple[str, str] | None` and `sibling_model(model, served) -> str | None` in wcl_agent/llm/models.py, reusing `_GEMINI_RE` / `_CLAUDE_RE` (a `name@version` id is classified by its name). Peers are the served ids of the same class in served order: first peer → second (or None); any other peer → first; unknown or unserved → None; plus `class_label(model_id)` ("Gemini flash", "Claude sonnet", None for unknown ids)
- [ ] T003 [P] Add `fallback_model_for(app, model) -> str | None` in backend/app/model_state.py: `sibling_model(model, get_model_state(app)[0])`
- [ ] T004 Add `TurnStats` fields `fallback_model`, `switched_to` and `switch_index` (all `None` by default) in wcl_agent/llm/model_retry.py
- [ ] T005 Tests for T002/T003 (and `class_label`) in backend/tests/test_model_fallback.py: newest → second, second → newest, three versions (third → newest), single-model class → None (Claude), Claude `@version` ids, unknown id → None, model not served → None, and `fallback_model_for` over a fake `app.state` and over no state (settings fallback)

**Checkpoint**: sibling rule tested; nothing behaves differently yet.

## Phase 3: User Story 1: a rate-limited turn finishes on the sibling (P1) MVP

**Goal**: a request on the turn's model that stays rate limited after the retries continues on the sibling, once, with no duplicated output.

**Independent test**: a fake client that 429s for model A and answers for model B; the wrapper yields B's response and the client saw `model=B`.

- [ ] T006 [US1] Add `generate_with_fallback(inner, llm_request, policy)` in wcl_agent/llm/model_retry.py per plan Design 2: act only when `current_turn` is set and `llm_request.model == stats.model`; route to `stats.switched_to` before the first attempt when already switched; on `ModelRateLimited` with `fallback_model` set and no switch yet, set `switched_to` / `switch_index`, log a warning, emit `{"type": "model_fallback", "from_model", "to_model"}`, route and run `generate_with_retry` once more. Every other case re-raises unchanged
- [ ] T007 [US1] Add the Gemini thought-signature guard used when routing a Gemini request (research R5) in wcl_agent/llm/model_retry.py: replace `thought_signature` with `b"skip_thought_signature_validator"` on the parts in `contents[user_turn_indices(contents)[-1]:switch_index]`, on new `Content`/`Part` copies only. Skip it for Claude ids (`is_anthropic_model`)
- [ ] T008 [US1] Make `RetryingGemini.generate_content_async` and `RetryingClaude.generate_content_async` delegate to `generate_with_fallback(lambda: super(...).generate_content_async(llm_request, stream), llm_request, self.policy)` in wcl_agent/llm/model_retry.py, and update the module docstring
- [ ] T009 [US1] Gemini-path tests in backend/tests/test_model_fallback.py: `RetryingGemini(model=A, client=<fake genai client>)` whose `aio.models.generate_content[_stream]` raises a genai `APIError(429)` for A and returns a response for B. Assert: the response from B is yielded; the recorded models are [A..., B]; exactly one `model_fallback` record with both ids; `stats.switched_to == B`; a second request in the same turn calls B only (no A attempt). Use a zero-delay `RetryPolicy`
- [ ] T010 [US1] Anthropic-path tests in backend/tests/test_model_fallback.py: `RetryingClaude(model=A, client=<fake AsyncAnthropicVertex>)` whose `messages.create(**kwargs)` raises `anthropic.RateLimitError` for `kwargs["model"] == A` and returns an `anthropic.types.Message` for B (two-model class, Q3 = A). Same assertions as T009
- [ ] T011 [US1] Guard tests in backend/tests/test_model_fallback.py: a non-rate-limit error → no switch; a 429 after a response was already yielded (mid-stream) → raw error, no switch, no record; no turn installed (CLI) → `ModelRateLimited` as before; a request whose model is not `stats.model` (a sub-agent) → no switch; the signature guard replaces current-turn pre-switch signatures in the request and leaves the original `Content`/`Part` objects (the stored session events) and earlier-turn parts untouched (Complexity Tracking R5)
- [ ] T012 [US1] Add keyword-only `fallback_model: str | None = None` to `stream_response` in backend/app/agent_runner.py, set it on `TurnStats`, document the `model_fallback` record, and append `fallback=<switched_to or ->` to the end of the turn stats line
- [ ] T013 [US1] Runner tests in backend/tests/test_model_fallback.py (using the `_Runner` fake pattern from test_runner_retry.py): `fallback_model` reaches `TurnStats`; a `model_fallback` record emitted by the script is yielded in order; the stats line ends with `fallback=B` after a switch and `fallback=-` without one

**Checkpoint**: backend fallback complete and tested at the wrapper and runner level; the socket still passes no sibling, so the behaviour is unchanged end to end.

## Phase 4: User Story 2: the player is told when both are busy (P1)

**Goal**: one switch only; no sibling or a busy sibling → feature 011 message; the socket survives.

**Independent test**: both models 429 → `ModelRateLimited` after exactly one switch; the socket sends `rate_limited`, and the next turn works.

- [ ] T014 [US2] Wrapper tests in backend/tests/test_model_fallback.py for both providers: both A and B 429 → `ModelRateLimited` raised, one `model_fallback` record, the attempts on B equal the policy's attempts, and no further switch; `fallback_model=None` (Claude single-model class) → `ModelRateLimited` with no record and no B call
- [ ] T015 [US2] Plumb the sibling in backend/app/api/ws.py: `chat()` computes `fallback_model_for(ws.app, turn.model)` after `is_valid_model`, `_start_turn(..., fallback_model=)` passes it to `_handle_turn(..., fallback_model: str | None = None)`, which passes it to `stream_response`. In the loop, set a local `switched` flag when a `model_fallback` record arrives. In the `ModelRateLimited` branch send `BOTH_RATE_LIMITED_MESSAGE.format(label=class_label(turn.model))` when switched (and a label exists), else `RATE_LIMITED_MESSAGE` unchanged; the code stays `rate_limited`
- [ ] T016 [US2] Socket tests in backend/tests/test_model_fallback_ws.py (the `_FakeSocket` + `as_user` pattern from test_ws_rate_limit.py): `_handle_turn(..., fallback_model=B)` hands `fallback_model=B` to `stream_response`; a stream that raises `ModelRateLimited` after a `model_fallback` record → the `rate_limited` error carries "Both Gemini flash models are rate-limited right now. Please try again in about a minute." and only the user message is stored; without a `model_fallback` record → the feature 011 message unchanged (SC-010); the next turn on the same conversation completes with `done`
- [ ] T016a [US2] SC-007 history test in backend/tests/test_model_fallback_history.py: a real ADK `Runner` with `InMemorySessionService` and a minimal `Agent` (one dummy async tool, `make_before_model_callback`) whose model is `RetryingGemini(model=A, client=<fake genai client>)`, driven through `agent_runner.stream_response(..., fallback_model=B)` with `_get_runner` patched to it. Script: A returns a function call, A then 429s, B answers text. Assert the session events hold exactly one user message, one function call, one function response and one final answer, and the yielded tokens hold the answer once

**Checkpoint**: end-to-end backend fallback live (minus the typed frame forward).

## Phase 5: User Story 3: the player sees which model answered (P2)

**Goal**: `model_fallback` reaches the client as a typed frame; status line while switching; a note under the reply.

**Independent test**: a stream with a `model_fallback` record → the socket sends `{"type": "model_fallback", ...}`; the frontend builds; the note renders on the agent message.

**Needs grants**: `backend/app/schemas.py`, `frontend/src/types.ts`, `frontend/src/App.tsx` (022), `frontend/src/components/MessageList.tsx` (product owner), `frontend/src/toolLabels.ts`.

- [ ] T017 [US3] Append `ModelFallbackFrame(type="model_fallback", from_model: str, to_model: str)` in backend/app/schemas.py, next to `ModelRetryFrame`, per contracts/websocket-model-fallback.md
- [ ] T018 [US3] Forward `kind == "model_fallback"` as `ModelFallbackFrame(**record)` in backend/app/api/ws.py
- [ ] T019 [US3] Socket test in backend/tests/test_model_fallback_ws.py: tokens before and after a `model_fallback` record → frames `meta, token, model_fallback, token, done`, the frame equals the contract, and the stored agent message is the tokens joined exactly once
- [ ] T020 [P] [US3] Add `| { type: "model_fallback"; from_model: string; to_model: string }` to `Frame` in frontend/src/api/wsClient.ts
- [ ] T021 [P] [US3] Add `fallback?: { from: string; to: string }` to `Message` in frontend/src/types.ts
- [ ] T022 [P] [US3] Add `fallbackLabel(from, to)` ("<from> is rate-limited — switching to <to>…") next to `retryLabel` in frontend/src/toolLabels.ts
- [ ] T023 [US3] Handle the frame in frontend/src/App.tsx: a `pendingFallbackRef`; on `model_fallback`, set the status to `fallbackLabel` and remember it; on `done`, attach `fallback` to the new agent message; reset on `done` and `error`
- [ ] T024 [US3] Search the shadcn registry through the MCP (badge / alert / item) for the note, decide, record the outcome in plan.md Constitution Check VII, then render "Answered by <to> (<from> was rate-limited)" under the agent reply when `m.fallback` is set in frontend/src/components/MessageList.tsx; run the MCP audit checklist if a registry item is added
- [ ] T025 [US3] `npm run build` in frontend/ green

## Phase 6: Polish

- [ ] T026 [P] One line at the `model_retry.py` entry in documentation/ai_guide.md: "… + 429 fallback to the same-class sibling (feature 021)"
- [ ] T027 Full suite green (`uv run --extra test pytest -q`); confirm `test_model_retry.py`, `test_runner_retry.py`, `test_ws_rate_limit.py`, `test_conversation_titles.py`, the greeting and the guide/guide_pipeline tests are unchanged (`git diff --stat cc3c783 -- backend/tests` lists only the new 021 test files) (SC-008)
- [ ] T028 Re-index the worktree and run `detect-changes --scope all`; check that the changed files ⊆ the granted list; restore `CLAUDE.md` and `.specify/feature.json` before committing
- [ ] T029 Mark tasks done, update checkpoint.md, and send the scrum master the hand-off (branch, base, commits, files, tests, risks, how to verify each AC per quickstart.md)

## Dependencies

- T002 → T003, T005; T004 → T006 → T007 → T008 → T009–T011; T012 → T013.
- US2 (T014–T016) needs US1's T006/T008 and T012.
- US3 backend (T017–T019) needs T015 and the `schemas.py` grant; frontend T020–T025 needs the grants; T020–T022 are independent files.
- Polish after all stories.

## Parallel opportunities

- T003 alongside T004 (different files).
- T020, T021, T022 together (different files), then T023 → T024.
- The backend core (T006–T016) is one tightly coupled chain in two files; planned as solo work, no sub-agents.

## Implementation strategy

MVP = Phases 2–3 (the switch works and is tested at the wrapper/runner level), then US2
wires it into the socket. US3 waits for the file grants and can land last without
blocking the backend. Each phase ends with the full pytest run.
