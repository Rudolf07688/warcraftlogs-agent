# Implementation Plan: LLM provider switch and Anthropic API client for the chat agent

**Branch**: `032-llm-provider-switch` | **Date**: 2026-10-31 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/032-llm-provider-switch/spec.md` (signed off, D9)

## Summary

Add one provider layer, `wcl_agent/llm/provider.py`, that reads `WCL_LLM_PROVIDER`
(`vertex` | `anthropic`) and `ANTHROPIC_API_KEY` (as a `SecretStr`), builds every model client,
resolves the six model roles per provider, and converts Claude id forms. `RetryingClaude` gets its
client from it, so under `anthropic` the ADK agent calls the Anthropic API through the existing
retry loop. Two small agent fixes make Claude turns work at all on the current models (adaptive
thinking, and `drop_block` for thinking blocks invalidated by the app's history edits), which also
restores Claude on Vertex. Settings resolve the roles and make startup discovery provider-aware
(static Claude probing under `anthropic` until 033), the backend logs the provider and a missing
key once, a WebSocket turn on an unserved model runs on the default, and the docs explain the
switch. No dependency change, no migration, no frontend source change.

## Technical Context

**Language/Version**: Python 3.14 (backend, `wcl_agent`); TypeScript/React 19 (one new test file)

**Primary Dependencies**: `anthropic` 1.11.0 (`AsyncAnthropic`, `AnthropicVertex`), `google-adk`
2.10.0 (`AnthropicLlm`/`Claude`, `BuiltInPlanner`), `google-genai`, pydantic-settings, FastAPI;
vitest + Testing Library (frontend test)

**Storage**: N/A (no schema change)

**Testing**: pytest (`uv run --extra test pytest -q`), fakes and `httpx2.MockTransport` only;
vitest for the frontend test

**Target Platform**: Linux container (compose) and local `uv run`

**Project Type**: web service (FastAPI backend + ADK agent package) with a React frontend

**Performance Goals**: no change; the provider lookup is cached per process

**Constraints**: no live LLM calls, no key, no ADC in tests; `vertex` behaviour unchanged; files
owned by 033/034/035 untouched (`models.py`, `_load_models`, `suggestions.py`,
`conversation_titles.py`, `report_synthesis.py`, `guide_pipeline/*`, `schemas.py`, `App.tsx`)

**Scale/Scope**: ~1 new module (~170 lines), edits in 9 files, 3 new backend test files, 1 new
frontend test file, docs

## Constitution Check

*GATE: passed before Phase 0, re-checked after Phase 1.*

| Principle | Check | Status |
|---|---|---|
| I. DRY / reuse | One module reads the provider and the key and builds every client; the guard test enforces it. Role resolution is one function used by Settings and `agent.py`. Id-form conversion is one function. Reuses `generate_with_retry`, `RetryingClaude`, `get_model_state`, the existing discovery. The two `vertex.py` forwarders are transitional (owners 033/035 delete them). | Pass |
| II. Small verified steps | Tasks are sliced: provider module + unit tests → agent wiring + agent tests → settings/startup/WS + app tests → frontend test → docs. Each slice runs the suite. | Pass |
| III. Simplicity | Plain functions and a `StrEnum`; no registry, no plugin pattern. Interim discovery reuses static mode via settings, not new discovery code. One override (`_build_anthropic_kwargs`) instead of rewriting ADK's request builder. | Pass |
| IV. Typed contracts | `Provider` Literal, `ModelRole` enum, `SecretStr` key, `LlmProviderNotConfigured`; Settings stay pydantic. | Pass |
| V. Async FastAPI | No new endpoints; the agent path stays async; clients are built off-loop as ADK does today. | Pass |
| VI. GitNexus | Impact run on every edited symbol (below). HIGH/CRITICAL reported to the scrum master before editing. | Pass |
| VII. shadcn | No UI component built or changed (one test file only). | N/A |
| VIII. Backlog sync | sc-249 In Progress; no `todo.md` change from this feature. | Pass |

### GitNexus impact (upstream, worktree index at `b963463`)

| Symbol | Risk | Direct callers / flows | Note |
|---|---|---|---|
| `RetryingClaude` | MEDIUM | `agent.py`, `agent_runner.py` (+ module importers) | Only `_anthropic_client` source changes and one added override; signature unchanged. |
| `is_anthropic_model` | HIGH | `agent._is_anthropic`, `_route_to_sibling`, `before_model`; flows greeting, guild summary, before_model | Not edited (docstring only). Reused by `provider.serves`. |
| `_retrying_model` | HIGH | `build_agent` → `_get_runner` → every agent run | Not edited. |
| `build_agent` (agent model factory) | HIGH | `_get_runner`, `agent.py` module (`root_agent`); flows greeting, guild summary | Edit: the planner's `ThinkingConfig` gets `thinking_budget=-1` for Claude ids only. Gemini config byte-identical. |
| `adk_client_kwargs` | HIGH | `_build_web_search_tool` → `build_agent` | Moves to `provider.py` unchanged; import path changes in `agent.py`, `model_retry.py`. |
| `genai_client` (vertex) | CRITICAL | suggestions, report synthesis, guide LLM, discovery | Body moves to `provider.py`; `vertex.genai_client` forwards, so all callers are unchanged. |
| `anthropic_client` / `async_anthropic_client` | LOW | discovery probe / `RetryingClaude` | Bodies move to `provider.py`; `vertex.anthropic_client` forwards. |
| `Settings` / `get_settings` (config loader) | CRITICAL / MEDIUM | 32 direct readers | Additive: two new fields, an after-validator, property bodies routed through the provider. Under `vertex` every value equals today's. Properties are attribute reads (UNKNOWN in the graph); confirmed by text search: `model_state`, `main._load_models`, tests. |
| `get_model_state` | CRITICAL | ws chat, models API, raids, recent raids, conversation create | Not edited. New sibling `resolve_chat_model` reuses it. |
| `is_valid_model` | HIGH | ws chat, conversation create, raid / M+ investigate | Not edited; ws stops calling it (REST callers unchanged). |
| ws `chat` (WS model resolution) | UNKNOWN (FastAPI route) | WebSocket route; text search: only the router | Edit: `invalid_model` branch replaced by `resolve_chat_model`. |
| `_boot` | LOW | `lifespan` | Edit: one provider/credentials log block; greeting priming skipped when credentials are missing. |

## Project Structure

### Documentation (this feature)

```text
specs/032-llm-provider-switch/
├── spec.md
├── plan.md              # this file
├── research.md          # R1–R10
├── data-model.md        # Provider, ModelRole, id forms, Settings changes
├── quickstart.md        # AC → test map, owner live check
├── contracts/
│   ├── provider-layer.md   # the contract for 033/035
│   └── config.md           # env variables and log lines
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source code (files this feature creates or modifies)

```text
wcl_agent/llm/provider.py            NEW   the provider layer (contracts/provider-layer.md)
wcl_agent/llm/vertex.py              EDIT  client builders → provider; genai_client/anthropic_client become forwarders; docstring
wcl_agent/llm/model_retry.py         EDIT  RetryingClaude: client from provider, drop_block + beta header; imports; is_anthropic_model docstring
wcl_agent/agent.py                   EDIT  DEFAULT_MODEL via role_model; adaptive thinking for Claude; adk_client_kwargs import
backend/app/config.py                EDIT  role fields + after-validator, wcl_suggest_model, wcl_greeting_model, llm_provider, provider-aware model lists and discovery mode
backend/app/greeting.py              EDIT  GREETING_MODEL = settings.wcl_greeting_model (one line + import)
backend/app/main.py                  EDIT  _boot: provider + credentials log; skip greeting priming without credentials (not _load_models)
backend/app/model_state.py           EDIT  new resolve_chat_model(app, model)
backend/app/api/ws.py                EDIT  chat(): resolve_chat_model instead of the invalid_model branch
backend/tests/test_llm_provider.py        NEW  provider unit tests (parsing, roles, id forms, clients, credentials)
backend/tests/test_llm_provider_agent.py  NEW  agent turns on a fake AsyncAnthropic (mock transport), vertex client selection, thinking, drop_block, 429 retry, greeting path
backend/tests/test_llm_provider_app.py    NEW  settings under each provider, startup with/without key, secret leak, WS stale model
backend/tests/test_vertex.py         EDIT  guard test → provider.py (+ Anthropic constructors); factory tests via provider
frontend/src/App.modelFallback.test.tsx   NEW  stale selection / reopened chat sends the served default (App.tsx untouched)
.env.example                         EDIT  provider block
README.md                            EDIT  provider section
```

`docker-compose.yml`: no change (research R9).

**Structure Decision**: existing layout (`wcl_agent/llm/` for model plumbing, `backend/app/` for
the service, `backend/tests/` flat). The provider layer joins `vertex.py`, `model_retry.py` and
`models.py` in `wcl_agent/llm/`.

## Design notes

1. **provider.py** (contract in `contracts/provider-layer.md`). `active_provider()` is
   `functools.cache`d; it warns once for an invalid value. `_api_key() -> SecretStr | None` reads
   the env. Client builders branch on the provider here and nowhere else. The async Vertex builder
   adds `get_tracking_headers()` (moved from `RetryingClaude`). `role_model` warns through a
   module-level set so each role warns once even though Settings and `agent.py` both resolve.
2. **vertex.py** keeps `uses_vertex`, `model_location`, `project_id`, the catalog. `genai_client`
   and `anthropic_client` become forwarders with a lazy import (no import cycle:
   `provider` imports `vertex` at module level). `async_anthropic_client` and `adk_client_kwargs`
   move outright (their only callers are 032's files and `test_vertex.py`).
3. **model_retry.py**. `RetryingClaude._anthropic_client`:
   `(self.client or async_anthropic_client()).with_options(max_retries=0)`. New override:
   ```python
   def _build_anthropic_kwargs(self, *args, **kwargs):
       request = super()._build_anthropic_kwargs(*args, **kwargs)
       thinking = request.get("thinking")
       if isinstance(thinking, dict) and thinking.get("type") == "adaptive":
           request["thinking"] = {**thinking, "block_binding": {"prefix_mismatch_behavior": "drop_block"}}
           request["extra_headers"] = {"anthropic-beta": THINKING_BINDING_BETA}
       return request
   ```
4. **agent.py**. `build_agent`: `ThinkingConfig(include_thoughts=True,
   thinking_budget=-1 if _is_anthropic(model) else None)`, a model-family check like the existing
   web-search one, not a provider check. `DEFAULT_MODEL = role_model(ModelRole.CHAT)`.
5. **config.py**. Role fields default `""`; `@model_validator(mode="after")` resolves the six roles.
   `gemini_models`, `anthropic_models` and `model_list` go through `served_ids`, with
   `default_candidates()` filling an empty Claude list. `model_discovery_mode` returns `static`
   when `not has_model_catalog()`. `default_model` keeps its shape.
6. **main.py** `_boot`, before the models step: `logger.info("LLM provider: %s", ...)`; `error =
   credentials_error()`; if set, `logger.error(error)`, and the greeting step doesn't prime
   (priming would only log a second failure). `_load_models` is untouched.
7. **model_state.py**: `resolve_chat_model(app, model) -> str`: `to_provider_id(model)` if it is
   in the served list, else the default, with one info line when it changes. **ws.py**:
   `turn = turn.model_copy(update={"model": resolve_chat_model(ws.app, turn.model)})`, and the
   `invalid_model` frame is no longer sent from the socket.
8. **Tests**. Agent tests build a real `AsyncAnthropic` on `httpx2.MockTransport` (recording
   requests, scripting 200 / 429 / 401 bodies) and set it as the `RetryingClaude` client; nothing
   leaves the process. The secret test uses a sentinel key and `caplog`, the WS test client,
   `/api/models`, `/api/health` and the greeting endpoint.

## Sub-agents

None proposed. The work is one cohesive seam (provider module → its three consumers → tests),
and each slice depends on the previous one. Splitting would cost more in hand-offs than it saves.

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|---|---|---|
| Two transitional forwarders in `vertex.py` (thin, no logic; **to delete**: 033 moves `models.py` to `provider` and deletes `anthropic_client`, 035 moves its three files and deletes `genai_client`, by scrum-master grant after 032 merges) | `models.py` (033) and three 035 files call `vertex.genai_client` / `vertex.anthropic_client`; 032 may not edit them, and the unchanged discovery probe must reach the Anthropic API under `anthropic`. | Editing `models.py` breaks file ownership. Leaving the builders in `vertex.py` makes a module named "vertex" build Anthropic API clients and splits client construction across two modules. |
| Override of ADK's private `_build_anthropic_kwargs` (a pin test fails loudly if an ADK upgrade renames it) | The only hook where both ADK request paths (stream and non-stream) build the request; needed for `drop_block` (Q3/FR-013). | Re-implementing `generate_content_async` duplicates ADK's request/response mapping. Client-side stripping of thinking blocks is discouraged by the API docs and loses reasoning. |
