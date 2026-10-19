# Research: Live Model Discovery

Phase 0 for [plan.md](plan.md). Each section: Decision / Rationale / Alternatives. Catalog
facts come from the live checks recorded in `documentation/live_model_probe.md`
(2026-10-18); code facts were read from the repo and the installed packages
(google-adk 2.10.0, google-genai 2.25.0, anthropic 1.11.0, google-auth 2.59.0).

## R1. How to list the catalog

**Decision**: REST `GET https://aiplatform.googleapis.com/v1beta1/publishers/{google|anthropic}/models`
through `google.auth.transport.requests.AuthorizedSession` (ADC credentials, `cloud-platform`
scope), header `x-goog-user-project: <project>`, `pageSize=100`, following
`nextPageToken`, `timeout=10` per page. The two publishers are listed concurrently with
the existing `_gather_threads`. Fields read per entry: `name` (last path segment is the
model name), `versionId`, `launchStage`.

**Rationale**: Only the REST listing returns `launchStage`; the genai SDK's `models.list`
returns names without a stage, and the Anthropic SDK has no listing. One code path for
both publishers. `requests` 2.34 and google-auth are already installed (no new
dependency). Discovery already runs off the event loop (`asyncio.to_thread`), so a
blocking session is fine (Principle V).

**Alternatives**: genai `models.list` (no stage, Google only); httpx with a manually
refreshed token (more code, same result); regional catalog endpoints (rejected: regional
catalogs differ, `europe-west1` lists only 11 Google models).

## R2. Classification rules

**Decision**: Anchored patterns on the model name:

- Gemini: `^gemini-(\d+)(?:\.(\d+))?-(pro|flash-lite|flash)(-preview)?$`
- Claude: `^claude-(haiku|sonnet|opus)-(\d+)(?:-(\d+))?$`

The version becomes an `(major, minor)` integer tuple, with a missing minor read as `0`,
so `3.10 > 3.9` and `3 < 3.1`. A class is kept only if it is configured. Stage allowlist:
`GA`, `PUBLIC_PREVIEW`. `EXPERIMENTAL` and any other stated stage are dropped. An entry
with no `launchStage` is kept, because the live call decides. An entry is a "preview" when
its stage is `PUBLIC_PREVIEW` or its name ends in `-preview`. Sort key per class:
`(version desc, GA before preview)`.

Callable id: Gemini uses the bare name. Claude uses the bare name when `versionId` is
missing or `default`, otherwise `name@versionId` (`claude-haiku-4-5@20251001`).

**Rationale**: The anchors drop TTS, image, live, embedding, transcribe and translate
models, `gemini-4-argon`, `omni`, dated previews (`…-preview-05-20`), `fable` and the
legacy `claude-3-opus` (class before version) with no deny-list to maintain.
`flash-lite` comes before `flash` in the alternation so it is never read as `flash`.

**Alternatives**: a deny-list of suffixes (has to change with every new modality);
sorting on the catalog's `versionId` (it is a release tag, not a model generation).

## R3. The probe and how failures are classified

**Decision**: Split today's probe into a raising call and wrappers:

- `_call_gemini(client, model_id)` / `_call_anthropic(client, model_id)` send the
  one-token "hello" plus one dummy function declaration (`ping`, no parameters). Gemini
  uses `types.Tool(function_declarations=[…])` in `GenerateContentConfig`. Anthropic uses
  `tools=[{"name": "ping", "input_schema": {"type": "object", "properties": {}}}]`. Both
  keep the 10 s timeout (`PROBE_TIMEOUT_S`).
- `_probe_gemini` / `_probe_anthropic` (static path) keep their `-> bool` signature and
  wrap the call, so the static path and its tests stay unchanged apart from the added tool
  declaration.
- `check_model(call) -> ProbeOutcome` (catalog path) runs the call and classifies the
  error by HTTP status: genai `APIError.code`, anthropic `APIStatusError.status_code`.
  - `404` / `403` → `NOT_ENABLED`
  - `429` → sleep 2 s, retry once; still `429` → `NO_QUOTA`
  - a transient error (any 5xx such as `504 DEADLINE_EXCEEDED` / `503` / `529`, a
    timeout, a dropped connection) → retry once at once; still failing → `FAILED`
    (added 2026-10-19: the first call to a newly released model can run past the 10 s
    probe timeout while the next one answers in ~2 s, so `gemini-3.8-flash` was lost at boot)
  - anything else, including `400` (no tool support) → `FAILED`
  - success → `PASSED`

**Rationale**: The chat agent always sends function declarations, so a model that rejects
tools would otherwise fail on the first chat turn (FR-008). Keeping the bool wrappers
leaves `test_guides_and_boot.py` and `test_models.py` (which monkeypatch
`_probe_gemini`) valid. `is_rate_limited` in `model_retry.py` is not reused for this,
because it also treats `503` / `529` as retryable. Here only `429` means "this class has
no quota" (the provider enforces quota per base model, so per class).

**Alternatives**: plain "hello" probe (misses tool-incapable models); reusing
`generate_with_retry` (async, 90 s budget, built for chat turns, far too slow for boot).

## R4. Picking per class

**Decision**: For each configured class, take the newest `keep + 2` candidates. Probe
every class's candidates in one concurrent wave (`_gather_threads` with
`max_workers=len(calls)`, capped at 32). Then walk each class in version order:

- `PASSED`: keep it, until `keep` models are kept.
- `NOT_ENABLED` / `FAILED`: continue with the next candidate.
- `NO_QUOTA`: stop. The class reason is `no_quota`, and anything already kept stays.

A class that keeps nothing records the reason of its first failure: `no_quota`,
`not_enabled`, `failed`, or `no_candidates` when the catalog had nothing to try.

`pick_per_class(candidates, outcomes, keep)` is pure: outcomes are passed in, so tests
need no network or threads.

**Rationale**: With defaults this is 12 Gemini and 9 Claude probes in one wave. A wave
costs at most one 10 s timeout. The 429 path costs about 2 s plus two fast refusals.
Today's `max_workers=8` would run 21 probes in three waves (up to 30 s), so the cap is
raised for the catalog path only. Static mode keeps 8. Stopping at `NO_QUOTA` matches
per-class quota. Probing concurrently rather than one by one keeps startup at one wave
(SC-004).

**Alternatives**: probe sequentially newest-first and stop at the first `keep` passes
(fewer calls, but up to `keep+2` × 10 s per class); probe every catalog version (wasteful,
over 40 calls).

## R5. One place that knows the model location

**Decision**: New module `wcl_agent/vertex.py`:

- `model_location() -> str`: `WCL_MODEL_LOCATION`, default `global`.
- `project_id() -> str | None`: `GOOGLE_CLOUD_PROJECT`, falling back to the ADC project.
- `genai_client()`: `genai.Client(vertexai=True, project=project_id(), location=model_location())`.
- `anthropic_client()` (sync) and `async_anthropic_client()`: `AnthropicVertex` /
  `AsyncAnthropicVertex(project_id=…, region=model_location(), …)`.
- `list_publisher_models(publisher) -> list[CatalogEntry]`: see R1.

Call sites that switch to the helper:

| Site | Today | After |
|---|---|---|
| `wcl_agent/models.py::_make_gemini_client` | `genai.Client()` | `vertex.genai_client()` |
| `wcl_agent/models.py::_make_anthropic_client` | `WCL_ANTHROPIC_REGION` or `GOOGLE_CLOUD_LOCATION` or `us-east5` | `vertex.anthropic_client()` |
| `backend/app/suggestions.py` | `genai.Client()` | `vertex.genai_client()` |
| `backend/app/services/report_synthesis.py` | `genai.Client()` | `vertex.genai_client()` |
| `backend/app/services/guide_pipeline/llm.py` | `genai.Client()` | `vertex.genai_client()` |
| `wcl_agent/model_retry.py::RetryingGemini` | ADK `Gemini` client built from env | `client_kwargs` default `{"location": model_location()}` |
| `wcl_agent/model_retry.py::RetryingClaude._anthropic_client` | ADK's client (env `GOOGLE_CLOUD_LOCATION`) | `vertex.async_anthropic_client().with_options(max_retries=0)` |
| `wcl_agent/agent.py::_build_web_search_tool` | bare model id → ADK `Gemini` built from env | `Gemini(model=model, client_kwargs={"location": model_location()})` |

**Rationale**: ADK 2.10's `Gemini` documents `client_kwargs` as the supported way to set
`location`. Overriding `api_client` pins one client across event loops, which the ADK
docstring warns against. ADK's `Claude._anthropic_client` reads `GOOGLE_CLOUD_LOCATION`
directly, so `RetryingClaude` must build its own client. It already overrides that
property, so the change stays in the one place that touches it. anthropic 1.11 handles
`region="global"` (it uses the global host).

The web-search sub-agent is a model call that `documentation/live_model_probe.md`
missed. Left alone, it would call `europe-west1` once the general region moves there,
and fail for every Gemini 3.x model. It stays a plain `Gemini`, not a retrying one, so
its retry behaviour is unchanged.

`WCL_ANTHROPIC_REGION` is removed: one location for all model calls (FR-017), and FR-019
removes the `us-east5` fallback.

**Alternatives**: setting `GOOGLE_CLOUD_LOCATION=global` and leaving clients alone (that
is today's setup, and it blocks moving the general region to `europe-west1`); a location
per provider (no present need, Principle III).

## R6. Caching the result

**Decision**: New cache family `CacheFamily.MODEL_CATALOG = "model_catalog"`,
`FamilyConfig(21600, 0.50)`. The value model is `cache_models.ModelCatalog`. The key is
`keys.model_catalog(project, location, classes_sig)` →
`ext:models:v1:{project}:{location}:{sig}`, where `sig` is a canonical string of the class
settings and the stage allowlist, for example `g=pro2.flash2.flash-lite2;a=haiku1.sonnet1.opus1`.

It is read in `main._models` through
`get_or_load(…, loader=lambda: asyncio.to_thread(discover_models, …), ttl=_catalog_ttl)`.
`_catalog_ttl(v)` returns `0` (don't store) unless `v.source == "catalog"` and
`not v.degraded`. The lifetime uses the existing per-family override
`WCL_CACHE_TTL_MODEL_CATALOG` (default 21600). `0` turns storage off, and
`WCL_CACHE_ENABLED=false` or no `REDIS_URL` bypasses the cache entirely.

**Rationale**: `get_or_load` already handles Redis being down (falls back to the loader),
stampede locks across workers, corrupt entries and the hit/miss stats (so the admin cache
stats page shows the family for free). Its `ttl` callable with a `0` result already means
"don't store" (`_encode` / `_load_and_store`).

Not caching a fallback or degraded result means a catalog or quota outage is retried at
the next restart instead of being frozen for 6 h. The source document proposed a
separate `WCL_MODEL_DISCOVERY_CACHE_S`. That would be a second lifetime setting beside
the generic `WCL_CACHE_TTL_{FAMILY}` mechanism every other family uses, so it is dropped
(Principle I). The `ext:` key prefix matches the other non-WCL families (`ext:hotfix`,
`ext:talents`) and holds no user or tenant id.

The loader lock lasts 90 s (`WCL_CACHE_LOCK_MS`) and outlasts discovery (about 22 s at
worst). A second worker booting at the same moment waits up to `WCL_CACHE_LOCK_WAIT_MS`
(2 s) for the winner's result. If the result isn't there yet, the second worker runs
discovery itself. That is the same behaviour as every other family and acceptable at
boot.

**Alternatives**: in-process memo only (does not survive a restart, which is the point);
a file on disk (not shared across containers).

## R7. Warning for fixed-purpose models

**Decision**: `ModelCatalog.listed` holds every callable id the catalog returned (bare
names, plus `@version` forms for Claude). After discovery, on a hit or a miss,
`main._models` logs one warning per fixed-purpose id absent from `listed`. The
fixed-purpose ids are `WCL_GUIDE_MODEL`, `WCL_GUIDE_REVIEW_MODEL`, `WCL_REPORT_MODEL` and
`greeting.GREETING_MODEL`. When `listed` is empty (static or fallback source), no warning
is logged.

**Rationale**: Storing the listed ids in the cached value keeps the warning on every
restart without re-listing. It costs about 45 short strings. An id with an `@version`
suffix also matches on its bare name.

**Alternatives**: warn only on a cache miss (the warning disappears for 6 h after the
first boot).

## R8. Configuration surface

**Decision**: New settings, documented in `.env.example` and the README:

| Setting | Default | Read by |
|---|---|---|
| `WCL_MODEL_DISCOVERY` | `catalog` (`static` = today's behaviour) | `backend/app/config.py` |
| `WCL_GEMINI_CLASSES` | `pro:2,flash:2,flash-lite:2` | `backend/app/config.py` |
| `WCL_ANTHROPIC_CLASSES` | `haiku:1,sonnet:1,opus:1` | `backend/app/config.py` |
| `WCL_MODEL_LOCATION` | `global` | `wcl_agent/vertex.py` (env; the package stays standalone) |
| `WCL_CACHE_TTL_MODEL_CATALOG` | `21600` | `wcl_agent/cache.py` (existing mechanism) |

`GOOGLE_CLOUD_LOCATION` becomes `europe-west1` in `.env.example`. `WCL_ANTHROPIC_REGION`
is removed. `WCL_GEMINI_MODELS`, `WCL_ANTHROPIC_MODELS`, `WCL_MODELS` and
`WCL_DEFAULT_MODEL` stay: they are the static lists, the fallback, and the preferred
default.

A class setting parses as `name:count`. An unknown class name or a non-positive count is
logged and ignored. An empty string means "no classes for this publisher".

**Rationale**: `wcl_agent` reads its own settings from the environment, as `cache.py`
does, and `backend/app/config.py` calls `load_dotenv()` so `.env` reaches `os.environ`.
The class settings are backend-only inputs passed into `discover_models`.

## R9. Startup log and boot step detail

**Decision**: The `models` boot step detail becomes `"{n} models ({source})"`, where
`source` is `catalog`, `static`, `fallback` or `degraded`, plus `", cached"` on a cache
hit. `discover_models` logs one INFO line per class (`gemini pro: gemini-3.1-pro-preview,
gemini-2.5-pro` or `claude sonnet: no quota (429)`). A cache hit replays those lines from
`ModelCatalog.classes`, so every boot shows them. A listing failure logs exactly one
WARNING (`model catalog unavailable (…); probing the static lists`).

**Rationale**: SC-006: the startup log alone explains every class.
