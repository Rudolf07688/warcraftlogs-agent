---

description: "Task list for feature 016: live model discovery from the Vertex Model Garden catalog"
---

# Tasks: Live Model Discovery

**Input**: Design documents from `specs/016-live-model-discovery/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R9), data-model.md, contracts/model-discovery.md, contracts/configuration.md, quickstart.md

**Tests**: Included. The source design (`documentation/live_model_probe.md` § Verification) and quickstart.md §1 call for unit tests with recorded catalog fixtures and no network. Write each story's tests first and confirm they fail before implementing.

**Organization**: Tasks are grouped by user story (spec.md US1–US6) so each story can be implemented and verified on its own.

**Before editing any existing symbol**: run `node .gitnexus/run.cjs impact "<symbol>" --direction upstream --repo .` and report the risk (CLAUDE.md). `discover_models` returns **UNKNOWN**. Its known callers are `backend/app/main.py::_boot._models`, `backend/tests/test_models.py` and `backend/tests/test_guides_and_boot.py`; confirm with `grep -rn discover_models backend wcl_agent`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story the task belongs to (US1–US6)

## Path Conventions

- Standalone agent package: `wcl_agent/`
- Backend: `backend/app/`
- Tests: `backend/tests/`, run with `uv run --extra test pytest -q`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Recorded catalog data that every test phase uses.

- [X] T001 Record today's two catalog listings as test fixtures: `backend/tests/fixtures/model_catalog_google.json` and `backend/tests/fixtures/model_catalog_anthropic.json`.
  - **Source**: the raw `publisherModels` arrays from `GET https://aiplatform.googleapis.com/v1beta1/publishers/{google|anthropic}/models?pageSize=100`, called with ADC and the `x-goog-user-project` header. Keep only `name`, `versionId` and `launchStage` per entry.
  - **Required content**: the Google file must include `gemini-3.1-pro-preview`, `gemini-2.5-pro`, `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, at least one `EXPERIMENTAL` entry and the non-chat models (TTS, image, live, embedding, `gemini-4-argon`, omni). The Anthropic file must include haiku-4-5 (`versionId` `20251001`), haiku-5-5, sonnet-5-5, opus-5-5 (`versionId` `default`), fable-5-1 and `claude-3-opus`.
  - **If no live credentials are available**: hand-write the files from the facts in `documentation/live_model_probe.md` § "Catalog facts", and note that at the top of the test module.
  - **Done 2026-10-18 (live):** recorded from the global endpoint with ADC: 30 Google and 13 Anthropic entries. The global Anthropic listing has no `claude-3-opus` (only regional listings do), so `test_model_discovery.py` adds it by hand.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared types, the catalog client, the settings, and the switch of `discover_models` to a typed result. Every story builds on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Create `wcl_agent/vertex.py` per research R1 and R5 and contracts/model-discovery.md:
  - `model_location()`: env `WCL_MODEL_LOCATION`, default `"global"`.
  - `project_id()`: env `GOOGLE_CLOUD_PROJECT`, else the project from `google.auth.default()`.
  - a frozen dataclass `CatalogEntry(publisher, name, version_id, stage)`.
  - `class CatalogUnavailable(Exception)`.
  - `list_publisher_models(publisher)`. It uses `google.auth.transport.requests.AuthorizedSession` with the `cloud-platform` scope and the header `x-goog-user-project: project_id()`, requests `pageSize=100`, follows `nextPageToken`, and uses `timeout=10` per request. It keeps the last path segment of `name` as `CatalogEntry.name`. Any transport, auth, HTTP status or JSON/shape error becomes `CatalogUnavailable`.
  - The module docstring says it is the only place that knows where models run.
- [X] T003 [P] Create `backend/tests/test_vertex.py` for the listing. Use a fake `AuthorizedSession` that returns two pages, so pagination is followed. Assert the `x-goog-user-project` header and `timeout=10`. Assert that the name segment is parsed. Assert that an HTTP 403, a `requests` exception and a malformed body each raise `CatalogUnavailable`. Assert that `model_location()` defaults to `global` and honours `WCL_MODEL_LOCATION`.
- [X] T004 [P] Add `ClassResult` and `ModelCatalog` (Pydantic) to `wcl_agent/cache_models.py` per data-model.md:
  - `ModelCatalog` has the fields `models`, `default`, `degraded`, `source: Literal["catalog","static","fallback","degraded"]`, `classes: list[ClassResult]`, `listed: list[str]` and `fetched_at: datetime`.
  - A `model_validator` enforces: `models` is non-empty, `default ∈ models`, and `degraded == (source == "degraded")`.
- [X] T005 Add the discovery value types to `wcl_agent/models.py` per data-model.md:
  - `ClassSetting(publisher, name, keep)`: frozen dataclass.
  - `Candidate(publisher, cls, version: tuple[int, int], preview, model_id)`: frozen dataclass.
  - `ProbeOutcome(StrEnum)`: `passed`, `not_enabled`, `no_quota`, `failed`.
  - The constants `GEMINI_CLASSES = ("pro", "flash", "flash-lite")`, `ANTHROPIC_CLASSES = ("haiku", "sonnet", "opus")` and `ALLOWED_STAGES = frozenset({"GA", "PUBLIC_PREVIEW"})`.
- [X] T006 Add the new settings to `backend/app/config.py` per contracts/configuration.md:
  - fields `wcl_model_discovery: str = "catalog"`, `wcl_gemini_classes: str = "pro:2,flash:2,flash-lite:2"` and `wcl_anthropic_classes: str = "haiku:1,sonnet:1,opus:1"`.
  - a property `model_discovery_mode` returning `"catalog"` or `"static"`. Any other value logs one WARNING and returns `"catalog"`.
  - properties `gemini_classes` / `anthropic_classes` that parse `name:count` into `list[ClassSetting]` in the given order. An unknown class name or a non-positive or non-integer count logs one WARNING and is skipped; an empty string gives `[]`.
  - Depends on T005.
- [X] T007 Change `discover_models` in `wcl_agent/models.py` to return a `ModelCatalog` instead of a dict, with static behaviour unchanged:
  - Add `mode: Literal["catalog","static"] = "static"`, `gemini_classes=()` and `anthropic_classes=()` keyword parameters. The catalog branch stays unimplemented until US1, so `mode="catalog"` raises `NotImplementedError` for now.
  - Static path: `source="static"` when something passes, otherwise `source="degraded"` with `degraded=True`. `classes` and `listed` are empty, and `fetched_at` is now in UTC.
  - Run impact on `discover_models` first (UNKNOWN; see the note at the top).
  - Depends on T004 and T005.
- [X] T008 Update the callers for the typed result:
  - In `backend/app/main.py::_boot._models`, read `discovery.models`, `.default` and `.degraded` into `app.state`, and change the step detail to `f"{len(d.models)} models ({d.source})"`.
  - Update the dict indexing in `backend/tests/test_models.py` and `backend/tests/test_guides_and_boot.py` to attribute access.
  - Run `uv run --extra test pytest -q backend/tests/test_models.py backend/tests/test_guides_and_boot.py`; it must pass.
  - Depends on T007.

**Checkpoint**: The app boots exactly as today. The full suite is green, and `wcl_agent/vertex.py` can list both catalogs.

---

## Phase 3: User Story 1 — The model picker shows current models without an operator edit (Priority: P1) 🎯 MVP

**Goal**: In catalog mode the dropdown shows the newest 2 Gemini models per class and the newest Claude model per class that pass a probe, in class order, with no per-model `.env` list.

**Independent Test**: In `discover_models(mode="catalog")`, monkeypatch `vertex.list_publisher_models` to return the T001 fixtures and make the probes all pass. Expect:
- `models == ["gemini-3.1-pro-preview", "gemini-2.5-pro", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", <newest haiku>, <newest sonnet>, <newest opus>]`
- `source == "catalog"`
- `default == "gemini-3.8-flash"` when `WCL_DEFAULT_MODEL` is not among them.

### Tests for User Story 1 ⚠️ (write first, must fail)

- [X] T009 [P] [US1] Classification tests in `backend/tests/test_models.py`, using the T001 fixtures:
  - `candidates_by_class` gives exactly the per-class candidate order from the plan's table.
  - EXPERIMENTAL entries, the non-chat models (TTS, image, live, embedding, `gemini-4-argon`, omni), dated previews (`…-preview-05-20`), `fable` and `claude-3-opus` are all dropped.
  - `flash-lite` is never classed as `flash`.
  - Versions compare numerically: `3.10 > 3.9` and `3 < 3.1`.
  - On a version tie, GA comes before preview.
  - `versionId` gives `claude-opus-5-5` for `default` and `claude-haiku-4-5@20251001` for a date.
  - An entry with no `launchStage` is kept.
  - **As built:** the US1–US3, US5 (T033/T034) and US6 tests live together in `backend/tests/test_model_discovery.py`; `test_models.py` / `test_guides_and_boot.py` keep the static-path tests (updated for T008).
- [X] T010 [P] [US1] Selection tests in `backend/tests/test_models.py`:
  - `pick_per_class` with all outcomes `passed` keeps 2 per Gemini class and 1 per Claude class, newest first.
  - `choose_default` returns the configured id if served, else the newest flash, else `models[0]`.
  - The served order is Gemini pro, flash, flash-lite, then Claude haiku, sonnet, opus.
- [X] T011 [US1] Catalog-path test in `backend/tests/test_models.py`. Monkeypatch `vertex.list_publisher_models` with the fixtures, and `_make_gemini_client` / `_make_anthropic_client` / `check_model` with an all-pass fake. Assert:
  - the Independent Test result above;
  - only the newest `keep + 2` candidates per class are probed (count the calls);
  - `listed` contains every callable fixture id;
  - one INFO line per class, e.g. `gemini flash: gemini-3.8-flash, gemini-3.7-flash`.

### Implementation for User Story 1

- [X] T012 [US1] Implement `classify(entry, classes) -> Candidate | None` and `candidates_by_class(entries, classes)` in `wcl_agent/models.py` per research R2:
  - Gemini regex: `^gemini-(\d+)(?:\.(\d+))?-(pro|flash-lite|flash)(-preview)?$`
  - Claude regex: `^claude-(haiku|sonnet|opus)-(\d+)(?:-(\d+))?$`
  - Stage allowlist: GA and PUBLIC_PREVIEW; an entry with no stage is kept.
  - `preview` is true for stage PUBLIC_PREVIEW or a `-preview` name.
  - Sort with key `(-major, -minor, preview)`.
  - The callable id gets `@version_id` only for Claude entries whose version is not `default`.
  - Only classes present in `classes` are returned.
- [X] T013 [US1] Implement `pick_per_class(candidates, outcomes, keep) -> ClassResult` and `choose_default(models, configured, classes) -> str` in `wcl_agent/models.py`. In this story the walk only keeps `passed` and moves past anything else. If nothing is kept, the reason is `no_candidates` when the class had no candidates and `failed` otherwise.
  - **As built:** the signature is `pick_per_class(setting: ClassSetting, candidates, outcomes)`, because a class with no candidates still needs its publisher and name for its `ClassResult`.
- [X] T014 [US1] Implement the catalog branch of `discover_models` in `wcl_agent/models.py`, replacing the T007 `NotImplementedError`:
  1. List `google` and `anthropic` concurrently with `_gather_threads`.
  2. Build the candidates.
  3. Take the newest `keep + 2` candidates per class.
  4. Probe all of them in one wave with `_gather_threads(…, max_workers=min(len(calls), 32))`. For now each probe is the existing bool probe mapped to `passed` / `failed`.
  5. Pick per class and concatenate in class-setting order (Gemini settings, then Anthropic).
  6. Log one INFO line per class.
  7. Fill `listed` and set `source="catalog"`.
  8. If nothing was kept, serve the degraded path, the same as the static one.
  - Static mode is unchanged.
- [X] T015 [US1] Wire catalog mode into `backend/app/main.py::_boot._models`. Pass `mode=settings.model_discovery_mode`, `gemini_classes=settings.gemini_classes` and `anthropic_classes=settings.anthropic_classes`, plus the existing static arguments, to `discover_models` (still through `asyncio.to_thread`, no cache yet).

**Checkpoint**: With live credentials, the boot log lists the per-class picks and `GET /api/models` serves them. T009–T011 pass, and the existing static tests still pass.

---

## Phase 4: User Story 2 — Only models that actually work are offered (Priority: P1)

**Goal**: Probes include a tool declaration. A 404/403 skips to an older version. A 429 that persists after one retry marks the whole class as "no quota".

**Independent Test**: Use fixture outcomes where `claude-haiku-5-5` is `not_enabled` and every sonnet candidate returns 429 twice. The result serves `claude-haiku-4-5@20251001`, serves no sonnet model, and logs `claude sonnet: no quota (429)`.

### Tests for User Story 2 ⚠️

- [X] T016 [P] [US2] `check_model` tests in `backend/tests/test_models.py`, using fake `google.genai.errors.APIError` (`code`) and `anthropic.APIStatusError` (`status_code`) exceptions, with `time.sleep` monkeypatched:
  - 404 and 403 give `not_enabled`;
  - 429 then 429 gives `no_quota`, after exactly one 2 s sleep;
  - 429 then success gives `passed`;
  - 400, 503, 529, a timeout and `RuntimeError` all give `failed`;
  - success gives `passed`.
- [X] T017 [P] [US2] Probe-payload tests in `backend/tests/test_models.py`, using fake clients that capture call kwargs:
  - The Gemini call's `config.tools` holds one function declaration named `ping`, with `max_output_tokens=1` and a 10 s timeout.
  - The Anthropic call passes `tools=[{"name": "ping", …}]`, with `max_tokens=1` and `timeout=10`.
  - The bool `_probe_gemini` / `_probe_anthropic` still return `True` / `False`.
- [X] T018 [P] [US2] Walk tests for `pick_per_class` in `backend/tests/test_models.py`:
  - `not_enabled` on the newest version falls through to the next (haiku-5-5 → haiku-4-5).
  - `no_quota` stops the class with reason `no_quota`; models kept before the stop are kept, and later passes are ignored.
  - All `not_enabled` gives reason `not_enabled`.
  - The INFO line for a no-quota class reads `claude sonnet: no quota (429)`.

### Implementation for User Story 2

- [X] T019 [US2] In `wcl_agent/models.py`, split the probes into raising calls `_call_gemini(client, model_id)` and `_call_anthropic(client, model_id)`, each with one dummy function declaration (research R3). The Gemini declaration is `types.Tool(function_declarations=[types.FunctionDeclaration(name="ping", description="Health check.", parameters=types.Schema(type="OBJECT", properties={}))])`; the Anthropic one is `{"name": "ping", "description": "Health check.", "input_schema": {"type": "object", "properties": {}}}`. Reimplement `_probe_gemini` / `_probe_anthropic` (signatures unchanged, `-> bool`) as wrappers around them. Run impact on `_probe_gemini` and `_probe_anthropic` first.
- [X] T020 [US2] Implement `check_model(call) -> ProbeOutcome` in `wcl_agent/models.py`:
  - A helper `_http_status(exc)` reads genai `APIError.code` or anthropic `APIStatusError.status_code`.
  - 404/403 give `not_enabled`.
  - 429 sleeps `_QUOTA_RETRY_S = 2` and retries once; a second 429 gives `no_quota`.
  - Anything else gives `failed`, logged at INFO with the model id and error.
  - Do not reuse `model_retry.is_rate_limited`: it also treats 503/529 as retryable (R3).
- [X] T021 [US2] In `pick_per_class` (`wcl_agent/models.py`), add the full walk rules:
  - `no_quota` stops the class.
  - A class with nothing kept records the reason of its first failure.
  - The per-class INFO line names the reason, e.g. `no quota (429)`, `not enabled`, `failed`, `no candidates`.
  - Switch the catalog branch of `discover_models` to `check_model(lambda: _call_gemini(...))` / `check_model(lambda: _call_anthropic(...))`.

**Checkpoint**: T016–T018 pass. Live, every Claude class logs "no quota (429)" until quota is granted, and no listed model fails on its first chat turn.

---

## Phase 5: User Story 3 — The dropdown is never empty (Priority: P1)

**Goal**: If either catalog listing fails, the app probes the static `.env` lists (source `fallback`, not degraded) and logs exactly one warning. If nothing passes, it serves the existing degraded list. Static mode is today's behaviour.

**Independent Test**: Make `vertex.list_publisher_models` raise `CatalogUnavailable` for `anthropic` only. The result has `source == "fallback"` and `degraded is False`, contains the static ids that passed, and caplog holds exactly one WARNING mentioning the catalog.

### Tests for User Story 3 ⚠️

- [X] T022 [P] [US3] Fallback tests in `backend/tests/test_models.py`:
  - Either publisher's listing raises `CatalogUnavailable` → static lists probed, `source="fallback"`, not degraded, one WARNING.
  - Listing fails and no static model passes → `source="degraded"`, `degraded=True`, `models == fallback_models`.
  - Catalog listing OK but nothing kept → degraded.
  - `mode="static"` → `list_publisher_models` is never called.
- [X] T023 [P] [US3] Settings tests in `backend/tests/test_models.py` (or a new `backend/tests/test_model_settings.py`):
  - `WCL_MODEL_DISCOVERY=bogus` → `catalog` plus one WARNING.
  - `WCL_GEMINI_CLASSES="pro:2,ultra:1,flash:0,flash-lite:x"` → only `pro:2`, plus warnings.
  - `WCL_ANTHROPIC_CLASSES=""` → `[]`.

### Implementation for User Story 3

- [X] T024 [US3] In the catalog branch of `discover_models` (`wcl_agent/models.py`), catch `CatalogUnavailable` from either listing. Log one WARNING (`model catalog unavailable (%s); probing the static lists`), run the existing static probe path, and relabel a non-degraded result as `source="fallback"`. Factor the static probe path into a private helper so both branches share it (Principle I).

**Checkpoint**: The quickstart §3 behaviour holds in tests. The dropdown is never empty in any test path.

---

## Phase 6: User Story 4 — All model calls run where current models are served (Priority: P2)

**Goal**: Every model call uses `model_location()` (default `global`), so `GOOGLE_CLOUD_LOCATION` can be `europe-west1`.

**Independent Test**: With `WCL_MODEL_LOCATION=global` and `GOOGLE_CLOUD_LOCATION=europe-west1`, every client factory (the genai client, sync and async Anthropic, `RetryingGemini`, `RetryingClaude`, the web-search sub-agent, suggestions, report synthesis and the guide LLM) is built with `global`. A source scan finds no `genai.Client(` or `AnthropicVertex(` outside `wcl_agent/vertex.py`.

### Tests for User Story 4 ⚠️

- [X] T025 [P] [US4] Location tests in `backend/tests/test_vertex.py`:
  - Monkeypatch `google.genai.Client`, `anthropic.AnthropicVertex` and `anthropic.AsyncAnthropicVertex` to capture kwargs, then assert `location` / `region == "global"` while `GOOGLE_CLOUD_LOCATION=europe-west1`, and the override when `WCL_MODEL_LOCATION=eu`.
  - `RetryingGemini(model="gemini-3.8-flash").client_kwargs == {"location": "global"}`.
  - `RetryingClaude(model="claude-opus-5-5")._anthropic_client` has region `global` and `max_retries == 0`.
  - The web-search tool built by `wcl_agent/agent.py::_build_web_search_tool` has a `Gemini` model with that `client_kwargs`.
  - A source-scan test fails if `genai.Client(` or `AnthropicVertex(` appears in `wcl_agent/` or `backend/app/` outside `wcl_agent/vertex.py`.

### Implementation for User Story 4

- [X] T026 [US4] Add the client factories to `wcl_agent/vertex.py` per contracts/model-discovery.md:
  - `genai_client()`: `genai.Client(vertexai=True, project=project_id(), location=model_location())`.
  - `anthropic_client()`: `AnthropicVertex(project_id=project_id(), region=model_location())`.
  - `async_anthropic_client(**kwargs)`: `AsyncAnthropicVertex(project_id=…, region=model_location(), **kwargs)`.
  - Import the SDKs lazily, as the call sites do today.
- [X] T027 [P] [US4] In `wcl_agent/models.py`, `_make_gemini_client` returns `vertex.genai_client()` and `_make_anthropic_client` returns `vertex.anthropic_client()`. Delete the `WCL_ANTHROPIC_REGION` / `GOOGLE_CLOUD_LOCATION` / `"us-east5"` lookup and the now-unused `os` import if nothing else uses it.
  - **As built:** the probe client is `vertex.anthropic_client(max_retries=0)`. The live check showed the SDK's own 429 retries stacking under `check_model`'s single retry.
- [X] T028 [P] [US4] In `wcl_agent/model_retry.py`:
  - `RetryingGemini` declares `client_kwargs: dict[str, Any] | None = Field(default_factory=lambda: {"location": model_location()})`.
  - `RetryingClaude._anthropic_client` returns `vertex.async_anthropic_client(default_headers=get_tracking_headers()).with_options(max_retries=0)`, taking `get_tracking_headers` from the same ADK module `anthropic_llm.py` uses. It still honours a preset `self.client`, as the ADK base does.
  - Update the `RetryingClaude` docstring.
  - Run impact on `RetryingGemini` and `RetryingClaude` first.
  - **As built:** `client_kwargs` defaults to `vertex.adk_client_kwargs()` = `{"vertexai": True, "location": model_location()}`; a location is only valid on Vertex, so `vertexai` is pinned too. The web-search sub-agent (T029) uses the same helper.
- [X] T029 [P] [US4] In `wcl_agent/agent.py::_build_web_search_tool`, pass `model=Gemini(model=model, client_kwargs={"location": model_location()})` (import `Gemini` from `google.adk.models.google_llm`) instead of the bare id. Keep it a plain `Gemini`, not a retrying one (R5). Run impact on `_build_web_search_tool` first.
- [X] T030 [P] [US4] In `backend/app/suggestions.py`, replace `genai.Client()` with `vertex.genai_client()` in the lazy client getter.
- [X] T031 [P] [US4] In `backend/app/services/report_synthesis.py`, replace `genai.Client()` with `vertex.genai_client()`.
- [X] T032 [P] [US4] In `backend/app/services/guide_pipeline/llm.py`, replace `genai.Client()` with `vertex.genai_client()` in the lazy client getter.

**Checkpoint**: T025 passes and the full suite is green. Live, chat with a tool call, web search, a guide, a report, the greeting and suggestions all work with `GOOGLE_CLOUD_LOCATION=europe-west1`.

---

## Phase 7: User Story 5 — Restarts are fast because the discovery result is shared (Priority: P2)

**Goal**: A catalog result is stored in Redis for 6 h, keyed on project, location and class settings. Restarts and other workers reuse it. Fallback and degraded results are never stored, and a Redis outage never blocks boot.

**Independent Test**: With fakeredis, two consecutive `_models` boot steps call `discover_models` once. The second step detail ends in `, cached`. A changed `WCL_GEMINI_CLASSES` makes it call again.

### Tests for User Story 5 ⚠️

- [X] T033 [P] [US5] Cache-family tests in `backend/tests/test_cache_families.py`:
  - `CacheFamily.MODEL_CATALOG` exists with `FamilyConfig(21600, 0.50)` and no memo.
  - `family_ttl` honours `WCL_CACHE_TTL_MODEL_CATALOG`.
  - `keys.model_catalog(project, location, sig)` gives `ext:models:v1:{project}:{location}:{sig}`.
  - `classes_signature` changes when any class, count or the stage allowlist changes, and is stable for equal input.
- [X] T034 [P] [US5] Boot-step cache tests in `backend/tests/test_guides_and_boot.py`, using fakeredis and a counting fake `discover_models`:
  - A miss stores the value; a hit skips discovery, and the detail reads `"6 models (catalog, cached)"`.
  - `fallback` and `degraded` results are not stored.
  - `WCL_CACHE_TTL_MODEL_CATALOG=0` stores nothing.
  - With Redis unreachable, discovery still runs and boot finishes.
  - `mode="static"` bypasses the cache entirely.

### Implementation for User Story 5

- [X] T035 [P] [US5] In `wcl_agent/cache.py`, add `CacheFamily.MODEL_CATALOG = "model_catalog"`, the `FAMILIES` entry `FamilyConfig(21600, 0.50)` and the key builder `keys.model_catalog(project, location, sig)` (research R6). Check that the admin cache-stats endpoint lists the new family without further changes.
- [X] T036 [P] [US5] In `wcl_agent/models.py`, add `classes_signature(gemini_classes, anthropic_classes) -> str`. Example output: `g=pro2.flash2.flash-lite2;a=haiku1.sonnet1.opus1;s=GA.PUBLIC_PREVIEW`.
- [X] T037 [US5] In `backend/app/main.py::_boot._models`, call discovery through the cache:
  - In catalog mode, call `get_or_load(CacheFamily.MODEL_CATALOG, keys.model_catalog(project_id() or "-", model_location(), classes_signature(...)), ModelCatalog, loader, ttl=...)`.
  - The loader sets a local `loaded = True` and runs `asyncio.to_thread(discover_models, …)`.
  - The `ttl` is `family_ttl(CacheFamily.MODEL_CATALOG)` when `v.source == "catalog" and not v.degraded`, else `0`.
  - In static mode, call `discover_models` directly.
  - Append `, cached` to the step detail when `loaded` stayed False.
  - Depends on T035 and T036.
  - **As built:** the step body is the module-level `backend/app/main.py::_load_models(app)` so it can be tested without the rest of `_boot`.

**Checkpoint**: T033 and T034 pass. Live, a second restart shows `(catalog, cached)` with no probe log lines.

---

## Phase 8: User Story 6 — Operators can see what was picked and why (Priority: P3)

**Goal**: Every boot (hit or miss) logs the per-class picks or reasons. A fixed-purpose model (guide, guide review, report, greeting) missing from the catalog is warned about without being changed.

**Independent Test**: Set `WCL_REPORT_MODEL=gemini-1.0-retired` and boot twice with fakeredis. Both boots log one WARNING naming `WCL_REPORT_MODEL` and one INFO line per configured class.

### Tests for User Story 6 ⚠️

- [X] T038 [P] [US6] Tests for `missing_fixed_models` in `backend/tests/test_models.py`:
  - Ids absent from `listed` are returned with their setting name.
  - `claude-haiku-4-5@20251001` matches a listed bare `claude-haiku-4-5`, and the reverse also holds.
  - An empty `listed` returns nothing (static or fallback source).
- [X] T039 [P] [US6] Boot-log tests in `backend/tests/test_guides_and_boot.py`, using caplog: on a cache hit, the per-class INFO lines are replayed from `ModelCatalog.classes`, and the fixed-purpose WARNING fires on both the miss and the hit boot.

### Implementation for User Story 6

- [X] T040 [US6] In `wcl_agent/models.py`:
  - Extract `log_class_results(classes: list[ClassResult])` from the per-class logging in `discover_models`. It is used by `discover_models` and on a cache hit.
  - Add a pure `missing_fixed_models(fixed: dict[str, str], listed: list[str]) -> list[tuple[str, str]]` that compares bare names (the text before `@`).
- [X] T041 [US6] In `backend/app/main.py::_boot._models`, after discovery:
  - Call `log_class_results(catalog.classes)` when the value came from the cache.
  - Log one WARNING per entry of `missing_fixed_models({"WCL_GUIDE_MODEL": settings.wcl_guide_model, "WCL_GUIDE_REVIEW_MODEL": settings.wcl_guide_review_model, "WCL_REPORT_MODEL": settings.wcl_report_model, "greeting": GREETING_MODEL}, catalog.listed)`, e.g. `"%s=%s is not in the model catalog; it may be retired"`.
  - Do not change any of those settings.
  - Depends on T037 and T040.

**Checkpoint**: The startup log alone explains every class and flags retired fixed-purpose ids (SC-006).

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T042 [P] Update `.env.example`:
  - Replace the model-selection comment block with one explaining catalog discovery and the static fallback.
  - Add `WCL_MODEL_DISCOVERY=catalog`, `WCL_GEMINI_CLASSES`, `WCL_ANTHROPIC_CLASSES`, `WCL_MODEL_LOCATION=global` and a commented `# WCL_CACHE_TTL_MODEL_CATALOG=21600`.
  - Set `GOOGLE_CLOUD_LOCATION=europe-west1`, with the region note from contracts/configuration.md.
  - Relabel `WCL_GEMINI_MODELS` / `WCL_ANTHROPIC_MODELS` / `WCL_MODELS` as static-mode and fallback lists.
- [X] T043 [P] Update `README.md`:
  - Rewrite the model discovery section: catalog mode, the class settings, a preview outranking an older GA model, the 6 h shared cache and how to clear it.
  - Explain why model calls use `global` (`europe-west1` serves only Gemini 2.5 and no Claude).
  - Add the Claude quota note: no Claude model appears until a per-class quota increase is granted in the Cloud console.
  - Replace the old `GOOGLE_CLOUD_LOCATION defaults to the global endpoint` line.
- [X] T044 [P] Update the `GOOGLE_CLOUD_LOCATION` mentions in `documentation/ai_guide.md` and `documentation/deployment.md` to the new split (`WCL_MODEL_LOCATION=global` for models, `europe-west1` for everything else).
- [X] T045 Run `uv run --extra test pytest -q` (full suite) and `npm run build --prefix frontend`. Both must pass. Record the counts in the delivery notes.
  - **Result:** 827 passed, 3 skipped, 1 deselected; the frontend build succeeds.
- [X] T046 Run the live check in `specs/016-live-model-discovery/quickstart.md` §2:
  - the per-class boot log;
  - `GET /api/models`;
  - a tool-using chat turn on `gemini-3.8-flash`;
  - guide, report, greeting and suggestions working with `GOOGLE_CLOUD_LOCATION=europe-west1`;
  - a cached restart.
  Note which Claude classes report "no quota". This needs live credentials; mark it open if they are unavailable.
  - **Result (in-process, 2026-10-18, GOOGLE_CLOUD_LOCATION=europe-west1):** the boot log matched quickstart §2: the six Gemini picks, default `gemini-3.8-flash`, and all three Claude classes `no quota (429)`. A chat turn with a `check_rate_limit` tool call, web search, the greeting, suggestions, report synthesis and a grounded guide call all succeeded. Against the compose Redis, boot 1 took 9.2 s `(catalog)` and boot 2 took 0.0 s `(catalog, cached)` with the class lines replayed; the key was deleted afterwards. Still open: a rebuilt backend container and `GET /api/models` / UI checks.
- [X] T047 Run the fallback check in quickstart.md §3 (unreachable catalog or bogus project): exactly one warning, and a non-empty dropdown.
  - **Result:** with the catalog host unreachable, there was exactly one `model catalog unavailable` warning and the result was `source=fallback` (not degraded, 5 static models). With a bogus project the listing still succeeds and every probe fails, so the result is `degraded` and the dropdown is still non-empty.
- [X] T048 Run `node .gitnexus/run.cjs detect-changes --scope all --repo .`. It must not be `partial` or `truncated`. Confirm the affected processes are limited to boot, model discovery and model client construction, then commit.
  - **Result:** 52 changed symbols, not partial or truncated. The `critical` rating comes from a false positive: `keys.metrics` is unchanged, and the new `keys.model_catalog` sits on its old line range. The real flows are boot, the guide-pipeline client and the web-search tool. **The commit is left to the user** (`/speckit-git-commit`).

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (T001)**: none. T001 is needed only by the US1–US3 tests.
- **Foundational (T002–T008)**: T002, T003 and T004 run in parallel. T005 → T006. T004 + T005 → T007 → T008. This phase blocks every story.
- **US1 (Phase 3)**: after Foundational. The MVP.
- **US2 (Phase 4)**: after US1 (it refines the probe and the walk US1 introduced).
- **US3 (Phase 5)**: after US1 (it adds a branch to the catalog path); independent of US2.
- **US4 (Phase 6)**: after Foundational only (it needs `vertex.py`). It can run alongside US1–US3, but T027 touches `wcl_agent/models.py`, so sequence T027 after whichever US1–US3 task is editing that file.
- **US5 (Phase 7)**: after US1 (a catalog result to cache).
- **US6 (Phase 8)**: after US5 (the hit path it replays on) and US1.
- **Polish (Phase 9)**: after all the stories wanted for the release.

### Story completion order

```text
Setup ─► Foundational ─┬─► US1 (MVP) ─┬─► US2
                       │              ├─► US3
                       │              └─► US5 ─► US6
                       └─► US4 (parallel track)
                                              └─► Polish
```

### Within each story

The tests come first and must fail. Then pure helpers, then the `discover_models` branch, then `main.py` wiring. Run `impact` before editing each existing symbol.

### Parallel opportunities

- Foundational: T002 (`vertex.py`), T003 (`test_vertex.py`) and T004 (`cache_models.py`).
- US1: tests T009 and T010.
- US2: tests T016, T017 and T018. They share `test_models.py`, so either add them as separate test functions in one sitting or split them into `test_model_probes.py`.
- US4: T027–T032 touch six different files and can all run together after T026.
- US5: T033/T034 (tests) and T035/T036 (cache and signature).
- Polish: T042, T043 and T044.
- Cross-story: US4 can run on its own track while US1→US2→US3 proceed.

---

## Parallel Example: User Story 4

```bash
# After T026 (factories in wcl_agent/vertex.py), switch every call site at once:
Task: "T027 [US4] models.py: _make_*_client use vertex factories; drop us-east5"
Task: "T028 [US4] model_retry.py: RetryingGemini client_kwargs; RetryingClaude client"
Task: "T029 [US4] agent.py: web-search sub-agent Gemini(client_kwargs=location)"
Task: "T030 [US4] suggestions.py: vertex.genai_client()"
Task: "T031 [US4] report_synthesis.py: vertex.genai_client()"
Task: "T032 [US4] guide_pipeline/llm.py: vertex.genai_client()"
```

## Parallel Example: User Story 1

```bash
Task: "T009 [US1] classification tests against the recorded fixtures"
Task: "T010 [US1] pick_per_class / choose_default / class order tests"
```

---

## Implementation Strategy

### MVP first (US1)

1. T001, then Foundational T002–T008. The app is unchanged and the suite is green.
2. US1, T009–T015. Catalog mode serves the newest passing models per class.
3. **Stop and validate**: run the live boot and confirm the Gemini picks match SC-005.

### Incremental delivery

1. **+US2**: tool-declaring probes and no-quota handling. Safe to enable in production from here, since no model is listed that fails its first turn.
2. **+US3**: a catalog outage falls back to the static lists.
3. **+US4**: the global model location for every client. After this, `GOOGLE_CLOUD_LOCATION` can move to `europe-west1`. Do not change that variable before US4 lands.
4. **+US5**: a shared 6 h cache with fast restarts.
5. **+US6**: per-class log replay and the fixed-purpose model warning.
6. **Polish**: docs, full suite, live and fallback checks, GitNexus `detect-changes`, commit.

### Notes

- `[P]` = different files, no dependency on an incomplete task.
- Keep `GOOGLE_CLOUD_LOCATION=global` in a local `.env` until US4 is merged. Only the `.env.example` default changes, in T042.
- Commit after each phase checkpoint. Every commit is preceded by GitNexus `detect-changes`.
