# Plan: live model discovery from the Vertex Model Garden catalog

## Context

**Today.** The chat model dropdown comes from a fixed list in `.env`:
- `WCL_GEMINI_MODELS` and `WCL_ANTHROPIC_MODELS`.
- At startup, `wcl_agent/llm/models.py::discover_models` sends each id a one-token "hello" and keeps the ones that answer.
- It stores the result on `app.state`, read through `backend/app/model_state.py::get_model_state`.
- `GET /api/models` serves it, and `frontend/src/App.tsx` renders it.

**The problem.** Every model release needs an `.env` edit and a restart before players can pick it.

**The goal.** The dropdown always shows **the latest two Gemini models of each class** and **the latest *enabled* Claude model of each class**, taken from Vertex's own catalog and confirmed by a live call. The API shape (`{models, default, degraded}`), `app.state`, the endpoint and the frontend stay as they are.

**What it would show today:**

| Publisher | Class | Kept |
|---|---|---|
| Gemini | pro | `gemini-3.1-pro-preview`, `gemini-2.5-pro` (there is no `gemini-3-pro` text model in the catalog) |
| Gemini | flash | `gemini-3.8-flash`, `gemini-3.7-flash` |
| Gemini | flash-lite | `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite` |
| Claude | haiku | latest that answers (expected `claude-haiku-4-5`) |
| Claude | sonnet | latest that answers (expected `claude-sonnet-5-5`) |
| Claude | opus | latest that answers (expected `claude-opus-5-5`) |

## Regions

| Use | Location |
|---|---|
| All model calls: chat dropdown, guides, reports, greeting, suggestions, discovery probes | **`global`**, via a new `WCL_MODEL_LOCATION` (default `global`) |
| Catalog listing | the global endpoint `https://aiplatform.googleapis.com/v1beta1/...` |
| Anything else regional; the default for `GOOGLE_CLOUD_LOCATION` | **`europe-west1`** |

**Why model calls can't use `europe-west1`** (tested live 2026-10-18):
- **`europe-west1`:** serves only Gemini 2.5. `gemini-3.8-flash`, `gemini-3.1-pro-preview` and every Claude model return 404.
- **`eu` multi-region:** serves `gemini-3.8-flash` but not `3.1-pro-preview`.
- **`global`:** serves all of them.
- **Regional catalogs differ too:** `europe-west1` lists 11 Google models and only `claude-3-opus`.

**How:** add one helper, `wcl_agent/llm/vertex.py::model_location()`. Every client that calls a model uses it instead of reading `GOOGLE_CLOUD_LOCATION`:
- `genai.Client(vertexai=True, location=...)` in `guide_pipeline/llm.py`, `report_synthesis.py`, `suggestions.py` and `wcl_agent/llm/models.py`;
- `AnthropicVertex(region=...)` in `wcl_agent/llm/models.py`;
- the ADK model subclasses `RetryingGemini` / `RetryingClaude` in `wcl_agent/llm/model_retry.py`, which override their client construction.

The `us-east5` fallback in `_make_anthropic_client` goes away.

## Catalog facts this design rests on (checked live, 2026-10-18)

- **Google catalog:** REST `GET https://aiplatform.googleapis.com/v1beta1/publishers/google/models` returns 30 Gemini entries, each with `launchStage` (GA / PUBLIC_PREVIEW / EXPERIMENTAL) and `versionId`. The SDK's `models.list` returns the same names without stage, so the plan uses REST for both publishers: google-auth `AuthorizedSession` with an `x-goog-user-project` header.
- **Anthropic catalog:** `.../publishers/anthropic/models` returns 13 entries (haiku-4-5 … opus-5-5, sonnet-5-5, haiku-5-5, fable-5-1). A `versionId` of `default` gives a bare id such as `claude-opus-5-5`; a dated one gives `claude-haiku-4-5@20251001`.
- **Listing is not access.** Only a call shows what the project can use. Two kinds of failure:
  - **404:** the model is not served or not enabled.
  - **429 `RESOURCE_EXHAUSTED` … `per_base_model with base model: anthropic-claude-sonnet`:** the quota is **per class, not per version**. Today every Claude call fails this way, because the project has no Claude quota yet. **No Claude model will appear until a quota increase is granted** in the Cloud console.

## Design

### Pipeline (startup, inside the existing `models` boot step)
1. **List** both catalogs from the global endpoint. Follow `nextPageToken`; 10 s per call; the two calls run concurrently.
2. **Classify** each entry into `(publisher, class, version, stage)` and drop anything outside the configured classes:
   - **Gemini pattern:** `gemini-<major>[.<minor>]-<class>[-preview]`, with class ∈ `pro`, `flash`, `flash-lite`. This match drops TTS, image, live, embedding, transcribe and translate models, `gemini-4-argon` and `omni`.
   - **Claude pattern:** `claude-<class>-<major>[-<minor>]`, with class ∈ `haiku`, `sonnet`, `opus`. This drops `fable` and the legacy `claude-3-opus`.
   - **Stage:** `EXPERIMENTAL` is dropped. GA and PUBLIC_PREVIEW stay.
   - **Ordering:** newest version first. When versions tie, GA beats `-preview`.
3. **Probe newest first, per class.** For each class, take the newest `keep + 2` candidates and probe them concurrently (the existing `_gather_threads`, 10 s timeout). Then keep the first `keep` that pass, in version order.
   - **Counts:** `keep` is 2 per Gemini class and 1 per Claude class. That is about 12 Gemini and about 9 Claude probes, all concurrent: roughly one 10 s wave at worst.
   - **The probe** is today's one-token call plus **one dummy function declaration**. A model that cannot call tools, which the chat agent needs, fails here instead of in the first chat turn.
   - **Failure handling:**
     - A 404 or 403 means not enabled; move on to the next version.
     - A 429 is retried once after 2 s. If it persists, **the class is marked "no quota"** and its other versions are skipped, because quota is per class.
4. **Default model:** `WCL_DEFAULT_MODEL` if it survived, otherwise the newest `flash`.
5. **Serve:** in class order (Gemini pro, flash, flash-lite, then Claude haiku, sonnet, opus), in the same return dict as today.

### Config (`backend/app/config.py`, `.env.example`)
- `WCL_MODEL_DISCOVERY=catalog|static`, default `catalog`. `static` keeps today's `.env` lists.
- `WCL_GEMINI_CLASSES=pro:2,flash:2,flash-lite:2`
- `WCL_ANTHROPIC_CLASSES=haiku:1,sonnet:1,opus:1`
- `WCL_MODEL_LOCATION=global`; `GOOGLE_CLOUD_LOCATION=europe-west1` in `.env.example`.
- `WCL_MODEL_DISCOVERY_CACHE_S=21600` (6 h; `0` turns the cache off).
- `WCL_GEMINI_MODELS` / `WCL_ANTHROPIC_MODELS` / `WCL_MODELS` stay as the fallback lists.

### Fallbacks (never an empty dropdown, FR-016)
- **The listing fails** (network, 403, timeout): probe the static `.env` lists exactly as today and log one warning.
- **Nothing passes:** today's degraded path, which serves `WCL_MODELS` with the "degraded" notice.

### Caching
- A new Redis family `MODEL_CATALOG` (`wcl_agent/cache/cache.py` and `cache_models.py`) holds the final result, loaded through the existing `get_or_load`.
- The key covers the class settings, location and project, so a config change misses it.
- Every restart and every worker reuses it for 6 h instead of re-probing.
- If Redis is down, `get_or_load` already computes the result without it.

### Warning for fixed-purpose models
After a successful listing, log a warning for each of these that is not in the catalog:
- `WCL_GUIDE_MODEL` and `WCL_GUIDE_REVIEW_MODEL`;
- `WCL_REPORT_MODEL`;
- the greeting model.

They are not taken from the dropdown and are not changed. The warning only catches a retired id early.

### Boot log
For example:
- the step detail reads `models: 6 models (catalog)`;
- one info line per class, e.g. `claude sonnet: no quota (429)` or `gemini pro: gemini-3.1-pro-preview, gemini-2.5-pro`.

## Files

| File | Change |
|---|---|
| `wcl_agent/llm/vertex.py` (new) | `model_location()`, `project_id()`, and `list_publisher_models(publisher)` (REST, paginated). |
| `wcl_agent/llm/models.py` | Add `classify(entry)`, `candidates_by_class(entries, classes)` and `pick_per_class(candidates, probe, keep)`. These are pure, apart from the injected probe. Add the tool-declaring probes, 404/429 classification, `discover_models(mode=...)` and the catalog path. The static path is unchanged. |
| `wcl_agent/llm/model_retry.py` | `RetryingGemini` / `RetryingClaude` build their clients with `model_location()`. |
| `backend/app/services/guide_pipeline/llm.py`, `services/report_synthesis.py`, `suggestions.py` | `genai.Client(vertexai=True, location=model_location())`. |
| `wcl_agent/cache/cache.py`, `wcl_agent/cache/cache_models.py` | Add the `MODEL_CATALOG` family and the `ModelCatalog` model (`models`, `default`, `degraded`, `source`, `classes`, `fetched_at`). |
| `backend/app/config.py`, `backend/app/main.py` (`_models` step) | Settings; call `discover_models` in catalog mode through the cache; the warning for fixed-purpose models. |
| `.env.example`, `README.md` | New settings; the region note; the Claude quota note. |

Reused unchanged: `_gather_threads`, `model_state.get_model_state` / `is_valid_model`, `api/models.py`, `ModelsResponse`, `is_anthropic_model`, the ADK `LLMRegistry` Claude registration, and the frontend.

## Risks
- **No Claude quota today,** so Claude classes come back empty until the increase is granted. That is correct behaviour, and the boot log says why.
- **A preview model can beat an older GA model of the same class** (`gemini-3.1-pro-preview` over `gemini-2.5-pro`). That is what was asked for. Setting the stage allowlist to GA-only removes previews.
- **Old conversations** whose model drops out: `is_valid_model` already rejects them, as when `.env` changes today.
- **Startup time:** about one probe wave (≤10 s) on a cache miss; nothing on a hit.

## Verification
1. **Unit tests** (`backend/tests/test_models.py`; no network). Use recorded fixtures of today's two catalog responses (`backend/tests/fixtures/model_catalog_*.json`):
   - classification gives exactly the per-class candidates above;
   - `keep` = 2 / 1 is honoured;
   - newer versions that 404 are skipped down to an older one (haiku-5-5 → haiku-4-5);
   - a 429 skips the whole class after one retry;
   - EXPERIMENTAL and preview tie-breaks;
   - `versionId` handling, for both bare and `@date` ids;
   - a listing failure falls back to the static lists without being degraded;
   - nothing passing is degraded;
   - the default falls back to the newest flash;
   - cache hit, cache miss, and `cache_s=0`;
   - the probe sends a tool declaration;
   - `model_location()` is used by every client factory;
   - the existing static-mode tests still pass.
2. **Live check:** start the backend:
   - the boot log shows the per-class picks;
   - `GET /api/models` lists them;
   - one Gemini chat turn with a tool call works on `global`;
   - after the Claude quota is granted, a restart (with the cache cleared) shows haiku, sonnet and opus.
3. **Fallback check:** with an unreachable endpoint or a bogus project, startup serves the static list and logs a single warning.
4. Run `uv run --directory backend pytest` and `npm run build`, then GitNexus `detect-changes` before committing.
