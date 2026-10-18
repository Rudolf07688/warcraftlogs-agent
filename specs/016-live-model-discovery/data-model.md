# Data Model: Live Model Discovery

Internal value objects are dataclasses. The cached value is a Pydantic model, because
it crosses the Redis boundary (Principle IV). Nothing here is persisted in the database.

## CatalogEntry (dataclass, `wcl_agent/vertex.py`)

One row of a publisher catalog listing (R1).

| Field | Type | Notes |
|---|---|---|
| `publisher` | `Literal["google", "anthropic"]` | |
| `name` | `str` | Last path segment of `name`, e.g. `gemini-3.8-flash`, `claude-haiku-4-5` |
| `version_id` | `str \| None` | `versionId`; `default` or a date tag such as `20251001` |
| `stage` | `str \| None` | `launchStage`: `GA`, `PUBLIC_PREVIEW`, `EXPERIMENTAL`, … |

## ClassSetting (dataclass, `wcl_agent/models.py`)

| Field | Type | Rule |
|---|---|---|
| `publisher` | `Literal["google", "anthropic"]` | |
| `name` | `str` | Gemini: `pro`, `flash`, `flash-lite`. Claude: `haiku`, `sonnet`, `opus`. Any other name is ignored with a warning. |
| `keep` | `int` | ≥ 1. Defaults: 2 per Gemini class, 1 per Claude class. |

The order of the settings is the serving order (FR-014). It is parsed from
`WCL_GEMINI_CLASSES` / `WCL_ANTHROPIC_CLASSES` (`name:count,…`) by
`backend/app/config.py`.

## Candidate (frozen dataclass, `wcl_agent/models.py`)

A catalog entry that matched a configured class (R2).

| Field | Type | Notes |
|---|---|---|
| `publisher` | `str` | |
| `cls` | `str` | Class name |
| `version` | `tuple[int, int]` | `(major, minor)`, minor defaulting to 0 |
| `preview` | `bool` | Stage `PUBLIC_PREVIEW` or a `-preview` suffix |
| `model_id` | `str` | The id the provider accepts for calls (bare, or `name@version_id` for dated Claude versions) |

**Ordering** within a class: `version` descending, then `preview=False` first.
**Filters**: `stage == "EXPERIMENTAL"` (or any stage not in {GA, PUBLIC_PREVIEW}) is
dropped, and a missing stage is kept.

## ProbeOutcome (StrEnum, `wcl_agent/models.py`)

`passed` · `not_enabled` (404/403) · `no_quota` (429 after one retry) · `failed`
(timeout or any other error).

## ClassResult (Pydantic, `wcl_agent/cache_models.py`)

The per-class outcome. It is part of the cached value, so it can be replayed in the log.

| Field | Type | Notes |
|---|---|---|
| `publisher` | `str` | |
| `cls` | `str` | |
| `models` | `list[str]` | Kept ids, newest first (≤ `keep`) |
| `reason` | `str \| None` | `None` when `models` is non-empty. Otherwise `no_quota`, `not_enabled`, `failed` or `no_candidates`. When models are kept but the walk stopped at a quota refusal, `no_quota` is still recorded. |

## ModelCatalog (Pydantic, `wcl_agent/cache_models.py`): the discovery result

What `discover_models` returns and what the cache family `MODEL_CATALOG` stores.

| Field | Type | Notes |
|---|---|---|
| `models` | `list[str]` | Served order (FR-014). Never empty. |
| `default` | `str` | Always a member of `models` (FR-013) |
| `degraded` | `bool` | True only for the degraded path (FR-016) |
| `source` | `Literal["catalog", "static", "fallback", "degraded"]` | `fallback` = listing failed and the static lists were probed (FR-015) |
| `classes` | `list[ClassResult]` | Empty unless the catalog was listed (`catalog`, or `degraded` after a listing) |
| `listed` | `list[str]` | Every callable id seen in the catalog (R7). Empty unless the listing succeeded. |
| `fetched_at` | `datetime` | UTC |

**Invariants**: `models` is non-empty; `default ∈ models`; `degraded ⇔ source ==
"degraded"`.

**Cache rule**: stored only when `source == "catalog"` and not `degraded` (R6).

**Return value**: `discover_models` returns a `ModelCatalog`. It replaces today's plain
`{"models", "default", "degraded"}` dict, and the existing callers and tests that index
the dict are updated to use attributes. `app.state.models`, `app.state.default_model`
and `app.state.models_degraded` are filled from it as today, so `get_model_state`,
`is_valid_model`, `GET /api/models` and the frontend are unchanged.

## Discovery flow (states)

```text
mode=static ───────────────────────────► probe static lists ──► static | degraded
mode=catalog ─► list catalogs ─┬─ fail ─► probe static lists ──► fallback | degraded
                               └─ ok ──► classify ► candidates ► probe wave ► pick
                                                        └─► any kept? ── yes ─► catalog
                                                                       └─ no ──► degraded
```

The `degraded` result serves `WCL_MODELS` (or `[WCL_DEFAULT_MODEL]`) exactly as today.
