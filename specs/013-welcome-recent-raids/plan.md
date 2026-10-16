# Implementation Plan: Welcome Page with My Recent Raids

**Branch**: `013-welcome-recent-raids` | **Date**: 2026-10-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/013-welcome-recent-raids/spec.md`

## Summary

When no chat is open, the app shows a welcome page listing the user's 20 most recent raids across all of their own characters. Each raid card starts the existing one-click investigation.

**Fetching and storage**:
- Raids are fetched in the background in two steps: an aliased `recentReports` list query, then report details fetched only for new or not-yet-final reports.
- Results go into three new tenant-scoped tables. A report's details are never fetched again once its log has ended.
- Refreshes are coordinated by an atomic claim on a per-tenant refresh row. That limits them to one every 15 minutes, works across instances and reclaims runs left stale by a crash.
- The page polls while a refresh is running.

**Side mission (US4)**:
- All Warcraft Logs access moves from `requests`-on-threads to one `httpx.AsyncClient`-based client.
- The new client adds real cancellation, a bytes-backed cache with no deepcopy, async single-flight and timeouts.
- An interactive/background `LaneLimiter` keeps background work from crowding out chat.
- The migration ships in three phases: async core plus bridge, then async tools, then deleting the thread pools. Every phase leaves the app working.

## Technical Context

**Language/Version**: Python 3.14 (backend, `wcl_agent`), TypeScript + React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy async (asyncpg), Alembic, Pydantic v2, Google ADK, **httpx**, which is already a dependency and now becomes the WCL transport. Frontend: Tailwind v4 + shadcn/ui. **No new dependencies.** `requests` is removed if nothing else imports it.

**Storage**: PostgreSQL with RLS. New migration `0010_recent_raids` adds `recent_raids`, `recent_raid_characters` and `recent_raid_refresh` (see [data-model.md](./data-model.md)). The tests use SQLite, which supports `UPDATE … RETURNING` from 3.35.

**Testing**: pytest (`backend/tests/`) with fake WCL transports through `httpx.MockTransport`, which needs no new dependency. A `perf`-marked loop-lag test. Frontend checks are `tsc -b && vite build`.

**Target Platform**: Linux server (docker compose; Cloud Run target per `documentation/deployment.md`) and a modern browser.

**Project Type**: Web application: a FastAPI backend in `backend/app`, the ADK agent and WCL package in `wcl_agent/`, and a React frontend in `frontend/src`.

**Performance Goals**:
- Return visits show stored raids within 1 s (SC-001). A first fetch takes under 10 s (SC-002).
- Abandoned turns release WCL capacity within 5 s (SC-007).
- Streaming stalls caused by WCL work stay under 20 ms with 4 tool-heavy turns (SC-008). Today's worst case is 157 ms.
- A refresh adds zero delay to chat lookups (SC-009).

**Constraints**:
- FR-012: each final report's details are fetched once.
- FR-020: background work never takes more than its lane cap and yields to queued chat work.
- FR-023: every existing tool returns equivalent results.
- No DB transaction is held across a WCL call.

**Scale/Scope**:
- Up to 10 own characters per tenant. At most 20 raids shown. One list request plus at most one detail request per refresh.
- Side-mission scope:
  - 6 `wcl_agent` modules converted to async (`report_tools`, `tools`, `fight_time`, `cooldowns`, `benchmark`, `patch`), plus `wcl_client`, `cache` and `menu`;
  - 4 backend callers: `ws.py`, `api/guides.py`, `services/raids.py` and `services/guide.py`;
  - 2 deletions: `threading_utils.py`, and the tool pool in `agent.py`;
  - test fakes in `backend/tests/wcl_fakes.py` and 3 test modules.

All earlier unknowns (WCL query shape, refresh coordination, delivery mechanism, migration strategy) are resolved in [research.md](./research.md).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. DRY & reuse-first | ✅ | **One** WCL client: the sync client is replaced, not paralleled, and the Phase A bridge keeps a single cache, cap and lane system during the move. Investigation reuses `POST /api/raids/{code}/investigate`, `_build_label` and the kickoff (R10). Guide `_spawn` moves to a shared `services/background.py` used by guides and recent raids (R5). The raid-zone check reuses the `MENU_DISCOVERY` and `_offers_heroic` logic. The welcome page reuses the new-chat and greeting flow (R11). |
| II. Step-wise delivery | ✅ | Increments, each verifiable on its own: (1) async core, lanes and bytes cache behind the bridge; (2) migration, models and repository with claim tests; (3) refresh service and REST; (4) welcome panel UI; (5) investigate-from-recent; (6) tools converted to async, one module at a time; (7) cleanup of threads and the bridge, plus the loop-lag and cancellation tests. |
| III. Simplicity / YAGNI | ✅ ⚠ | No job queue, no scheduler, no SSE or WebSocket push, no shared cross-tenant report table, no per-turn WCL cap (PERF-106). One justified addition, `LaneLimiter` (about 40 lines), is listed in Complexity Tracking. The **temporary** Phase A bridge is deleted in Phase C. |
| IV. Typed contracts | ✅ | Pydantic: `RecentRaidOut`, `RecentRaidCharacterOut`, `RecentRaidsRefreshOut`, `RecentRaidsResponse`. Dataclasses: `ListedReport`, `ReportDetails`. `Lane` is a `Literal`. Frontend types mirror the Pydantic models. |
| V. Async FastAPI | ✅ | This feature *strengthens* the principle. New endpoints are `async def`, and WCL I/O becomes native async (no executor), which retires the "offload blocking work" exception for WCL. Background refreshes hold no transaction across awaits on the network. |
| VI. GitNexus awareness | ✅ ⚠ | `impact` (upstream) was run on `query`, `off_loop`, `run_in_tool_pool`, `gather_threads`, `investigate_raid`, `_spawn`, `capture_raid` and `TTLCache`. **It returned CRITICAL for all except `query` (UNKNOWN / MEDIUM 45), but the counts are near-identical (154–158) for unrelated symbols (`investigate_raid` lists the WCL tool processes).** That matches the known index quirk (see memory), so the results are treated as **UNKNOWN**. Callers were confirmed by text search instead (R9 lists all 18 WCL call sites across 6 modules and the 4 backend callers). Each Phase B and C task re-runs `impact` per symbol before editing. **Warning: `off_loop`, `run_in_tool_pool`, `gather_threads` and `TTLCache` are on the hot path of every chat tool. The phased plan exists because of that risk.** |
| VII. shadcn/ui via MCP | ✅ | Welcome-panel parts come from existing `components/ui/`: Card, Item, Badge, Skeleton, Empty, Alert, Button and Spinner. The shadcn MCP search and audit checklist run during the UI task. Nothing hand-built is planned. |

**Post-design re-check**: still passes. The design adds three tables, one service module (`recent_raids.py`), one helper module (`background.py`), one router (`api/recent_raids.py`), `LaneLimiter` and one frontend component (`WelcomePanel`). It removes `threading_utils.py`, the tool thread pool, the sync client and the per-call thread pools. The net layer count is unchanged or lower.

## Project Structure

### Documentation (this feature)

```text
specs/013-welcome-recent-raids/
├── plan.md               # this file
├── research.md           # Phase 0: R1–R12 decisions
├── data-model.md         # Phase 1: 3 tables, API and value models
├── quickstart.md         # Phase 1: run and verify
├── contracts/
│   ├── rest-recent-raids.md   # GET/POST recent-raids, extended investigate, UI states
│   └── wcl-async-client.md    # AsyncWCLClient, LaneLimiter, lanes, removals
├── checklists/requirements.md
└── tasks.md              # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
wcl_agent/
├── wcl_client.py        # REWRITE: AsyncWCLClient, LaneLimiter, background_lane, get_client per loop, aclose_clients
├── cache.py             # CHANGE: store raw bytes, parse on hit, drop deepcopy
├── threading_utils.py   # Phase A: loop-capture bridge · Phase C: DELETE
├── report_tools.py      # async tools (+ gather_settled)
├── tools.py             # async tools
├── fight_time.py        # async helpers
├── cooldowns.py         # async tool
├── benchmark.py         # async tool
├── patch.py             # async current_patch
├── menu.py              # asyncio.run shim (CLI only)
├── models.py            # local thread-gather for non-WCL probes (moved from threading_utils)
└── agent.py             # register TOOLS directly (no off_loop)

backend/app/
├── db/models.py                      # + RecentRaid, RecentRaidCharacter, RecentRaidRefresh
├── db/repository.py                  # + list_recent_raids, upsert_listed_reports, set_report_details,
│                                     #   link_characters, claim_refresh, finish_refresh, get_refresh
├── services/background.py            # NEW: spawn(coro, key) (moved from guide._spawn)
├── services/recent_raids.py          # NEW: list step, detail step, run_recent_raid_refresh, character_set hash
├── services/guide.py                 # use background.spawn; resolve_active_spec awaits in background_lane
├── services/raids.py                 # await get_report_metadata directly
├── api/recent_raids.py               # NEW: GET /api/recent-raids, POST /api/recent-raids/refresh
├── api/raids.py                      # investigate: fall back to recent raid → upsert tracked raid
├── api/ws.py, api/guides.py          # await current_patch in background_lane
├── schemas.py                        # + RecentRaid* models
├── config.py                         # + wcl_background_concurrency, recent_raids_* settings
└── main.py                           # include router; lifespan shutdown → aclose_clients()

backend/migrations/versions/0010_recent_raids.py   # NEW: 3 tables + RLS policies

backend/tests/
├── wcl_fakes.py                 # async fake client / MockTransport helpers
├── test_wcl_async.py            # NEW: cache bytes, single-flight, cancel, timeout, lanes (SC-007, SC-009)
├── test_wcl_loop_lag.py         # NEW (perf): SC-008
├── test_recent_raids.py         # NEW: list/detail steps, dedupe, FR-016, claim gate, stale reclaim, two sessions (SC-010)
├── test_tool_concurrency.py     # REWRITE for async
└── test_wcl_cache.py, test_provenance.py, test_api.py   # adapt to async fakes / extended investigate

frontend/src/
├── components/WelcomePanel.tsx  # NEW: raid cards + all FR-007 states + polling
├── App.tsx                      # render WelcomePanel in the no-conversation state; card → handleInvestigateRaid
├── api/restClient.ts            # + getRecentRaids, refreshRecentRaids
└── types.ts                     # + RecentRaid types

documentation/deployment.md       # note: Cloud Run "CPU always allocated" for background refreshes (R4)
```

**Structure Decision**: The existing web-application layout is kept. Feature code follows the established router → service → repository split (`api/raids.py`, `services/raids.py`, `db/repository.py`). The WCL work stays inside the standalone `wcl_agent` package.

## Delivery Order (input for /speckit-tasks)

1. **US4 Phase A, async core.** `AsyncWCLClient`, `LaneLimiter`, the bytes cache and the bridge in `threading_utils` with the loop captured by `run_in_tool_pool`. Tests: `test_wcl_async.py` and the existing suite unchanged. *The app works on the new transport.*
2. **US3 storage.** Migration `0010`, models and repository, including `claim_refresh`/`finish_refresh`. Tests: claim gate, stale reclaim, two sessions (SC-010).
3. **US1 and US3 service and API.** `services/recent_raids.py` (async client, background lane, list then detail), `services/background.py` (with guides moved over), the `api/recent_raids.py` router. Confirm `ReportPagination` and `data` with one live call.
4. **US1 UI.** `WelcomePanel` with the states, polling and the shadcn MCP audit.
5. **US2.** Investigate falls back to the recent raid. The card click reuses `handleInvestigateRaid` and refreshes the raid list.
6. **US4 Phase B.** Tools converted to async one module at a time (callees first: `report_tools` → `fight_time` → `patch` → `benchmark` → `cooldowns` → `tools`; unconverted sync callers use `threading_utils.run_sync` until their own step), then the backend callers, with background ones wrapped in `background_lane()`. Run `impact` and the suite after each module.
7. **US4 Phase C.** Delete the bridge, `off_loop`, the pool and `gather_threads`, and drop `requests`. Add the loop-lag `perf` test (SC-008) and the cancellation test (SC-007). Update the deployment note and README settings.

Steps 1–5 deliver the welcome page (MVP: steps 2–5 could ship on the threaded client, but step 1 comes first so the new code is async from day one). Steps 6–7 finish the side mission.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| `LaneLimiter` (custom concurrency primitive, about 40 lines) | FR-020 requires a hard background cap **and** that background work yields to queued interactive work. SC-009 tests this. | Two plain semaphores (6 and 2) let background work take interactive slots while chat is queued. A priority-queue dispatcher needs a long-lived dispatcher task, which is more moving parts. |
| Temporary sync→async bridge in `threading_utils` (Phase A to B) | It lets the new client, cache and lanes ship before the six tool modules are converted (Principle II). Without it, everything would change in one step. | Converting all tools at once is a single multi-module change touching every chat tool. Two clients side by side would split the cache and the concurrency cap (Principle I). The bridge is deleted in Phase C. |
