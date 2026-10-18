# Implementation Plan: Live Model Discovery

**Branch**: `016-live-model-discovery` | **Date**: 2026-10-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/016-live-model-discovery/spec.md`. Source
design: `documentation/live_model_probe.md`.

## Summary

The chat model dropdown is built at startup from Vertex's own model catalog instead of
the hand-kept `.env` lists. The app lists the Google and Anthropic publisher catalogs
from the global endpoint. It sorts each entry into a class (Gemini pro, flash and
flash-lite; Claude haiku, sonnet and opus), then makes a one-token call with a tool
declaration to the newest few versions of each class, all at once. It keeps the newest
passing 2 per Gemini class and 1 per Claude class.

A 404 or 403 skips to an older version. A persistent 429 marks the whole class "no
quota". The result is stored for 6 h in the shared Redis cache (feature 014). If the
listing fails, the app falls back to today's static probing, and if nothing passes, to
today's degraded list.

Every model call (chat, web search, guides, reports, greeting, suggestions, probes) moves
to one `WCL_MODEL_LOCATION` (default `global`), so `GOOGLE_CLOUD_LOCATION` can default to
`europe-west1`. `GET /api/models`, `app.state`, `get_model_state` and the frontend are
unchanged.

## Technical Context

**Language/Version**: Python 3.14 (backend, `wcl_agent`). No frontend change.

**Primary Dependencies**:
- FastAPI and asyncio;
- google-adk 2.10, using `Gemini.client_kwargs` and an override of `Claude._anthropic_client`;
- google-genai 2.25, anthropic 1.11 (`AnthropicVertex`, `region="global"`);
- google-auth 2.59 with `requests` 2.34 (`AuthorizedSession` for the REST catalog);
- redis 8 through the existing `wcl_agent.cache.get_or_load`.

No new dependency.

**Storage**: Redis, through a new cache family `model_catalog` (6 h, key
`ext:models:v1:{project}:{location}:{classes-sig}`). No database change.

**Testing**: pytest (`uv run --extra test pytest`). Recorded catalog fixtures in
`backend/tests/fixtures/`, fake probes and fakeredis. No network in tests.

**Target Platform**: Linux containers (docker compose) and local `uv run`.

**Project Type**: Web service (FastAPI backend + React frontend); backend-only change.

**Performance Goals**:
- Cache miss: about one 10 s probe wave (≤ ~22 s with a 429 retry) on top of two
  concurrent listings (≤ 10 s each).
- Cache hit: no listing and no probes (SC-004).

**Constraints**:
- The dropdown is never empty (FR-016).
- Probes run off the event loop (`asyncio.to_thread`, Principle V).
- Every model call uses `model_location()` (FR-017).
- Fallback and degraded results are never cached.

**Scale/Scope**:
- About 43 catalog entries and about 21 concurrent probes per cache miss.
- Roughly 9 files touched, 1 new module, about 15 new tests.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. DRY & reuse | ✅ | Reuses `_gather_threads`, `get_or_load`, the family TTL override (`WCL_CACHE_TTL_MODEL_CATALOG` instead of the source doc's separate `WCL_MODEL_DISCOVERY_CACHE_S`), `get_model_state`, `ModelsResponse` and the static probe path. The location logic is centralised in `vertex.py`, replacing four `genai.Client()` sites, two Anthropic client sites and the env reads ADK would otherwise do. |
| II. Step-wise delivery | ✅ | Slices: (1) `vertex.py` and the client switch to `model_location()`; (2) pure classify/pick plus tests; (3) probe outcomes and the catalog path in `discover_models`; (4) cache family and boot step; (5) warnings, docs, live check. Each slice is testable on its own. |
| III. Simplicity | ✅ | One new module and plain functions. No scheduler or background refresh: the result refreshes at restart after the TTL. No per-provider location and no GA-only switch, because neither is needed now. |
| IV. Typed contracts | ✅ | `CatalogEntry`, `ClassSetting`, `Candidate` are dataclasses. `ModelCatalog` and `ClassResult` are Pydantic, since they cross Redis. `discover_models` returns `ModelCatalog` instead of a plain dict. |
| V. Async backend | ✅ | Discovery stays blocking inside `asyncio.to_thread`. The cache read and write are async through `get_or_load`. |
| VI. GitNexus | ✅ | `impact` was run upstream: `_gather_threads` LOW and `_make_anthropic_client` LOW. `discover_models` came back **UNKNOWN** (no resolved callers); a text search shows its only callers are the `backend/app/main.py::_boot._models` step and `backend/tests/test_models.py` / `test_guides_and_boot.py`. Re-run `impact` before each symbol edit and `detect-changes` before committing. |
| VII. shadcn UI | N/A | No frontend change. |

**Result**: PASS. Nothing needs justifying under Complexity Tracking.

**Post-design re-check (after Phase 1)**: PASS. The design adds no dependency or service,
and it removes a setting (`WCL_ANTHROPIC_REGION`) rather than adding a second lifetime
setting.

## Design decisions (details in [research.md](research.md))

1. **Catalog listing** (R1): REST `v1beta1` global endpoint, `AuthorizedSession`,
   paginated, 10 s per request, both publishers concurrently. If either listing fails,
   the result is `fallback` (static lists probed, not degraded, one warning).
2. **Classification** (R2): anchored name patterns; `(major, minor)` integer versions;
   GA and PUBLIC_PREVIEW kept, a missing stage kept; GA beats preview on a tie;
   Claude ids get `@versionId` unless the version is `default`.
3. **Probe** (R3): today's one-token call plus one dummy function declaration on both
   paths. Catalog path outcomes: 404/403 → `not_enabled`; 429 → retry once after 2 s →
   `no_quota`; anything else → `failed`. The static `_probe_*` functions keep their `bool`
   signature.
4. **Pick** (R4): the newest `keep + 2` per class, all classes in one concurrent wave
   (`max_workers` raised for this path); walk in version order; `no_quota` stops the class.
5. **Location** (R5): `wcl_agent/vertex.py` is the only place model clients are built.
   This includes `RetryingGemini` (through `client_kwargs`), `RetryingClaude` (its own
   `AsyncAnthropicVertex`) and the **web-search sub-agent**, which the source doc missed.
   `WCL_ANTHROPIC_REGION` and the `us-east5` fallback are removed.
6. **Cache** (R6): family `model_catalog`, 6 h. Only `source == "catalog"` results are
   stored. The key covers project, location, class settings and the stage allowlist.
7. **Fixed-purpose warning** (R7): `ModelCatalog.listed` keeps the catalog ids, so the
   warning fires on cache hits too.
8. **Default** (FR-013): the configured default if served, else the newest flash, else
   the first model.

## Project Structure

### Documentation (this feature)

```text
specs/016-live-model-discovery/
├── plan.md              # this file
├── research.md          # Phase 0: R1–R9
├── data-model.md        # Phase 1: entities, invariants, discovery states
├── quickstart.md        # Phase 1: tests, live check, fallback check
├── contracts/
│   ├── model-discovery.md   # internal Python interface + unchanged GET /api/models
│   └── configuration.md     # env settings: new, changed, removed
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
wcl_agent/
├── vertex.py            # NEW: model_location, project_id, client factories, list_publisher_models
├── models.py            # classify / candidates_by_class / pick_per_class / choose_default,
│                        #   check_model + tool-declaring probes, discover_models(mode=…) → ModelCatalog
├── model_retry.py       # RetryingGemini client_kwargs location; RetryingClaude client from vertex
├── agent.py             # web-search sub-agent: Gemini(model, client_kwargs={"location": …})
├── cache.py             # CacheFamily.MODEL_CATALOG, FamilyConfig, keys.model_catalog
└── cache_models.py      # ClassResult, ModelCatalog

backend/app/
├── config.py            # wcl_model_discovery, wcl_gemini_classes, wcl_anthropic_classes (+ parsed properties)
├── main.py              # _models step: catalog mode via get_or_load; per-class log replay; fixed-model warning
├── suggestions.py       # vertex.genai_client()
└── services/
    ├── report_synthesis.py      # vertex.genai_client()
    └── guide_pipeline/llm.py    # vertex.genai_client()

backend/tests/
├── fixtures/model_catalog_google.json      # NEW: recorded listing
├── fixtures/model_catalog_anthropic.json   # NEW: recorded listing
├── test_models.py       # extended: catalog path, pick, outcomes, default, fallback, degraded
├── test_vertex.py       # NEW: location factories, pagination, CatalogUnavailable
├── test_guides_and_boot.py  # boot step: cache hit/miss/ttl 0, static mode untouched
└── test_cache_families.py   # MODEL_CATALOG family/key rules

.env.example, README.md, documentation/ai_guide.md, documentation/deployment.md
                         # new settings, region note, Claude quota note
```

**Structure Decision**: The existing web-app layout is kept. Discovery logic stays in the
standalone `wcl_agent` package, which reads its own settings from the environment like
`cache.py` does. The backend passes in the class settings and owns the boot step and the
cache call. No frontend files change.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| No Claude quota today, so no Claude models are served | Correct behaviour. The boot log names "no quota" per class, and the README explains how to request the quota. |
| A preview model outranks an older GA model | As requested (spec Assumptions). Documented in the README. |
| A catalog response changes shape | Parsing failures raise `CatalogUnavailable` → `fallback` with one warning. The fixtures pin today's shape. |
| A model that passed discovery is retired within the 6 h cache window | The chat turn fails as it would today. Lower `WCL_CACHE_TTL_MODEL_CATALOG` or clear the key and restart. |
| Moving `GOOGLE_CLOUD_LOCATION` to `europe-west1` breaks a missed client | The location test asserts every factory. The live check covers chat with tools, web search, guides, reports, greeting and suggestions. |
| Old conversations reference a dropped model | `is_valid_model` already rejects them, as when `.env` changes today. |

## Complexity Tracking

No constitution violations. Nothing to justify.
