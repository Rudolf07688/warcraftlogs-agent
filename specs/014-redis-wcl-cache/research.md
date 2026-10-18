# Research: Shared Warcraft Logs Cache (feature 014)

Design reference: `documentation/redis_cache_spec.md` (the "design doc"). This file records
where the plan follows it, where the codebase forces a deviation, and why.

## R1. Mapping the design doc's families onto the real tool surface

The design doc assumes tools shaped around a character id and per-player aggregates. The
real WCL call sites (found by GitNexus + text search, 2026-10-18) are:

| Call site | Query | Today |
|---|---|---|
| `report_tools.get_report_fights` | report title/zone/guild/players/fights | cached 24h |
| `report_tools.get_report_metadata` (raids capture) | title/zone/guild/startTime | cached 24h |
| `recent_raids.fetch_report_details` | batched `report_details_query` (endTime, zone, fights) | cached 24h |
| `recent_raids.fetch_listed_reports` | batched `recent_reports_query` per character | `cache=False` |
| `report_tools.get_report_table` | `table(...)` JSON | cached 24h |
| `report_tools.get_report_player_details` | `playerDetails` JSON | cached 24h |
| `report_tools.get_report_events/graph/rankings/master_data` | JSON scalars | cached 24h |
| `report_tools.get_character_zone_rankings` / `_encounter_rankings` | by name/server/region | cached 1h |
| `tools._fetch_rankings` (leaderboards, many pages) | `ENCOUNTER_RANKINGS` | cached 1h |
| `patch.current_patch` (every chat turn), `patch.raid_zone_ids`, `tools.find_encounter`, `menu` | `MENU_DISCOVERY` | cached 1h |
| `report_tools.run_wcl_graphql` | arbitrary | cached by shape |
| `wcl_client._token` | OAuth | process dict, never expires |

**Decision** — family → call sites:

| Family | Key | Loader / consumers | TTL |
|---|---|---|---|
| `char_id` | `wcl:v1:char_id:{region}:{realm_slug}:{name_lc}` | new `resolve_character()` (tiny `character(name,serverSlug,serverRegion){id name classID server{slug region{slug}}}` query); used first by both character-rankings tools and by recent raids | 24h |
| `char_overview` | `wcl:v1:char:{id}:overview:zone:{zone}:{metric}:{diff}` and `wcl:v1:char:{id}:overview:enc:{enc}:{metric}:{diff}` | `get_character_zone_rankings`, `get_character_encounter_rankings` (query by `character(id:)`) | 10m |
| `char_reports` | `wcl:v1:char:{id}:reports:{limit}` | `recent_raids.fetch_listed_reports`, per character | 5m |
| `report_summary` | `wcl:v1:report:{code}:summary` | `get_report_fights`; `get_report_metadata` and `fetch_report_details` become projections of the same `ReportSummary` | 24h if finished, else 2m |
| `report_player` | `wcl:v1:report:{code}:player:{source_id}:table:{data_type}:{fight}:{ability}:{hostility}` | `get_report_table` **only when `source_id > 0`** (the per-player breakdown) | 24h if finished, else 2m |
| `oauth_token` | `wcl:v1:oauth:token` | `AsyncWCLClient._token` | `expires_in − 60s` |
| `world_zones` | `wcl:v1:world:zones` | `MENU_DISCOVERY` consumers (patch, find_encounter, menu, raid_zone_ids) | 1h |

**Rationale**:
- `char_id` then `char:{id}` follows the doc literally and gives the negative cache a home:
  a misspelt name is answered from `{"_missing": true}` for 60s and the rankings query is
  never sent. Cost: one extra tiny WCL request per character per 24h.
- `char_overview` widens the doc's key by the query dimensions (zone/encounter, metric,
  difficulty). Without them two different questions would share one entry and answer wrongly.
  The doc's "gear, progress and parse summary" has no single WCL query; zone/encounter
  rankings are the parse+progress data the agent actually asks for.
- `report_summary` matches `get_report_fights` almost exactly (fights, bosses, kills/wipes,
  roster). Folding metadata and the recent-raids detail step into it removes three queries
  with overlapping fields (Principle I).
- `report_player` = per-player tables only. Whole-raid tables, events, graphs, master data,
  report rankings and `playerDetails` are **not** cached (design doc: event-level data is
  large and rarely repeated; the user chose to remove the generic cache — Clarifications).
- `world_zones` is the 7th family the user approved on 2026-10-18: `current_patch()` runs on
  every chat turn, so without it each turn would cost a WCL request.

**Alternatives considered**: keep querying by name and drop `char_id` (no negative cache,
diverges from doc); cache all report tables under `report_player` (unbounded key space, large
values — the doc rejects it); keep `playerDetails` as a family (not per player; can add later
with evidence).

## R2. "Finished report" rule

**Decision**: a report is finished when `now − endTime ≥ 2h`. Reuse the existing
`FINAL_AFTER` rule from `backend/app/services/recent_raids.py` by moving it to
`wcl_agent` (single source, consumed by both). Unfinished report entries get TTL 120s.
`ReportSummary` therefore includes `end_time_ms`.

**Rationale**: WCL v2 exposes no "live" flag; `endTime` advances while live logging runs.
The 2h rule is already what feature 013 uses to stop re-fetching reports.

**Alternatives**: skip caching unfinished reports (more WCL calls during raid night).

## R3. Cache client shape — `get_or_load`

**Decision**: one module `wcl_agent/cache.py` (rewritten), one public coroutine:

```python
await get_or_load(family: CacheFamily, key: str, model: type[M], loader: Callable[[], Awaitable[M | None]],
                  *, ttl: int | None = None, force_refresh: bool = False) -> M | None
```

- Values are Pydantic models; stored as `model_dump_json()`, read with
  `model_validate_json()`. A validation/JSON failure is the "corrupt" path (DEL, miss, `error`).
  Typed boundary per Principle IV; schema drift within one `v1` is also caught.
- `loader()` returning `None` means "not found" → `{"_missing":true}` for `WCL_NEG_CACHE_TTL`,
  outcome `miss`; reading the marker → `neg_hit`, returns `None`.
- `ttl=None` → family default (env override `WCL_CACHE_TTL_{FAMILY}`); callers pass `ttl`
  only for the dynamic cases (unfinished reports, OAuth `expires_in`).
- Jitter `ttl * uniform(1, 1 + WCL_CACHE_JITTER)` applied on every write.
- Lock: `SET lock:{key} 1 NX PX WCL_CACHE_LOCK_MS`; losers poll `GET key` every 100ms up to
  `WCL_CACHE_LOCK_WAIT_MS` (2000), then load themselves (`lock_timeout`). Winner DELs the lock
  after writing (and in `finally` on error).
- Redis error anywhere → `redis_error`, call loader, skip writes. A Redis error during the
  metrics write is swallowed (logged at debug).

**Rationale**: the doc's behaviour list, typed. A lock-timeout loser in the *same process*
re-sends the same GraphQL, which the client's existing single-flight joins, so it costs no
second WCL request; the only possible duplicate is across processes.

**Alternatives**: return raw dicts (violates Principle IV); in-process single-flight around
the Redis lock (redundant with client single-flight).

## R4. Redis client lifecycle

**Decision**: `redis.asyncio.Redis.from_url(REDIS_URL)` **one per event loop**, in a
`WeakKeyDictionary[loop, Redis]`, the pattern `wcl_client._clients` already uses (CLI and
tests run several loops; redis-py asyncio connections are loop-bound). Closed by the existing
`aclose_clients()` in the FastAPI lifespan. `socket_timeout=0.25`, `socket_connect_timeout=0.25`
so a dead Redis costs ≤250ms before fallback. While a loop's client is failing, stop trying for
`5s` (simple circuit: `_down_until` timestamp) so every lookup does not pay the timeout.

`REDIS_URL` unset **or** `WCL_CACHE_ENABLED=false` → cache disabled: `get_or_load` calls the
loader directly and records nothing. This keeps `wcl_agent` standalone (the CLI needs no Redis).

**Alternatives**: one global client (breaks multi-loop tests/CLI); no circuit (every call in
an outage pays the connect timeout, violating SC-004's "no visible impact").

## R5. OAuth token

**Decision**: keep the process memo `_tokens` but store `(token, expires_at)`; on memo miss
or expiry call `get_or_load("oauth_token", "wcl:v1:oauth:token", OAuthToken, loader,
ttl=expires_in-60)`. On a 401 the memo entry is dropped and `get_or_load(..., force_refresh=True)`.

**Rationale**: reading Redis before *every* WCL call would turn a Redis outage into an OAuth
request per WCL call. The memo keeps the hot path free; Redis shares the token across
processes/restarts. The token is a credential: the key holds a client-credentials bearer
token in a cache that is not exposed outside the compose network (documented in quickstart).

**Alternatives**: Redis only (outage amplifies OAuth calls); memo only (status quo, no sharing).

## R6. Retries, backoff and API cost logging

**Decision** (in `AsyncWCLClient._fetch`):
- Retry on HTTP 429 and 5xx, max 2 retries, backoff `0.5s·2^n` + jitter, honouring
  `Retry-After` when present (capped at 10s); retries stay inside the existing query timeout.
- Cost: inject `rateLimitData { pointsSpentThisHour }` into the top-level selection of every
  query (insert after the first `{` that follows the operation header). Strip it from the
  returned payload. Log `wcl_cost op=<operation name> points_this_hour=N delta=M` at INFO,
  where `delta` is relative to the last value seen by this process.

**Rationale**: FR-016/FR-017/FR-026. Injection covers every call, including uncached ones and
`run_wcl_graphql`, with one change at the chokepoint.

**Alternatives**: separate `rateLimitData` query per call (doubles requests).

## R7. Metrics

**Decision**: per the doc: hash `wcl:metrics:v1:{family}:{YYYYMMDD}` with fields
`hit miss neg_hit lock_timeout error redis_error load_ms_sum load_count`, `EXPIRE`
`WCL_METRICS_RETENTION_DAYS·86400` on every write (idempotent, cheaper than checking first).
Writes go in a non-transactional pipeline: on a miss, together with the `SET`; on a hit, as a
fire-and-forget task (strong refs held in a module set, like the app's other background tasks).
`redis_error` cannot be written to a Redis that is down, so it is also counted in a process
counter and flushed into the hash on the next successful write.

Status thresholds come from the family config (R8). `INFO stats` / `INFO memory` give
`keyspace_hits`, `keyspace_misses`, `evicted_keys`, `used_memory`.

**Alternatives**: Prometheus (doc: optional, not running here — out of scope).

## R8. Family configuration

**Decision**: `CacheFamily` `StrEnum` + one frozen dataclass table in `cache.py`:
`FAMILIES[family] = FamilyConfig(default_ttl_s, review_below)`. Env override
`WCL_CACHE_TTL_{FAMILY.upper()}` read once per lookup via the existing `_env_int`. Key builders
live next to it (`keys.char_id(region, realm, name)` …) so every key is built in one place and
can be tested for normalisation and for the absence of user data.

## R9. Force refresh

**Decision**: `force_refresh: bool = False` parameter on `get_character_zone_rankings` and
`get_character_encounter_rankings` (the agent passes it when the user says "check again");
agent instruction gets one line. Rate limit: `SET chat:refresh:{user_id}:{char_id} 1 NX EX 60`.
If the SET fails (already refreshed) the call proceeds as a normal cached read and the tool
result includes `"refresh": "skipped_recent"` so the agent can say so. The acting user id comes
from a `ContextVar` set by `ws.py` at the point where it used to call `set_cache_scope`
(the `chat:` prefix keeps user data out of `wcl:` keys).

**Alternatives**: per-tenant limit via ADK `user_id` (it is the tenant id, not the user).

## R10. Removing tenant scoping and the in-process cache

**Decision**: delete `TTLCache`, `get_cache`, `cache_key`, `ttl_for`, `is_report_scoped`,
`set_scope_prefix`/`get_scope_prefix`, settings `wcl_cache_ttl_report_s`,
`wcl_cache_ttl_leaderboard_s`, env `WCL_CACHE_TTL_REPORT_S`, `WCL_CACHE_TTL_LEADERBOARD_S`,
`WCL_CACHE_MAX_BYTES`, and the `cache=` kwarg on `AsyncWCLClient.query`. Single-flight stays,
keyed by `sha256(query + sorted variables)` computed in `wcl_client` (no scope prefix).
Tests `test_wcl_cache.py` (rewrite for Redis), cache parts of `test_tenant_isolation.py`
(replace with a "keys contain no tenant/user id" test), `test_recent_raids.py`,
`test_wcl_async.py`, `test_tool_concurrency.py`, `test_wcl_loop_lag.py` (drop `get_cache` use).

**Impact (GitNexus, 2026-10-18)**: `cache_key` HIGH (7 impacted, 4 processes),
`get_cache` HIGH (8, 4 processes), `AsyncWCLClient._token` HIGH (5, 4 processes),
`AsyncWCLClient.query` LOW/8 per graph **but** ~20 call sites via `get_async_client()` that the
graph does not resolve (dynamic dispatch) — confirmed with text search; treat as HIGH.
`fetch_listed_reports` / `fetch_report_details` LOW (3).

## R11. Docker Compose and dependencies

**Decision**:
- Service `redis`: image `redis:8-alpine`, command
  `redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru --save "" --appendonly no`,
  healthcheck `redis-cli ping` (5s/3s/10 retries), port `6379:6379` (host CLI and tests, same as
  `db` exposes 5432), no volume.
- `backend`: `environment.REDIS_URL: redis://redis:6379/0`, `depends_on.redis: service_healthy`.
- `.env.example`: `REDIS_URL=redis://localhost:6379/0` (host runs) plus every `WCL_CACHE_*`
  setting commented with defaults; compose overrides `REDIS_URL` for the container.
- Python: `redis>=6` (includes `redis.asyncio`) in `dependencies`; `fakeredis>=2.30` in the
  `test` extra. `uv add`, commit `uv.lock`.
- Backend `Settings` gains the same fields (documented, typed); `wcl_agent` keeps reading
  `os.getenv` (standalone package, same as the WCL concurrency settings).

## R12. Stats endpoint

**Decision**: `GET /api/admin/cache-stats?days=7` (1–35) on a new router file
`backend/app/api/cache_stats.py`, guarded by the existing `require_platform_admin`
(the app's "operator"). The doc's `/internal/...` path is replaced by the existing admin
prefix so it inherits auth, CSRF-free GET, and Vite proxying. Pure aggregation helper
`summarize(days_of_hashes) -> CacheStats` lives in `wcl_agent/cache.py` so it is unit-testable
without FastAPI. Redis down → 200 with `"redis": null` and empty families plus
`"available": false`.
