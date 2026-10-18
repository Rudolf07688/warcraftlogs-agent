# Implementation Plan: Shared Warcraft Logs Cache

**Branch**: `014-redis-wcl-cache` | **Date**: 2026-10-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/014-redis-wcl-cache/spec.md`; design reference
`documentation/redis_cache_spec.md`.

## Summary

Replace the in-process, tenant-scoped WCL query cache with a shared Redis cache-aside layer.
Seven typed key families (char_id, char_overview, char_reports, report_summary,
report_player, oauth_token, world_zones) are reached only through one
`get_or_load` coroutine that handles TTL + jitter, a per-key lock against stampedes, negative
caching, corrupt-value recovery and a fail-open path when Redis is down. Per-family daily
counters in Redis feed an admin-only `GET /api/admin/cache-stats`. The WCL client gains
429/5xx retries and per-request API-cost logging; everything else it fetches goes uncached.
Docker Compose gains a health-checked, memory-bounded, non-persistent `redis` service that
the backend waits for.

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: FastAPI, httpx, Pydantic v2 / pydantic-settings, google-adk; **new**: `redis>=6` (`redis.asyncio`); test: `fakeredis>=2.30`

**Storage**: Redis 8 (cache + metrics, disposable); PostgreSQL unchanged

**Testing**: pytest + pytest-asyncio (auto mode), fakeredis for unit tests; manual live checks in quickstart.md

**Target Platform**: Linux containers (Docker Compose locally); backend on Cloud Run later (managed Redis out of scope)

**Project Type**: Web application (FastAPI backend + `wcl_agent` package + React frontend; no frontend change)

**Performance Goals**: repeat lookups ≥50% faster (SC-001); ≥40% fewer WCL points on a 100-question replay vs cache off (SC-002); Redis hit path adds ≤2ms locally

**Constraints**: Redis is never a hard dependency (≤250ms penalty, then 5s circuit); `wcl_agent` stays standalone (cache off without `REDIS_URL`); no user/tenant ids in `wcl:` keys; values are normalised models, never raw GraphQL

**Scale/Scope**: single backend process today, may become several; a handful of tenants; 7 families; Redis `maxmemory 256mb`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — still passing.*

| Principle | Status | How |
|---|---|---|
| I. DRY & reuse | ✅ | One `get_or_load` and one key-builder table; `ReportSummary` replaces three overlapping report queries (fights, metadata, recent-raids details); `load_world_zones()` replaces four `MENU_DISCOVERY` call sites; `FINAL_AFTER` and `_server_slug` move to one shared home; per-loop client pattern reused from `wcl_client`. |
| II. Step-wise delivery | ✅ | Design doc rollout order: cache core + metrics + stats (tools unchanged) → oauth_token, world_zones, char_id → remaining families → removal of the old cache. Each step leaves tests green. |
| III. Simplicity | ⚠ justified | Adds Redis (a new service) and two dependencies — see Complexity Tracking. No Prometheus, no in-process L1, no hash tags/generations. |
| IV. Typed contracts | ✅ | Cached values are Pydantic models (data-model.md); config is dataclasses/StrEnum; stats endpoint returns `CacheStats`. `WorldZones.zones` stays `list[dict]` deliberately (consumed by existing pure helpers). |
| V. Async FastAPI | ✅ | `redis.asyncio`; all Redis calls awaited with 250ms socket timeouts; stats endpoint `async def`. |
| VI. GitNexus | ✅ | Impact run 2026-10-18 (research R10): `cache_key`, `get_cache`, `_token` HIGH; `AsyncWCLClient.query` resolves only 8 callers in the graph but ~20 via `get_async_client()` (dynamic dispatch) — treated as HIGH. Re-run `impact` before each edit and `detect_changes` before each commit. |
| VII. shadcn UI | n/a | No frontend change. |

**HIGH-risk warning**: removing `cache_key`/`get_cache`/scope prefix and changing `_token` and
`query()` touches every WCL call path (chat tools, recent raids, guides, patch preamble).
Mitigation: the WCL client changes land with the contract tests in 013's `test_wcl_async.py`
kept green, and the old cache is removed only in the last step.

## Project Structure

### Documentation (this feature)

```text
specs/014-redis-wcl-cache/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cache-client.md
│   ├── cache-stats-api.md
│   └── config-and-compose.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
docker-compose.yml                 # + redis service, backend REDIS_URL + depends_on
.env.example                       # + REDIS_URL, WCL_CACHE_*; − old cache vars
pyproject.toml / uv.lock           # + redis, + fakeredis (test)

wcl_agent/
├── cache.py                       # REWRITE: CacheFamily, FamilyConfig, keys, get_or_load,
│                                  #   metrics, read_stats, per-loop Redis client, refresh claim
├── cache_models.py                # NEW: CharacterRef, CharacterRankings, CharacterReports,
│                                  #   ReportSummary, PlayerTable, OAuthToken, WorldZones
├── normalize.py                   # NEW: server_slug, FINAL_AFTER, is_finished (pure; no cycle with cache)
├── wcl_client.py                  # − result cache, cache kwarg; + retries, cost logging,
│                                  #   token via oauth_token, single-flight hash, close Redis
├── report_tools.py                # resolve_character (char_id); load_report_summary; fights/metadata from it; per-player
│                                  #   tables via report_player; character tools via char_id +
│                                  #   char_overview + force_refresh
├── menu.py                        # load_world_zones (world_zones); menu uses it
├── patch.py, tools.py             # current_patch/raid_zone_ids, find_encounter use load_world_zones
└── agent.py                       # one instruction line: force_refresh on "check again"

backend/app/
├── api/cache_stats.py             # NEW: GET /api/admin/cache-stats
├── api/ws.py                      # set_refresh_actor(user_id) replaces set_cache_scope
├── services/recent_raids.py       # char_reports per character; details from ReportSummary
├── schemas.py                     # FamilyStats, RedisHealth, CacheStats
├── config.py                      # + cache settings; − wcl_cache_ttl_*_s
└── main.py                        # include cache_stats router

backend/tests/
├── conftest.py                    # fakeredis fixture; cache disabled by default
├── test_wcl_cache.py              # REWRITE: get_or_load behaviour C1–C12, keys, metrics
├── test_cache_stats.py            # NEW: aggregation, status rules, auth, degraded modes
├── test_wcl_async.py              # retries, cost injection/stripping, token flow
├── test_tenant_isolation.py       # cache-scope test → "no tenant/user id in wcl: keys"
└── test_recent_raids.py, test_tool_concurrency.py, test_wcl_loop_lag.py   # drop get_cache
```

**Structure Decision**: existing web-app layout. Cache logic belongs in `wcl_agent`
(tools and the WCL client live there and it must stay importable without the backend); the
backend only adds the admin endpoint, settings, compose wiring and the per-turn refresh actor.

## Implementation phases (for /speckit-tasks)

1. **Infra**: compose `redis` service, deps, settings, `.env.example`, fakeredis fixture.
2. **Core** (US2 + US3 foundation): `cache.py` rewrite alongside the old cache (new names),
   `cache_models.py`, metrics, `read_stats`, stats endpoint. Tests C1–C12 + stats.
3. **First families**: `oauth_token` (token memo + Redis), `world_zones`, `char_id` +
   `char_overview` with force refresh. WCL client retries + cost logging.
4. **Report and recent-raid families**: `report_summary` (+ metadata/details projections),
   `report_player`, `char_reports`.
5. **Removal**: delete old in-process cache, `cache=` kwarg, scope prefix, old settings/env;
   update affected tests; README/ai_guide cache sections.
6. **Verify**: quickstart US1–US5 live; 100-question replay with cache on/off (SC-002).

## Risks

- **Uncached leaderboards and report tables** (accepted in Clarifications): rankings tools page
  through many WCL requests and were cached 1h. FR-026 cost logging makes the increase
  visible; adding a family needs that evidence.
- **Extra char_id request** on the first lookup of each character per day (cheap; enables
  the negative cache).
- **Token in Redis**: dev port is exposed on localhost only; documented in quickstart.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New service: Redis in compose (and later in prod) | Shared cache across processes/restarts and per-family metrics are the feature (user-mandated) | In-process cache: per-process, lost on restart, no cross-process stampede protection — what this feature replaces |
| New dependency `redis` | Async Redis client | Hand-rolled RESP client: more code, no benefit |
| New test dependency `fakeredis` | Unit-test every outcome without a running Redis (design doc §9) | Real Redis in CI: slower, needs a service; mocks: would not exercise NX/PX/pipeline semantics |
| 7th family `world_zones` beyond the doc's six | `current_patch()` runs every chat turn; uncached it costs one WCL request per turn (user-approved 2026-10-18) | Leave it uncached: regresses today's behaviour |
