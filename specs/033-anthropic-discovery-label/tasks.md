# Tasks: Anthropic model discovery, provider label and discovery log fix

**Input**: `/specs/033-anthropic-discovery-label/` (plan.md, spec.md, research.md, data-model.md, contracts/models-endpoint.md)
**Tests**: requested by the brief (fakes only, no live LLM). Do not create `backend/tests/llm_fakes.py` (035's); use 032's fakes or local fakes, and import `llm_fakes` read-only only after 035 merges.
**Format**: `- [ ] T### [P] [US#] description with file path`

## Phase 1: Setup

- [ ] T001 Run `impact` (upstream) on each symbol before editing it (discover_models, _discover_catalog, _list_catalog, classify, model_class, is_catalog_id, sibling_model, _load_models, model_catalog key, ModelsResponse, get_models handler, has_model_catalog) and note risk; HIGH/CRITICAL goes to the scrum master.
- [ ] T002 Run the baseline `uv run --extra test pytest -q backend/tests/test_model_discovery.py backend/tests/test_models.py backend/tests/test_vertex.py` and record the result.

## Phase 2: Foundational (blocks all stories)

- [ ] T003 In `wcl_agent/llm/provider.py` make `has_model_catalog()` return True for both providers (update its docstring); adjust `backend/app/config.py` `model_discovery_mode` so catalog mode is no longer demoted under `anthropic`, and make `gemini_classes` empty under `anthropic`.
- [ ] T004 In `wcl_agent/llm/models.py` add the API-form Claude pattern and make `classify`, `model_class`, `is_catalog_id` and `callable_id` choose the id shape by `provider.active_provider()` (Vertex `name@date`, API `name-date`, each rejecting the other).
- [ ] T005 In `wcl_agent/llm/models.py` switch `_make_anthropic_client`/`_make_gemini_client` to `provider.anthropic_client`/`provider.genai_client`; then delete the `anthropic_client` forwarder (and `genai_client` if 035 has not merged) in `wcl_agent/llm/vertex.py` and update `backend/tests/test_vertex.py` and the `_make_anthropic_client` patches in `backend/tests/test_model_discovery.py`.

## Phase 3: US1 - Catalog discovery on the Anthropic API (P1)

**Independent test**: a fake Models API (paged, aliases + dated ids) and fake probes yield the newest usable model per class, no Gemini.

- [ ] T006 [P] [US1] Write `backend/tests/test_anthropic_discovery.py`: paged listing, API id/alias classification and alias-over-dated de-dup, not-enabled and no-quota probes, no Gemini offered, static mode in API form, listing failure falls back to static (not degraded), key never in logs.
- [ ] T007 [US1] In `wcl_agent/llm/models.py` add `_list_anthropic_api()` (iterates `provider.anthropic_client().models.list()`, maps to `CatalogEntry`, alias preferred, any error to `CatalogUnavailable`) and make `_list_catalog()` branch on the active provider; make `discover_models` use it under `anthropic`.

## Phase 4: US2 - Busy model falls back to its sibling (P1)

**Independent test**: Anthropic 429/529 on one model completes on the sibling; both busy shows the friendly message.

- [ ] T008 [P] [US2] Add tests in `backend/tests/test_anthropic_discovery.py` (or `backend/tests/test_model_fallback.py` if it fits better and is granted): `sibling_model`/`class_label` with API dated ids, 429 and 529 with `retry-after` honoured, a hint over the wait budget switches to the sibling at once (logged), both busy gives the same friendly message.
- [ ] T009 [US2] Fix any gap the tests expose in `wcl_agent/llm/models.py` (expected: none beyond T004; `model_retry.py` is not edited).

## Phase 5: US3 - Per-provider stored catalog (P1)

**Independent test**: a stored Vertex catalog is never served under `anthropic` and the reverse.

- [ ] T010 [P] [US3] Add tests in `backend/tests/test_model_discovery.py`: key differs per provider, cross-provider cache is not served, ids of the wrong shape are rediscovered with a warning.
- [ ] T011 [US3] Change `keys.model_catalog` in `wcl_agent/cache/cache.py` to take the provider (`ext:models:v2:{provider}:...`) and update its call in `backend/app/main.py::_load_models` (provider, `-` project/location under `anthropic`, no Gemini classes under `anthropic`).

## Phase 6: US4 - Provider label in the picker (P2)

**Independent test**: the badge shows the right text at 390px; the endpoint returns `provider`.

- [ ] T012 [P] [US4] Add `provider` assertions to `backend/tests/test_api.py` and a test in `backend/tests/test_models.py` if needed (default `vertex`, `anthropic` when active, no secrets in the body).
- [ ] T013 [US4] Add `provider: Literal["vertex","anthropic"] = "vertex"` to `ModelsResponse` in `backend/app/schemas.py` and fill it in `backend/app/api/models.py` from `provider.active_provider()`.
- [ ] T014 [US4] Search the shadcn registry via the MCP (`registries: ["@shadcn"]`) for a badge, use/add it from `frontend/` as the MCP says, then run the audit checklist.
- [ ] T015 [US4] Extend `getModels()` in `frontend/src/api/restClient.ts`, keep `provider` in state in `frontend/src/App.tsx` (after grant) and show the read-only badge in `frontend/src/components/ModelSelect.tsx` ("Vertex AI" / "Anthropic API").
- [ ] T016 [P] [US4] Write `frontend/src/components/ModelSelect.test.tsx` (both labels, hidden when absent) and update `frontend/src/App.test.tsx`/`App.modelFallback.test.tsx` mocks only if required.

## Phase 7: US5 - Startup log and empty listing (P3)

**Independent test**: an empty listing runs the fallback under both providers; every boot logs the summary line.

- [ ] T017 [P] [US5] Add tests in `backend/tests/test_model_discovery.py`: empty Vertex listing and empty Anthropic listing run the fallback with one warning; the summary line is logged on fresh and cached boots.
- [ ] T018 [US5] In `wcl_agent/llm/models.py::_list_catalog` raise `CatalogUnavailable` when the combined listing has zero entries; in `backend/app/main.py::_load_models` log `model discovery: N models from <source> (<provider>)` on every boot.

## Phase 8: Polish

- [ ] T019 [P] Add the discovery note to `.env.example` (`WCL_MODEL_DISCOVERY`/`WCL_ANTHROPIC_CLASSES` apply to `anthropic`); list the README lines for the scrum master (do not edit `README.md`).
- [ ] T020 Run `uv run --extra test pytest -q`, `cd frontend && npm run build && npm test`; 390px check with headless Chrome on app port 18033 (own containers: Postgres 15433, Redis 16333).
- [ ] T021 Index the worktree, run `detect-changes --scope all`, check ownership, restore `CLAUDE.md` and `.specify/feature.json`, commit (never push).

## Dependencies and parallelism

T003-T005 first, then T007 (US1), then US2/US3/US5 backend tasks in any order; US4 backend (T013) is independent of the rest and T012/T016/T017/T006/T008/T010 are test files that can run in parallel with their code tasks. Everything is in few files, so I will do it alone, without sub-agents. MVP: Phase 2 + US1.
