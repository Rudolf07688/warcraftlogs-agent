# Implementation Plan: Anthropic model discovery, provider label and discovery log fix

**Branch**: `033-anthropic-discovery-label` | **Date**: 2026-10-31 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/033-anthropic-discovery-label/spec.md`

## Summary

Feature 032 left the `anthropic` provider on static discovery. This feature gives it real
discovery: list the Anthropic Models API (paged), sort ids into haiku/sonnet/opus, probe with the
existing tool-carrying one-token call, keep the newest `count` per class. The listing is built in
`models.py` from `provider.anthropic_client()` (no new provider function). The same
`_discover_catalog` pipeline then serves both providers; only the listing, the id shape and the
class set differ. Also: the cached key gains the provider, `GET /api/models` gains `provider`,
the picker gets a read-only provider badge, an empty listing becomes a listing failure, and the
016 startup summary line is logged.

## Technical Context

**Language/Version**: Python 3.12 (FastAPI, asyncio), TypeScript/React (Vite)

**Primary Dependencies**: `anthropic` SDK (`client.models.list()` auto-pages), existing shadcn `Badge`/`StatusBadge`; no new dependencies

**Storage**: Redis/shared cache family `model_catalog` (key gains the provider); no DB, no migration

**Testing**: pytest with fakes (no live LLM); vitest + `npm run build` for the frontend

**Target Platform**: Linux server, browser down to 390px

**Project Type**: web service + SPA

**Performance Goals**: discovery stays one concurrent probe wave (cost <= one probe timeout)

**Constraints**: no key in logs/responses; Vertex behaviour unchanged

**Scale/Scope**: 3 classes x a few versions; ~10 probes at boot

## Design decisions (research folded in; see research.md)

1. **Id shape.** Vertex dated Claude ids are `name@YYYYMMDD`, the API's are `name-YYYYMMDD`. A second
   pattern `^claude-(haiku|sonnet|opus)-(\d+)(?:-(\d{1,2}))?(?:-(\d{8}))?$` classifies API ids and
   aliases (minor is 1-2 digits so a date is never read as a minor). `model_class`, `is_catalog_id`
   and `classify` pick the pattern by the active provider; each provider rejects the other's shape.
   This is also what makes the 429 sibling path work for API ids: `sibling_model` and
   `class_label` go through `model_class`, and `generate_with_fallback`/`is_rate_limited`/
   `retry_after_hint` already handle Anthropic 429/529 and are provider-agnostic, so
   `model_retry.py` needs tests, not edits.
2. **Listing.** `_list_anthropic_api()` in `models.py` iterates `provider.anthropic_client().models.list()`
   and yields `CatalogEntry(publisher="anthropic", name=<base id>, version_id=<date|"default">, stage=None)`.
   Per model, the alias (undated) is preferred over a dated twin (Q1). Any SDK error raises
   `CatalogUnavailable`. `_list_catalog()` branches on the active provider: Vertex lists both
   publishers as today; Anthropic lists only the API. **Zero entries raise `CatalogUnavailable`
   in both branches** (sc-159), so the existing fallback runs.
3. **Probes.** `_make_anthropic_client` builds via `provider.anthropic_client(max_retries=0)`;
   `_make_gemini_client` via `provider.genai_client()`. The `vertex.anthropic_client` forwarder is
   deleted (and `genai_client` too if 035 has not merged by then).
4. **No Gemini under anthropic.** `_load_models` passes no Gemini classes/ids under `anthropic`
   (`settings.gemini_classes` is empty there; `gemini_models` is already filtered by `served_ids`).
   `discover_models` no longer demotes catalog to static for the Anthropic provider, only for a
   Vertex-less Gemini setup as today.
5. **Cache.** `keys.model_catalog(provider, project, location, sig)` -> `ext:models:v2:{provider}:...`
   (old v1 keys expire by TTL, no migration). Under `anthropic` project/location are `-`. The
   cached-ids check (`is_catalog_id`) is provider-shaped.
6. **Response + label.** (Label is a shadcn `Badge` via the MCP, `registries: ["@shadcn"]`, audit after add; 390px check in headless Chrome on port 18033.) `ModelsResponse.provider: Literal["vertex","anthropic"] = "vertex"`
   (additive); the handler fills it from `provider.active_provider()`. `getModels()` type gains
   `provider?`; `App.tsx` keeps it in state and passes it to `ModelSelect`, which shows the existing
   `StatusBadge` ("Vertex AI" / "Anthropic API"), hidden label text never includes secrets.
7. **Startup log (sc-159).** `_load_models` logs one summary line `model discovery: N models from
   <source> (<provider>)` on every boot (fresh or cached), plus the existing per-class lines.
7b. **Q3.** `generate_with_retry` already raises `ModelRateLimited` when a hint exceeds the wait budget, and `generate_with_fallback` then switches and logs. Test only.
8. **Q2 deviation.** Ranking is the numeric version compare already used; `created_at` is not used
   (alias/date de-dup removes the only tie it would break). Noted, no scope added.

## Constitution Check

| Principle | Status |
|---|---|
| I Reuse-first | Pass: one pipeline for both providers; reuses `StatusBadge`, retry/sibling code, `check_model`. |
| II Small verified steps | Pass: backend slices each with pytest, then frontend with build + vitest. |
| III Simplicity | Pass: no new setting, no provider.py listing function, no created_at ranking. One tiny `provider.py` edit is requested (see below). |
| IV Typed contracts | Pass: `ModelsResponse.provider` is a `Literal`; `CatalogEntry`/`ModelCatalog` reused. |
| V Async FastAPI | Pass: blocking SDK calls stay in `asyncio.to_thread` as today. |
| VI GitNexus | Pass: impact below; detect-changes before commit. |
| VII shadcn | Pass: existing `StatusBadge`/`ui/badge`; MCP search + audit run before the UI change. |
| VIII Backlog sync | Pass: stories In Progress; scrum master moves later states. |

**Complexity Tracking**: none. One deviation to approve: `provider.has_model_catalog()` returns
True for both providers (one-line edit in `provider.py`; its only user is `config.py`).

## GitNexus impact (index rebuilt in this worktree)

| Symbol | Risk | Notes |
|---|---|---|
| `discover_models` | UNKNOWN | no resolved callers; text search: only `main._load_models` and tests call it |
| `_load_models` | LOW | called by `_boot` (lifespan startup) |
| `sibling_model` | LOW | called by `model_state.fallback_model_for` (ws chat turn) |
| `model_class` | LOW | `class_label`, `sibling_model`; chat process |
| `ModelsResponse` | HIGH (file-level import edges, 19 importers of `schemas.py`) | change is one additive optional field; no importer breaks |
| `model_retry.py` | n/a | not edited |

## Project Structure

Source: `wcl_agent/llm/models.py`, `wcl_agent/llm/provider.py` (one function), `wcl_agent/llm/vertex.py`
(forwarder removal), `wcl_agent/cache/cache.py` (key), `backend/app/main.py`, `backend/app/config.py`,
`backend/app/schemas.py`, `backend/app/api/models.py`; frontend `components/ModelSelect.tsx`,
`api/restClient.ts`, `App.tsx`. Tests and docs below.

## Files to create or modify (grant request)

Modify: `wcl_agent/llm/models.py`, `wcl_agent/llm/provider.py` (has_model_catalog only),
`wcl_agent/llm/vertex.py`, `wcl_agent/cache/cache.py`, `backend/app/main.py`, `backend/app/config.py`,
`backend/app/schemas.py`, `backend/app/api/models.py`, `frontend/src/components/ModelSelect.tsx`,
`frontend/src/api/restClient.ts`, `frontend/src/App.tsx` (needs your OK),
`.env.example`, `backend/tests/test_model_discovery.py`, `backend/tests/test_vertex.py`,
`backend/tests/test_api.py` (provider field), `frontend/src/App.test.tsx` and
`frontend/src/App.modelFallback.test.tsx` only if their mocks need `provider`.
Create: `backend/tests/test_anthropic_discovery.py`, `frontend/src/components/ModelSelect.test.tsx`,
`specs/033-anthropic-discovery-label/**`.
README.md: separate (dev-b-035's): one line in the model-discovery section that `anthropic` now discovers via the Models API, and one on the provider label.
