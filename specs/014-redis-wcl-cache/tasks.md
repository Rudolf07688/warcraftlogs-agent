# Tasks: Shared Warcraft Logs Cache

**Input**: Design documents from `specs/014-redis-wcl-cache/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (cache-client.md, cache-stats-api.md, config-and-compose.md), quickstart.md

**Tests**: Included. The design doc (`documentation/redis_cache_spec.md` §9) and quickstart.md §3 require unit coverage of every cache outcome, the metrics and the key builders.

**Organization**: Tasks are grouped by user story. US1 and US2 are both P1; US3 and US5 are P2; US4 is P3.

**Every task that edits an existing symbol**: run `node .gitnexus/run.cjs impact "<symbol>" --direction upstream --repo .` first, and warn on HIGH/CRITICAL (constitution VI, CLAUDE.md). Run `detect-changes --scope all` before each commit.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: User story the task belongs to (US1–US5)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: dependencies and settings that every later phase needs.

- [X] T001 Add runtime dependency `redis>=6` and test-extra dependency `fakeredis>=2.30` with `uv add redis` / `uv add --optional test fakeredis`, committing the updated `pyproject.toml` and `uv.lock`
- [X] T002 [P] Add cache settings to `Settings` in `backend/app/config.py` (typed, with comments in the file's style): `redis_url: str = ""`, `wcl_cache_enabled: bool = True`, `wcl_cache_ttl_char_id: int = 86400`, `wcl_cache_ttl_char_overview: int = 600`, `wcl_cache_ttl_char_reports: int = 300`, `wcl_cache_ttl_report_summary: int = 86400`, `wcl_cache_ttl_report_player: int = 86400`, `wcl_cache_ttl_world_zones: int = 3600`, `wcl_cache_unfinished_ttl: int = 120`, `wcl_cache_jitter: float = 0.10`, `wcl_cache_lock_ms: int = 10000`, `wcl_cache_lock_wait_ms: int = 2000`, `wcl_neg_cache_ttl: int = 60`, `wcl_metrics_retention_days: int = 35` (documentation only — `wcl_agent` reads the same names via `os.getenv`, per contracts/config-and-compose.md). Leave the old `wcl_cache_ttl_*_s` fields until T045
- [X] T003 [P] Add a `fake_redis` fixture to `backend/tests/conftest.py`: creates `fakeredis.aioredis.FakeRedis()`, monkeypatches `wcl_agent.cache` so the running loop's client is that instance, and sets `REDIS_URL=redis://fake` + `WCL_CACHE_ENABLED=true`. Add an autouse fixture that unsets `REDIS_URL` by default, so existing tests run with the cache disabled unless they request `fake_redis`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the typed models and the `get_or_load` core (happy paths + metrics). The old in-process cache stays in place and untouched until Phase 8, so the new code lives beside it under new names.

**⚠️ CRITICAL**: no user story work can begin until this phase is complete.

- [X] T004 [P] Create `wcl_agent/cache_models.py` with the Pydantic models from data-model.md: `CharacterRef`, `CharacterRankings`, `RecentReport`, `CharacterReports`, `PlayerRef`, `FightSummary`, `ReportSummary`, `PlayerTable`, `OAuthToken`, `WorldZones`. No backend imports
- [X] T005 [P] Create `wcl_agent/normalize.py` (renamed from characters.py: `cache` imports it, so it must not import `cache` — avoids an import cycle) holding the shared helpers: move `_server_slug` from `wcl_agent/report_tools.py` (re-export it there as `_server_slug = server_slug` for the existing import in `backend/app/services/recent_raids.py`), and move `FINAL_AFTER = timedelta(hours=2)` from `backend/app/services/recent_raids.py` (import it back there). Add `is_finished(end_time_ms: int, now: datetime | None = None) -> bool`
- [X] T006 In `wcl_agent/cache.py`, **add** (do not remove anything yet): `CacheFamily` and `Outcome` StrEnums, `FamilyConfig` dataclass and the `FAMILIES` table (TTL and review threshold per family, data-model.md), a frozen `CacheSettings` dataclass read from env (`REDIS_URL`, `WCL_CACHE_ENABLED`, `WCL_CACHE_JITTER`, `WCL_CACHE_LOCK_MS`, `WCL_CACHE_LOCK_WAIT_MS`, `WCL_NEG_CACHE_TTL`, `WCL_METRICS_RETENTION_DAYS`, `WCL_CACHE_UNFINISHED_TTL`), and `family_ttl(family)`, which applies the `WCL_CACHE_TTL_{FAMILY}` override through the existing `_env_int`
- [X] T007 In `wcl_agent/cache.py`, add the `keys` namespace (a small class of staticmethods or module functions prefixed `key_`) with builders for `char_id`, `char_zone`, `char_enc`, `char_reports`, `report_summary`, `report_player`, `OAUTH_TOKEN`, `WORLD_ZONES`, `lock`, `metrics(family, day)` and `refresh(user_id, char_id)` exactly as in data-model.md. `char_id` normalises with `strip().lower()` and `characters.server_slug`
- [X] T008 In `wcl_agent/cache.py`, add the per-loop Redis client: `_redis_clients: WeakKeyDictionary[loop, Redis]`, `_redis()` (returns `None` when the cache is disabled), built with `redis.asyncio.Redis.from_url(url, socket_timeout=0.25, socket_connect_timeout=0.25)`, and `aclose_redis()`. Follow the pattern of `wcl_client._clients` / `get_async_client`
- [X] T009 In `wcl_agent/cache.py`, implement `get_or_load(family, key, model, loader, *, ttl=None, force_refresh=False)` for contract guarantees C1–C6, C9, C11 and C12 (contracts/cache-client.md): GET, decode with `model_validate_json`, `_missing` marker, `SET lock NX PX`, loader, `SET EX ttl·U(1,1+jitter)`, `DEL lock` in `finally`, losers poll every 100 ms up to `lock_wait_ms`, then `lock_timeout` with no write, corrupt value → `DEL`, `error`, then continue as a miss. Disabled → call the loader directly (C8)
- [X] T010 In `wcl_agent/cache.py`, implement metrics recording (C10): `_record(family, outcome, load_ms=None)` with `HINCRBY` on `keys.metrics(family, utc_today)` plus `EXPIRE retention_days*86400` in a `pipeline(transaction=False)`. A miss's counters go in the same pipeline as the value `SET`; a hit's counters run as a fire-and-forget task kept in a module-level `set` of strong references. Metric write errors are logged at debug and swallowed
- [X] T011 [P] Rewrite `backend/tests/test_wcl_cache.py` around `get_or_load` with `fake_redis` and a counting stub loader. Cover: hit (C1), negative hit (C2), miss write + jitter bounds (C3), 10 concurrent callers → exactly 1 loader call (C4), lock-wait timeout → `lock_timeout` and no write (C4), loader error re-raised with the lock released and nothing written (C5), corrupt value (C6), force refresh (C9), lock released on cancellation (C12), one counter per outcome plus `load_ms_sum` / `load_count`, and key normalisation (`"Rudolf"`, `"rudolf "` and realm `"Area 52"` / `"area-52"` produce the same key). Keep any old-cache tests still needed until T045

**Checkpoint**: `uv run pytest backend/tests/test_wcl_cache.py -q` is green, and nothing calls `get_or_load` in production code yet.

---

## Phase 3: User Story 1 - Faster answers for repeated character and report questions (Priority: P1) 🎯 MVP

**Goal**: all seven families go through `get_or_load`; repeated questions are answered from Redis and every real WCL request logs its point cost.

**Independent Test**: with `fake_redis` (or live compose), asking the same character question twice sends no WCL request for the cached data the second time; a misspelt name repeated within 60 s sends one request; 10 concurrent identical lookups send one request (quickstart US1).

### Tests for User Story 1

- [X] T012 [P] [US1] In `backend/tests/test_wcl_async.py`, add tests for the client changes: 429 and then 200 → 1 retry; 503 three times → raises after 2 retries; `Retry-After` honoured (capped at 10 s, use a patched sleep); `rateLimitData { pointsSpentThisHour }` injected into named and anonymous queries and stripped from the returned payload; a `wcl_cost` log line with `op`, `points_this_hour` and `delta`
- [X] T013 [P] [US1] Create `backend/tests/test_cache_families.py` (uses `fake_redis` and an httpx `MockTransport` WCL fake). Cover: the token is fetched once across two client instances on different loops, and a 401 forces a reload (oauth_token); `current_patch()` and `raid_zone_ids()` together send one `MENU_DISCOVERY` request (world_zones); a character zone-rankings call twice → 1 char_id request + 1 rankings request; an unknown character twice → 1 request then `neg_hit`; `get_report_fights` and `get_report_metadata` on the same code → 1 request (report_summary); an unfinished report (endTime < 2 h ago) is written with TTL ≤ 120 s·1.1; `get_report_table` with `source_id>0` is cached and with `source_id=0` is not; no `wcl:` key contains the tenant or user id used in the test

### Implementation for User Story 1

- [X] T014 [US1] In `wcl_agent/wcl_client.py` `AsyncWCLClient._fetch`, add the 429/5xx retry (max 2, backoff `0.5·2ⁿ` s + jitter, `Retry-After` ≤ 10 s), inside the existing `asyncio.timeout` (contract W3). Impact-check `_fetch` first
- [X] T015 [US1] In `wcl_agent/wcl_client.py`, add `_with_cost(query) -> str` (inserts `rateLimitData { pointsSpentThisHour }` after the first top-level `{` following the operation header; skip queries that already select `rateLimitData`) and cost logging in `_fetch`: parse `pointsSpentThisHour`, remove it from the payload before returning, and log `wcl_cost op=<operation name or "anonymous"> points_this_hour=N delta=M` at INFO using a per-process last-seen value (contract W4). Make `acheck_rate_limit` still work (it selects `rateLimitData` itself)
- [X] T016 [US1] In `wcl_agent/wcl_client.py`, change `_tokens` to a memo of `OAuthToken` with `expires_at`, and make `_token()` use the memo first, then `get_or_load(CacheFamily.OAUTH_TOKEN, keys.OAUTH_TOKEN, OAuthToken, loader, ttl=expires_in-60)`. The loader posts to `TOKEN_URL` and reads `expires_in`. A 401 drops the memo entry and reloads with `force_refresh=True` (contract W5). Keep `_auth_lock`. Impact-check `_token` first (HIGH)
- [X] T017 [US1] In `wcl_agent/menu.py` (patch imports menu, so it lives there to avoid a cycle), add `load_world_zones() -> list[dict]` using `get_or_load(CacheFamily.WORLD_ZONES, keys.WORLD_ZONES, WorldZones, loader)`, and make `current_patch()` and `raid_zone_ids()` use it
- [X] T018 [P] [US1] Switch the other `MENU_DISCOVERY` call sites to `patch.load_world_zones()`: `find_encounter` in `wcl_agent/tools.py` and the menu loader in `wcl_agent/menu.py`. Keep their result shapes unchanged
- [X] T019 [US1] In `wcl_agent/report_tools.py` (next to the character tools), add `resolve_character(name, server, region, *, force_refresh=False) -> CharacterRef | None` using `get_or_load(CacheFamily.CHAR_ID, keys.char_id(...), CharacterRef, loader)`. The loader query is `characterData { character(name:, serverSlug:, serverRegion:) { id name classID server { slug region { slug } } } }` and returns `None` when the character is null
- [X] T020 [US1] In `wcl_agent/report_tools.py`, rework `get_character_zone_rankings` and `get_character_encounter_rankings`: call `resolve_character` first (`None` → the existing "not found" error dict), then query by `character(id: $id)` through `get_or_load(CacheFamily.CHAR_OVERVIEW, keys.char_zone/char_enc(...), CharacterRankings, loader)`. Apply `_acap` + `with_envelope` after the cache. The agent-visible return shape stays the same
- [X] T021 [US1] In `wcl_agent/report_tools.py`, add `load_report_summary(code) -> ReportSummary | None`: one query (the current `get_report_fights` query plus `endTime`), cached under `report_summary` with `ttl = family default if characters.is_finished(end_time_ms) else unfinished_ttl`. Rewrite `get_report_fights` and `get_report_metadata` as projections of it, keeping both return shapes unchanged
- [X] T022 [US1] In `wcl_agent/report_tools.py` `get_report_table`, when `source_id > 0` wrap the fetch in `get_or_load(CacheFamily.REPORT_PLAYER, keys.report_player(...), PlayerTable, loader)`. The loader's query also selects the report's `endTime` for the finished/unfinished TTL. `source_id == 0` is unchanged
- [X] T023 [US1] In `backend/app/services/recent_raids.py`, rework `fetch_report_details` to build `ReportDetails` from `load_report_summary(code)` per code, run with `wcl_agent.aio.gather_settled`, where a `None` or an error skips that code (same behaviour as today's per-code fallback). Remove the batched `report_details_query` call. Impact-check first
- [X] T024 [US1] In `backend/app/services/recent_raids.py`, rework `fetch_listed_reports` to call `resolve_character` and then `get_or_load(CacheFamily.CHAR_REPORTS, keys.char_reports(id, limit), CharacterReports, loader)` for each character (single-character `recentReports` query), run with `gather_settled`, merging into `ListedReport` exactly as today. Remove the batched `recent_reports_query(..., cache=False)` call. Impact-check first
- [X] T025 [US1] Delete `recent_reports_query` and `report_details_query` from `wcl_agent/queries.py` once T023/T024 have no remaining callers (confirm with GitNexus `context` and a text search)
- [X] T026 [US1] Update `backend/tests/test_recent_raids.py` for the per-character and per-report fakes (the "final reports are never fetched again" and "a live report stays non-final and is fetched again" tests must still pass), and run `uv run pytest -q`

**Checkpoint**: US1 is fully functional with `fake_redis`. Both caches still exist (the old one is retired in Phase 8).

---

## Phase 4: User Story 2 - The chat keeps working when the cache is unavailable (Priority: P1)

**Goal**: Redis failure, corrupt data and the off switch never break or slow a chat answer.

**Independent Test**: stop Redis (or make the fake raise) and ask a question: a correct answer comes back, nothing is written, and `redis_error` is counted once Redis returns (quickstart US2).

### Tests for User Story 2

- [X] T027 [P] [US2] In `backend/tests/test_wcl_cache.py`, add fail-open tests: a client whose every command raises `redis.exceptions.ConnectionError` → the loader is called, the value is returned, no exception escapes, and the process `redis_error` counter goes up; the 5 s circuit sends no Redis call for the second lookup (patch time); the `redis_error` count is flushed into the metrics hash on the next successful write; `WCL_CACHE_ENABLED=false` → no Redis calls and no metrics (C8); with no `REDIS_URL`, `wcl_agent` imports and works
- [X] T028 [P] [US2] In `backend/tests/test_cache_families.py`, add: Redis down during `_token()` → at most one OAuth request for many WCL calls (the memo protects the hot path); WCL down and the data not cached → the tool returns its existing `{"status": "error", ...}` dict, and nothing is cached

### Implementation for User Story 2

- [X] T029 [US2] In `wcl_agent/cache.py`, wrap every Redis interaction in `get_or_load` and `_record` with `except RedisError` (including timeouts) → `redis_error`, then call the loader directly and skip writes (C7). Add a per-loop `_down_until` circuit (5 s) checked before contacting Redis, and a process-level `_pending_redis_errors: Counter[CacheFamily]` that is flushed into the next successful metrics pipeline
- [X] T030 [US2] In `wcl_agent/cache.py`, log Redis unavailability at WARNING at most once per circuit opening (not once per lookup), and its recovery at INFO

**Checkpoint**: US1 and US2 both pass. The cache is optional at runtime.

---

## Phase 5: User Story 5 - Developers get the cache with the standard local stack (Priority: P2)

**Goal**: `docker compose up --build` brings up a health-checked, bounded, non-persistent Redis, and the backend uses it.

**Independent Test**: from a clean checkout, `docker compose up --build`; `docker compose ps` shows redis healthy; `CONFIG GET maxmemory-policy` = `allkeys-lru`; a repeated question creates `wcl:v1:*` keys (quickstart US5).

- [X] T031 [US5] Add the `redis` service to `docker-compose.yml` exactly as in contracts/config-and-compose.md (`redis:8-alpine`, `--maxmemory 256mb --maxmemory-policy allkeys-lru --save "" --appendonly no`, `redis-cli ping` healthcheck, port `6379:6379`, no volume). Add `REDIS_URL: redis://redis:6379/0` to `backend.environment` and `redis: condition: service_healthy` to `backend.depends_on`. Update the header comment to list redis
- [X] T032 [P] [US5] Update `.env.example`: add `REDIS_URL=redis://localhost:6379/0` and every `WCL_CACHE_*` / `WCL_NEG_CACHE_TTL` / `WCL_METRICS_RETENTION_DAYS` setting (commented, with defaults and one-line explanations in the file's style). Note that compose overrides `REDIS_URL` for the backend container
- [X] T033 [US5] In `wcl_agent/wcl_client.py` `aclose_clients()`, also await `cache.aclose_redis()` (contract W6), so the FastAPI lifespan in `backend/app/main.py` closes the Redis pools without a separate call
- [ ] T034 [US5] Live check: `docker compose up --build`, then run quickstart §2 "US5 – stack wiring" plus one repeated character question, and record the result in this file's Notes section

**Checkpoint**: the full local stack runs with Redis.

---

## Phase 6: User Story 3 - Operator sees how well each kind of cached data performs (Priority: P2)

**Goal**: `GET /api/admin/cache-stats?days=N` shows the per-family counts, hit rate, average load time and status, plus Redis health.

**Independent Test**: seed the metric hashes with known numbers, call the endpoint as an admin, and check the numbers and statuses; a non-admin gets 403 (quickstart US3).

### Tests for User Story 3

- [X] T035 [P] [US3] Create `backend/tests/test_cache_stats.py`: a pure `summarize` test (window sums across days, `hit_rate = (hit+neg_hit)/(hit+neg_hit+miss)`, `avg_load_ms`, `ok`/`review`/`no_data` at each family's threshold, all seven families always present, days outside the window ignored); endpoint tests using the `as_user` / admin fixtures from `backend/tests/conftest.py`: admin 200, non-admin 403, signed-out 401, `days=0` and `days=36` → 422, Redis down → 200 with `available: false` and `redis: null`, cache disabled → `enabled: false`

### Implementation for User Story 3

- [X] T036 [P] [US3] Add the `FamilyStats`, `RedisHealth` and `CacheStats` Pydantic models to `backend/app/schemas.py` (data-model.md)
- [X] T037 [US3] In `wcl_agent/cache.py`, add `summarize(per_day: dict[CacheFamily, list[dict[str, int]]]) -> dict` (pure) and `async read_stats(days) -> dict`: `HGETALL` each family × day hash in one pipeline, plus `INFO stats` (`keyspace_hits`, `keyspace_misses`, `evicted_keys`) and `INFO memory` (`used_memory`). Redis down or disabled → the degraded shape from contracts/cache-stats-api.md. Return plain data; the backend validates it into `CacheStats`
- [X] T038 [US3] Create `backend/app/api/cache_stats.py`: `router = APIRouter(prefix="/api/admin", tags=["admin"])` with `GET /cache-stats` (`days: int = Query(7, ge=1, le=35)`, `Depends(require_platform_admin)`, `response_model=CacheStats`), and include it in `backend/app/main.py` next to `admin_users.router`

**Checkpoint**: the stats endpoint works against `fake_redis` and against live compose.

---

## Phase 7: User Story 4 - User can force a fresh lookup (Priority: P3)

**Goal**: "check again" bypasses the cache for a character, at most once per user per character per minute.

**Independent Test**: ask about a character, say "check again" → a fresh WCL request; say it again within a minute → no request, and the agent says it just refreshed (quickstart US4).

### Tests for User Story 4

- [X] T039 [P] [US4] In `backend/tests/test_cache_families.py`, add: `force_refresh=True` reloads and overwrites the `char_overview` key; a second forced refresh by the same user within 60 s is served from the cache with `"refresh": "skipped_recent"`; a different user may refresh at once; the `chat:refresh:` key holds the user id and no `wcl:` key does; with Redis down, `try_claim_refresh` returns True

### Implementation for User Story 4

- [X] T040 [US4] In `wcl_agent/cache.py`, add the `_refresh_actor` ContextVar with `set_refresh_actor` / `get_refresh_actor`, and `try_claim_refresh(user_id, char_id) -> bool` (`SET keys.refresh(...) 1 NX EX 60`; True when Redis is unavailable or there is no actor)
- [X] T041 [US4] Add `force_refresh: bool = False` to `get_character_zone_rankings` and `get_character_encounter_rankings` in `wcl_agent/report_tools.py` (document it in their docstrings — ADK builds the tool schema from them). When it is set and `try_claim_refresh(get_refresh_actor(), char.id)` succeeds, pass `force_refresh=True` to the `char_overview` `get_or_load` and add `"refresh": "done"`; otherwise add `"refresh": "skipped_recent"`
- [X] T042 [US4] In `backend/app/api/ws.py`, call `set_refresh_actor(str(user_id))` for the turn where the WS handler currently calls `set_cache_scope(str(tenant_id))` (keep `set_cache_scope` until T045). Use the signed-in user's id from the WS identity. Impact-check `_handle_turn`
- [X] T043 [US4] In `wcl_agent/agent.py`, add one instruction line: when the user explicitly asks to refresh or check a character again, call the character tool with `force_refresh=True`; if the result says `skipped_recent`, tell the user it was refreshed moments ago. Also adjust the line near "lookups are cached" so it doesn't claim every lookup is cached

**Checkpoint**: all five stories work.

---

## Phase 8: Retire the in-process cache (cross-cutting, FR-025, FR-008)

**Purpose**: remove the old cache and tenant scoping now that every family is on Redis.

- [X] T044 In `wcl_agent/wcl_client.py` `AsyncWCLClient.query`: remove the `cache=` kwarg and all `get_cache()` / `ttl_for` / `is_rate_limit` use. Keep single-flight, keyed by `sha256(query + json.dumps(variables, sort_keys=True))` computed locally (contract W1/W2). Remove the `cache=False` argument from any remaining caller. Impact-check `query` (treat as HIGH: about 20 dynamic call sites)
- [X] T045 Remove from `wcl_agent/cache.py`: `TTLCache`, `get_cache`, `cache_key`, `ttl_for`, `is_report_scoped`, `is_rate_limit`, `report_ttl`, `leaderboard_ttl`, `max_bytes`, `DEFAULT_*` old constants, `_scope_prefix`, `set_scope_prefix` and `get_scope_prefix`, and rewrite the module docstring for the Redis design. Remove the `set_cache_scope` import and call from `backend/app/api/ws.py`, the `wcl_cache_ttl_report_s` / `wcl_cache_ttl_leaderboard_s` fields from `backend/app/config.py`, and `WCL_CACHE_TTL_REPORT_S`, `WCL_CACHE_TTL_LEADERBOARD_S`, `WCL_CACHE_MAX_BYTES` from `.env.example`. Impact-check `cache_key`, `get_cache` and `set_scope_prefix` (HIGH)
- [X] T046 [P] Update the tests that used the old cache: in `backend/tests/test_tenant_isolation.py`, replace the cache-scoping test with "two tenants asking about the same character share one `wcl:` entry, and no `wcl:` key contains either tenant id"; in `backend/tests/test_wcl_async.py`, `backend/tests/test_tool_concurrency.py`, `backend/tests/test_wcl_loop_lag.py` and `backend/tests/test_recent_raids.py`, drop `get_cache` / `cache_key` use; keep 013's single-flight and cancellation tests passing
- [X] T047 Run `grep -rn "get_cache\|cache_key\|set_scope_prefix\|cache=False\|WCL_CACHE_TTL_REPORT_S\|WCL_CACHE_MAX_BYTES" --include=*.py --include=*.md --include=.env.example .` (excluding `specs/`, `qa-reports/` and `node_modules/`) and fix any leftovers. Then run `uv run pytest -q`

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T048 [P] Update `README.md` and `documentation/ai_guide.md`: the Redis service, the new env settings, the stats endpoint, and the fact that WCL data is now shared across tenants (supersedes feature 006 FR-019). Link `documentation/redis_cache_spec.md`
- [X] T049 [P] Update `specs/013-welcome-recent-raids/contracts/wcl-async-client.md` to mark G2 (cache) as withdrawn by feature 014, with a pointer to `specs/014-redis-wcl-cache/contracts/cache-client.md`
- [ ] T050 Live verification against compose: quickstart §2 US1–US4 (repeat question, misspelt name, `docker compose stop redis` mid-chat, stats endpoint as admin and non-admin, "check again" twice). Record the results in the Notes section below
- [ ] T051 SC-002 load check: replay 100 realistic questions with `WCL_CACHE_ENABLED=false` and then `true` (quickstart §4). Compare the summed `wcl_cost delta` and the per-family hit rates, and record the numbers and any TTL changes in the Notes section
- [X] T052 Run `node .gitnexus/run.cjs detect-changes --scope all --repo .` (re-run if `partial` or `truncated`), review the affected processes, then `uv run pytest -q` before committing

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (1)** → **Foundational (2)** → the user story phases.
- **US1 (3)** depends on Foundational.
- **US2 (4)** depends on Foundational. Its tests T028 use the US1 token flow (T016), so do US2 after US1, or run T027/T029/T030 in parallel with US1 and T028 after T016.
- **US5 (5)** depends only on Setup for T031/T032. T033 needs T008. It can run in parallel with US1. T034 needs US1 to see `wcl:` keys.
- **US3 (6)** depends on Foundational (metrics, T010). It is independent of US1 but more useful once US1 records traffic.
- **US4 (7)** depends on US1 (T019, T020).
- **Retire (8)** depends on US1 (every former cache consumer moved) and on US4's T042 (the `ws.py` hook point moved).
- **Polish (9)** depends on everything.

### Within phases

- T006 → T007 → T008 → T009 → T010 (the same file, `wcl_agent/cache.py`, in sequence).
- T014 → T015 → T016 (same file, `wcl_client.py`).
- T017 → T018; T019 → T020; T021 → T022 → T023; T019 + T021 → T024 → T025 → T026.
- T029 → T030; T036 + T037 → T038; T040 → T041 → T042 → T043; T044 → T045 → T046 → T047.

### Parallel opportunities

- Setup: T002 ∥ T003 (after T001).
- Foundational: T004 ∥ T005 ∥ T011 (write the tests against the contract) while T006–T010 proceed.
- US1: T012 ∥ T013 (tests first). T018 ∥ T019 once T017 is done. The `wcl_client.py` chain (T014–T016) ∥ the `report_tools.py` / `patch.py` chain.
- US5 (T031, T032) ∥ US1.
- US3 tests and schemas (T035, T036) ∥ any US1 work.
- Polish: T048 ∥ T049.

### Parallel example: User Story 1

```text
Task: "T012 client retry/cost tests in backend/tests/test_wcl_async.py"
Task: "T013 family tests in backend/tests/test_cache_families.py"
then
Task: "T014–T016 wcl_client.py chain"          ∥   Task: "T017 load_world_zones in wcl_agent/patch.py"
Task: "T018 tools.py / menu.py switch"         ∥   Task: "T019 resolve_character in wcl_agent/characters.py"
```

---

## Implementation Strategy

### MVP first (US1 + US2, both P1)

1. Phases 1–2: dependencies, settings, models, `get_or_load` + metrics, tests green.
2. Phase 3 in the design doc's rollout order: **oauth_token, world_zones, char_id first** (T016–T019). Check the numbers. Then char_overview, report_summary, report_player, char_reports.
3. Phase 4: fail-open. **Stop and validate**: the MVP is safe to run even with no Redis.

### Incremental delivery

4. US5 (compose) as soon as Phase 2 is done, so live checks are possible.
5. US3 stats → a week of observation (design doc §10.4).
6. US4 refresh.
7. Phase 8 retires the old cache. Only after this is the cross-tenant sharing (FR-008) fully in effect.
8. Polish and the SC-002 load check.

## Notes

- [P] = different files, no dependency on an incomplete task.
- Tool return shapes seen by the agent must not change (contracts/cache-client.md), except for the optional `refresh` field.
- Commit after each phase, after `detect-changes`.
- Live-check results (T034, T050, T051) are recorded here.

### Implementation log (2026-10-18)

- Suite: `uv run pytest -q` → 579 passed, 3 skipped (the old-cache tests were removed; new:
  `test_wcl_cache.py` 22, `test_cache_families.py` 15, `test_cache_stats.py` 13, client tests in
  `test_wcl_async.py`). `-m perf` loop-lag test passes.
- **T034 (partial)**: `docker compose up -d redis` → healthy; `maxmemory-policy allkeys-lru`,
  `save ""`, `maxmemory 268435456`, Redis 8.10.2. Against it (DB 15, flushed): 10 concurrent
  misses → 1 load + 9 hits, TTL in the jittered 24 h band, metrics hash written; `read_stats`
  returns per-family numbers and real INFO health. **Open**: a repeated chat question through
  the full stack (needs ADC credentials + `docker compose up --build`).
- **T050 / T051 open**: live US1–US4 walkthrough and the 100-question cache on/off replay need
  the running stack with Vertex credentials.
- T052: `detect-changes --scope all` → 32 files, 267 symbols, 110 flows, risk **critical**
  (not partial/truncated) — expected: every WCL path changed by design; covered by the suite.
- Deviations from the task text: `characters.py` became `normalize.py` (import cycle);
  `load_world_zones` lives in `menu.py`, `resolve_character` in `report_tools.py`;
  `get_or_load` also takes `ttl` as a function of the loaded value (token expiry, finished vs
  live report); no jitter on `oauth_token`; INFO-less Redis gives `redis: null`;
  `drain_metrics` only awaits the current loop's tasks.

### Performance fixes from QA sweep 2026-10-18 (qa-reports/2026-10-18/performance.md)

- [X] PERF-001 Batch the recent-raids refresh again: `cache.get_many_or_load`, `report_tools.resolve_characters` / `load_report_summaries`, aliased queries in `wcl_agent/queries.py`; cold refresh ≈ 3 requests (was 2C + k)
- [X] PERF-002 `context_trim.ELIDED_NOTE` and the agent's EVIDENCE_PLAN no longer promise free re-fetches
- [X] PERF-003 In-process memo for `char_id` (1 h) and `world_zones` (5 min) in front of Redis (`FamilyConfig.memo_s`)
- [X] PERF-004 A 429 whose `Retry-After` exceeds 10 s fails at once and blocks later calls until then; no backoff that would outlast the query deadline
- [X] PERF-005 Leaderboard pages 2..N fetched concurrently after page 1 (`tools._fetch_rankings`)
- [X] PERF-006 Same-process single-flight inside `get_or_load`; `WCL_CACHE_LOCK_MS` default 90000 (> 75 s query timeout)
- [X] PERF-007 Metrics counted in-process and flushed every 2 s in one pipeline (counts kept on failure); EXPIRE once per hash; values > 256 KB decoded off the loop
- [ ] PERF-008 Left as is: `char_reports` TTL stays 300 s (spec FR-001); with batching a miss costs one shared request. Its stats status may read "review" by design — decide whether to raise the TTL (staler welcome page) or accept
- [X] PERF-009 Injected `_cost` selects the full budget; `acheck_rate_limit` answers from a ≤ 30 s snapshot (benchmark, `check_rate_limit` tool)

