# Tasks: LLM provider switch and Anthropic API client for the chat agent

**Input**: Design documents from `specs/032-llm-provider-switch/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Requested (spec FR-012, sc-249 AC 9). All tests use fakes: an `AsyncAnthropic` on
`httpx2.MockTransport`, monkeypatched env, the FastAPI test client. No key, no ADC, no live call.

**Baseline** (`b963463`, this worktree): `uv run --extra test pytest -q` → 1171 passed, 6 skipped,
1 deselected.

**Gate**: no task below starts before the scrum master relays OWNER GO and the file grant.

**Rules for every edit**: run GitNexus `impact` (upstream) on the symbol first. Touch only the
granted files (plan.md "Source code"). Match the surrounding style and comment density.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Re-index the worktree (`node /home/rudolf/dev/warcraftlogs-agent/.gitnexus/run.cjs analyze --index-only` in `/home/rudolf/dev/wcl-worktrees/dev-a`) and confirm the baseline suite (1171 passed) before the first edit

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the provider layer every story uses (contracts/provider-layer.md).

- [X] T002 Create `wcl_agent/llm/provider.py` with the module docstring (the rule), `Provider`, `ModelRole`, `ROLE_ENV`, `ROLE_DEFAULTS` (data-model.md table), `LlmProviderNotConfigured`, `active_provider()` (cached; trimmed, case-insensitive; one warning and `vertex` for an invalid value), `_api_key() -> SecretStr | None`, `credentials_error()`, `has_model_catalog()`
- [X] T003 Add id forms and roles to `wcl_agent/llm/provider.py`: `serves()` (reuses `model_retry.is_anthropic_model` via a lazy import, or a local family check if the import would cycle), `to_provider_id()` (dated `name@YYYYMMDD` ⇄ `name-YYYYMMDD` into the active form), `served_ids()`, `default_candidates()`, `role_model(role, explicit=None)` (explicit/env if served, else default; warn once per role)
- [X] T004 Move the client builders into `wcl_agent/llm/provider.py`: `genai_client()`, `adk_client_kwargs()` (bodies unchanged), `anthropic_client(**kw)` and `async_anthropic_client(**kw)` (Anthropic API with `api_key` from the `SecretStr` under `anthropic`, raising `LlmProviderNotConfigured` without a key; `AnthropicVertex`/`AsyncAnthropicVertex` at `project_id()`/`model_location()` under `vertex`, the async Vertex one adding ADK's `get_tracking_headers()`)
- [X] T005 In `wcl_agent/llm/vertex.py`: delete the moved builders; keep `genai_client()` and `anthropic_client(**kwargs)` as forwarders with a lazy `from .provider import …` and a one-line "transitional: 033/035 move callers to provider" note; update the module docstring (location + catalog only; clients live in provider)
- [X] T006 [P] Write `backend/tests/test_llm_provider.py`: provider parsing (unset, `" Anthropic "`, `openai` → vertex with one warning), `to_provider_id` both ways and passthrough (Gemini, undated Claude), `served_ids`, `default_candidates`, `role_model` for all 6 roles × 2 providers, explicit Claude wins under anthropic, explicit Gemini under anthropic warned once and replaced, `credentials_error` with and without key, client builders (fake constructors capture kwargs; API client gets the key, Vertex clients get project/location), `LlmProviderNotConfigured` message has no key
- [X] T007 Update `backend/tests/test_vertex.py`: the factory tests call `provider` (and the two forwarders still return the same clients); the guard test scans for `genai\.Client\(|AnthropicVertex\(|\bAnthropic\(|AsyncAnthropic\(` outside `wcl_agent/llm/provider.py`
- [X] T008 Run `uv run --extra test pytest -q backend/tests/test_llm_provider.py backend/tests/test_vertex.py backend/tests/test_model_discovery.py` and then the full suite (no new failures)

**Checkpoint**: provider layer in place, `vertex` behaviour unchanged, guard test enforces AC 2.

---

## Phase 3: User Story 1 - Run Barnaby on Claude with an Anthropic API key (P1) 🎯 MVP

**Goal**: under `anthropic`, every ADK agent run reaches the Anthropic API through the retry
wrapper; Claude turns work on both providers.

**Independent Test**: a chat turn with a tool round, a greeting run and a 429 retry against a fake
`AsyncAnthropic` on a mock transport; under `vertex` the client is `AsyncAnthropicVertex`.

- [ ] T009 [US1] In `wcl_agent/llm/model_retry.py`: import `adk_client_kwargs`, `async_anthropic_client` from `.provider`; `RetryingClaude._anthropic_client` becomes `(self.client or async_anthropic_client()).with_options(max_retries=0)`; update its docstring (either provider)
- [ ] T010 [US1] In `wcl_agent/llm/model_retry.py`: add `THINKING_BINDING_BETA = "thinking-binding-controls-2026-08-01"` and the `RetryingClaude._build_anthropic_kwargs` override (adaptive thinking → `block_binding.prefix_mismatch_behavior="drop_block"` + `extra_headers` beta); update the `is_anthropic_model` docstring (Claude family on either provider)
- [ ] T011 [US1] In `wcl_agent/agent.py`: `from .llm.provider import ModelRole, adk_client_kwargs, role_model`; `DEFAULT_MODEL = role_model(ModelRole.CHAT)` (keep the comment's intent); `build_agent` gives the planner `ThinkingConfig(include_thoughts=True, thinking_budget=-1)` for Claude ids only (comment: ADK's Anthropic adapter requires an explicit budget; -1 = adaptive)
- [ ] T012 [US1] Write `backend/tests/test_llm_provider_agent.py`: (a) under `anthropic`, `RetryingClaude._anthropic_client` is an `AsyncAnthropic` with `max_retries=0`, under `vertex` an `AsyncAnthropicVertex`; (b) a full ADK turn (`InMemoryRunner` or `agent_runner.stream_response`) on `build_agent("claude-sonnet-5-5")` with a mock-transport client: the first response is a `tool_use` for a stubbed tool, the second text; assert both requests reached the transport with the tool declarations, `thinking == {"type": "adaptive", "display": "summarized", "block_binding": {"prefix_mismatch_behavior": "drop_block"}}` and the `anthropic-beta` header; (c) a 429 with `retry-after: 0` then 200 is retried by `generate_with_retry` (one `model_retry` record); (d) Gemini agents' planner config has no `thinking_budget`; (e) the greeting path (`greeting._generate_greeting` with the greeting role model) reaches the fake client
- [ ] T013 [US1] Add an ADK pin test to `backend/tests/test_llm_provider_agent.py`: `AnthropicLlm` still defines `_build_anthropic_kwargs` and `_anthropic_client`, and `RetryingClaude` overrides both, so an ADK upgrade that renames them fails loudly (scrum-master condition)
- [ ] T014 [US1] Run the US1 tests and the full suite; fix regressions at the root

**Checkpoint**: MVP: Claude agent turns run on the Anthropic API (fakes) and on Vertex again.

---

## Phase 4: User Story 2 - The key stays secret; a missing key never crashes (P1)

**Goal**: one clear startup error without a key, degraded models, no crash; the key never leaks.

**Independent Test**: sentinel key leak test; startup with `anthropic` and no key.

- [ ] T015 [US2] In `backend/app/main.py` `_boot`, before the `models` step: log `LLM provider: %s` once; `error = credentials_error()`; if set, `logger.error(error)` and skip priming the greeting in the `greeting` step (comment why). `_load_models` stays untouched
- [ ] T016 [US2] Write the secret and missing-key tests in `backend/tests/test_llm_provider_app.py`: (a) sentinel `ANTHROPIC_API_KEY`, a mock transport answering 401: run a chat turn through the WS test client (fake agent client), call `/api/models`, `/api/health`, the greeting endpoint; assert the sentinel is absent from `caplog` text, every WS frame, every response body and `str`/`repr`/traceback of the raised errors; (b) `anthropic` without key: `_boot` logs exactly one ERROR naming `ANTHROPIC_API_KEY`, `app.state.models_degraded` is true with Claude ids, the app answers `/api/health`, and a chat turn ends in an `agent_error` frame with the key-free message and the socket stays open
- [ ] T017 [US2] Run the US2 tests and the full suite

**Checkpoint**: AC 4 proven.

---

## Phase 5: User Story 3 - One `.env` line switches the provider (P1)

**Goal**: roles resolve per provider; startup discovery follows the provider without touching
`_load_models`.

**Independent Test**: Settings under each provider; `_load_models` under `anthropic` probes only
Claude ids in API form through the forwarder.

- [ ] T018 [US3] In `backend/app/config.py`: role fields default `""`; add `wcl_suggest_model: str = ""`, `wcl_greeting_model: str = ""`; an after-validator resolving the six fields through `role_model`; `llm_provider` property; `gemini_models` / `anthropic_models` / `model_list` through `served_ids` (empty Claude list → `default_candidates()`); `model_discovery_mode` returns `static` with one info line when `not has_model_catalog()`; keep comments accurate (no Gemini defaults claimed)
- [ ] T019 [US3] In `backend/app/greeting.py`: `GREETING_MODEL = settings.wcl_greeting_model` (import `settings`; comment: the greeting role, per provider)
- [ ] T020 [US3] Add settings/discovery tests to `backend/tests/test_llm_provider_app.py`: a "vertex unchanged" regression test (scrum-master condition), parametrised over provider unset and `vertex`, asserting literal `b963463` values for every role field, `default_model`, `model_list`, `gemini_models`, `anthropic_models`, `candidate_models` and `model_discovery_mode` (default env and an owner-style env); under `anthropic` with the owner-style env (Gemini role ids, `WCL_MODELS` Gemini, `WCL_ANTHROPIC_MODELS=claude-sonnet-4@20250514`, `WCL_MODEL_DISCOVERY=catalog`): roles are Claude defaults with one warning per Gemini role, discovery mode `static`, `gemini_models == []`, `anthropic_models == ["claude-sonnet-4-20250514"]`; `_load_models` with a fake probe client (patched `provider.anthropic_client`) serves the probed Claude ids and never calls `vertex.list_publisher_models` or `project_id`
- [ ] T021 [US3] Run the US3 tests and the full suite (watch `test_model_discovery.py`, `test_guides_and_boot.py`, `test_greeting.py`, `test_guide_pipeline_review.py`)

**Checkpoint**: AC 1, 5, 7 proven.

---

## Phase 6: User Story 4 - Old chats keep working after a switch (P2)

**Goal**: WS turns on an unserved model run on the default; the browser never sends a stale id.

**Independent Test**: WS turn on a Gemini id under `anthropic`; the App test.

- [ ] T022 [US4] In `backend/app/model_state.py`: `resolve_chat_model(app, model) -> str` (`to_provider_id`; served → itself, else default with one info line)
- [ ] T023 [US4] In `backend/app/api/ws.py` `chat()`: replace the `is_valid_model` / `invalid_model` branch with `turn = turn.model_copy(update={"model": resolve_chat_model(ws.app, turn.model)})`; drop the now-unused `is_valid_model` import
- [ ] T024 [P] [US4] Add WS tests to `backend/tests/test_llm_provider_app.py`: under `anthropic` a turn naming `gemini-3.6-flash` runs on the default (fake agent records the model) with no `invalid_model` frame; a Vertex-form `claude-sonnet-4@20250514` runs as `claude-sonnet-4-20250514` when served; `POST /api/conversations` with an unserved model still returns 400
- [ ] T025 [P] [US4] Write `frontend/src/App.modelFallback.test.tsx` (mock `./api/restClient`, `./api/wsClient` `ChatSocket` capturing `send`, `./auth/useAuth`; render `App` in a `MemoryRouter`): (a) `/api/models` serves only Claude; sending a message sends `model: <default>`; (b) opening a conversation whose stored model is a Gemini id, then sending, sends the default. No change to `App.tsx`
- [ ] T026 [US4] Run the backend suite, `npx vitest run` and `npm run build` in `frontend/`

**Checkpoint**: AC 6 and the PO condition (D9) proven.

---

## Phase 7: User Story 5 - The owner can follow the switch from the docs (P3)

- [ ] T027 [P] [US5] `.env.example`: a provider block above the Vertex block (`WCL_LLM_PROVIDER`, `ANTHROPIC_API_KEY=` marked secret, ADC not needed for LLM calls under `anthropic`, `GCP_ADC_FILE=/dev/null` hint); role variables with both providers' defaults incl. `WCL_SUGGEST_MODEL` and `WCL_GREETING_MODEL`; note that under `anthropic` Gemini ids are ignored and discovery is static until 033
- [ ] T028 [P] [US5] `README.md`: a "Switching the LLM provider" section (the two lines, restart, role defaults table, missing-key behaviour, key handling via `env_file: .env`, ADC note, Claude on Vertex now works, what still runs on Gemini until 035)

---

## Phase 8: Polish & cross-cutting

- [ ] T029 Grep check: no `AsyncAnthropicVertex(`/`AnthropicVertex(`/`AsyncAnthropic(`/`genai.Client(` outside `provider.py`; no call site compares `active_provider()` outside `provider.py`/`config.py` properties' delegation
- [ ] T030 Full backend suite (no new failures vs 1171 passed), `npm run build` and `npx vitest run` in `frontend/`
- [ ] T031 GitNexus: `analyze --index-only` then `detect-changes --scope all --repo .` (re-run on partial/truncated); ownership check (`git diff --name-only b963463...HEAD` + uncommitted ⊆ grant); restore `CLAUDE.md` and `.specify/feature.json`; commit
- [ ] T032 Hand-off message to the scrum master (branch, base, commits, files, test results, risks incl. drop_block live check, AC verification map from quickstart.md, "Claude on Vertex works again")

---

## Dependencies & execution order

- Phase 1 → Phase 2 (T002 → T003 → T004 → T005; T006/T007 after T005) → stories.
- US1 (T009–T014) needs Phase 2. US2 (T015–T017) needs US1's client wiring (the leak test runs a
  real agent turn). US3 (T018–T021) needs Phase 2 only, but runs after US2 because both add tests
  to `test_llm_provider_app.py`. US4 needs US3 (resolved default). US5 any time after US3.
- Within a story, implementation before its tests' run; tests may be written first.

### Parallel opportunities

- T006 ‖ T007 (different test files).
- T024 ‖ T025 (backend vs frontend test file).
- T027 ‖ T028 (docs).

## Implementation strategy

MVP = Phase 2 + US1: Claude agent turns on the Anthropic API behind the switch. Then the secret
and missing-key safety (US2), the one-line switch (US3), stale chats (US4), docs (US5). Each
phase ends with the full suite green.
