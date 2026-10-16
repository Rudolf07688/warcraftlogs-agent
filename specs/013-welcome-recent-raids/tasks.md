---
description: "Task list for feature 013: welcome page with my recent raids, plus the async WCL side mission"
---

# Tasks: Welcome Page with My Recent Raids

**Input**: Design documents from `specs/013-welcome-recent-raids/`. These are plan.md, spec.md, research.md (R1–R12), data-model.md, contracts/rest-recent-raids.md, contracts/wcl-async-client.md and quickstart.md.

**Tests**: Included. The plan and research R12 name test files for SC-004, SC-005 and SC-007 to SC-010, and the existing suite must keep passing through the WCL migration (FR-023).

**Organization**:
- Phase 2 holds the shared foundation: the async WCL core (US4 Phase A, which the welcome page's code is written against) and the storage layer.
- Each user story after that is its own phase.
- US4 Phases B and C (async tools, then removing the threads) come last.

## Conventions for every task

- **GitNexus (constitution VI, CLAUDE.md)**: before editing any existing function, class or method, run `node .gitnexus/run.cjs impact "<symbol>" --direction upstream --repo .`.
  - Report the callers and the risk. Warn on HIGH or CRITICAL.
  - If counts are near-identical (around 150) for unrelated symbols, that is the known index quirk. Treat the result as UNKNOWN and confirm the callers with `grep -rn`.
  - Before any commit, run `node .gitnexus/run.cjs detect-changes --scope all --repo .`.
- **Test command**: `uv run --extra test pytest -q`. Run the whole suite at the end of every task that touches `wcl_agent/` or `backend/app/`. Frontend check: `cd frontend && npx tsc -b && npx vite build`.
- **Tenant scoping**: request handlers use `get_tenant_db`. Background work uses `backend.app.tenancy.context.tenant_scope(tenant_id)`. **Never hold a DB session open across a WCL `await`.**
- Paths are relative to the repo root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (a different file and no dependency on an unfinished task)
- **[Story]**: US1–US4, from spec.md

---

## Phase 1: Setup

**Purpose**: settings and test markers used by later phases.

- [X] T001 Add settings to `backend/app/config.py`, next to the existing WCL settings:
  - `wcl_background_concurrency: int = 2`
  - `wcl_query_timeout_s: int = 75`
  - `recent_raids_refresh_min_s: int = 900`
  - `recent_raids_stale_s: int = 300`
  - `recent_raids_limit: int = 20`
  - `recent_raids_refresh_timeout_s: int = 120`

  Add `WCL_BACKGROUND_CONCURRENCY=2` and `WCL_QUERY_TIMEOUT_S=75` (commented, with defaults) to `.env.example`. `wcl_agent` reads these two with `cache._env_int`, because the package stays standalone.
- [X] T002 [P] Register a `perf` pytest marker in `pyproject.toml` under `[tool.pytest.ini_options]` (`markers = ["perf: timing-sensitive benchmarks"]`), and add `addopts = "-m 'not perf'"` so the default run skips it. `-m perf` runs it.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the async WCL core with lanes (US4 Phase A, research R7–R9) and the recent-raids storage (data-model §1–3). Every user story depends on this phase.

**⚠️ CRITICAL**: no user-story work may start until this phase is complete and the full suite passes.

### Async WCL core (US4 Phase A)

- [X] T003 Change `TTLCache` in `wcl_agent/cache.py` to store values unchanged, with no `deepcopy` in `get` or `set`. The WCL client will store raw response `bytes`, which are immutable. Update the class and module docstrings to say values are raw bytes and callers parse them. Keep the key, TTL, byte-bound and LRU logic unchanged. Delete `from copy import deepcopy`. This closes PERF-105.
- [X] T004 Create `wcl_agent/aio.py` with:
  - `async def gather_settled(*aws) -> list[T | BaseException]`, which is `asyncio.gather(*aws, return_exceptions=True)` in input order;
  - `unwrap(result)`, moved from `wcl_agent/threading_utils.py` with the same behaviour.

  Leave a re-export (`from .aio import unwrap`) in `threading_utils.py` so existing imports keep working.
- [X] T005 In `wcl_agent/wcl_client.py`, add the lane machinery (contracts/wcl-async-client.md §LaneLimiter, research R8):
  - `Lane = Literal["interactive", "background"]`;
  - a `_lane: ContextVar[Lane]` with default `"interactive"`;
  - a `@contextmanager background_lane()`;
  - `class LaneLimiter(total, background_cap)`, built on one `asyncio.Condition` with counters `in_use`, `bg_in_use` and `interactive_waiting`. It provides an `@asynccontextmanager slot()` that implements rules L1–L3, and a waiter that is cancelled must decrement `interactive_waiting` in `finally`.
  - `_limiter()`, which returns one limiter per running loop from a `weakref.WeakKeyDictionary[loop, LaneLimiter]`. It is sized from `WCL_MAX_CONCURRENCY` (default 6) and `WCL_BACKGROUND_CONCURRENCY` (default 2, clamped to `1..total-1`).
- [X] T006 In `wcl_agent/wcl_client.py`, add `class AsyncWCLClient(client_id, client_secret, transport: httpx.AsyncBaseTransport | None = None)` per contracts/wcl-async-client.md G1–G9:
  - an `httpx.AsyncClient(timeout=httpx.Timeout(60, connect=5), limits=httpx.Limits(max_connections=16), transport=transport)`;
  - an `asyncio.Lock` for auth;
  - `async def query(query, variables=None, *, cache=True) -> dict`.

  How `query` behaves:
  - **Cache**: a hit returns `json.loads(bytes)`, or `await asyncio.to_thread(json.loads, b)` when `len(b) > 2_000_000`. `is_rate_limit(query)` or `cache=False` bypasses the cache.
  - **Single-flight**: `self._flights: dict[str, tuple[asyncio.Task, list[int]]]`. Each waiter count goes up on entry and down in `finally`. Callers `await asyncio.shield(task)`. When a cancelled waiter takes the count to 0, it cancels the task.
  - **Fetch**: `async with asyncio.timeout(WCL_QUERY_TIMEOUT_S): async with _limiter().slot(): resp = await http.post(...)`. Then `raise_for_status`. A `401` refreshes the token once and retries. A GraphQL `errors` payload raises `RuntimeError(json.dumps(errors, indent=2))`. Only successful payloads are stored, as `resp.content` with `ttl_for(...)` and `size=len(resp.content)`.
  - **Debug log** per fetch: `wcl inflight=<n> lane=<lane>`, used by quickstart US4.

  Also add:
  - `get_async_client()`: one client per running loop (`WeakKeyDictionary`), reading `WCL_CLIENT_ID` and `WCL_CLIENT_SECRET` with the same error message as `get_client`;
  - `async def aclose_clients()`: closes every client's `httpx.AsyncClient`;
  - `async def acheck_rate_limit()`.
- [X] T007 Turn the sync `WCLClient` in `wcl_agent/wcl_client.py` into a **bridge facade** (research R9 Phase A). `WCLClient.query(query, variables=None)` delegates to `threading_utils.run_sync(get_async_client().query(...))`, with the coroutine created inside the target loop: wrap it as `async def _q(): return await get_async_client().query(...)`. Then:
  - delete the `requests` session, `_inflight`, `_flights`, `_auth_lock`, `authenticate` and `_fetch`;
  - keep the names `get_client()` and `check_rate_limit()` working so existing call sites don't change.

  In `wcl_agent/threading_utils.py`:
  - add `_bridge_loop: ContextVar[asyncio.AbstractEventLoop | None]`;
  - set it to the running loop inside `run_in_tool_pool` **before** `contextvars.copy_context()`;
  - add `run_sync(coro_factory)`. When `_bridge_loop` is set and the current thread is not running that loop, it uses `asyncio.run_coroutine_threadsafe(coro_factory(), loop).result()`. Otherwise it uses `asyncio.run(coro_factory())` (CLI and sync unit tests).
  - Update the module docstring to say the bridge is temporary (Phase C deletes it).
- [X] T008 Call `await aclose_clients()` (from `wcl_agent.wcl_client`) in the `lifespan` shutdown of `backend/app/main.py`, before `await engine.dispose()`. Wrap it in `contextlib.suppress(Exception)`.
- [X] T009 [P] Write `backend/tests/test_wcl_async.py` with `httpx.MockTransport` responders and `AsyncWCLClient(..., transport=...)`. Monkeypatch the token endpoint response. Tests:
  1. A cache hit returns an equal but **distinct** object, and mutating it doesn't affect the next hit (FR-022).
  2. `rateLimitData` and `cache=False` always reach the transport.
  3. 10 concurrent identical queries cause exactly 1 POST.
  4. Cancelling 1 of 3 waiters leaves the other 2 with the result.
  5. Cancelling all waiters of a hanging fetch cancels it, and `_limiter().in_use` returns to 0 within 5 s (SC-007, at client level).
  6. A hanging transport with `WCL_QUERY_TIMEOUT_S=1` raises `TimeoutError` and frees the slot (FR-021).
  7. A GraphQL `errors` payload raises `RuntimeError` and is not cached.
  8. A `401` then `200` refreshes the token once.
  9. **Lanes (SC-009)**, using `LaneLimiter(6, 2)` directly:
     - background can't hold a 3rd slot;
     - an interactive acquire succeeds while background holds 2 slots and another background waiter is queued;
     - a background acquire waits while `interactive_waiting > 0`, even when slots are free.
- [X] T010 Adapt the existing WCL tests to the new transport so the whole suite is green:
  - In `backend/tests/test_wcl_cache.py`, replace the `counting_post` / `requests` patching with a fixture that installs an `httpx.MockTransport` on the loop's `AsyncWCLClient`, through monkeypatching `get_async_client`.
  - Rename `test_deep_copy_isolation` to `test_hits_are_isolated_copies`.
  - The single-flight tests use the async client.
  - In `backend/tests/test_tool_concurrency.py`, port `test_wcl_requests_respect_the_concurrency_cap` to the `LaneLimiter` cap and `test_ttl_cache_survives_concurrent_access` to bytes values. Leave the `off_loop` and `gather_threads` tests until T046.

  Run the full suite.

### Shared background-task helper

- [X] T011 [P] Create `backend/app/services/background.py` containing `spawn(coro, key: Hashable) -> None`, moved from `_spawn` in `backend/app/services/guide.py` with the same behaviour: GC-safe `_bg_tasks` set, in-memory duplicate-key skip, closing the coroutine when there is no running loop. Then:
  - change `schedule_character_guide`, `schedule_guild_summary` and `ensure_spec_guide` in `guide.py` to call `background.spawn`;
  - delete `_spawn`, `_bg_tasks` and `_inflight` from `guide.py`;
  - check that tests patching `guide._spawn` or `_inflight` are updated (`grep -rn "_spawn\|_inflight" backend/tests`).

### Recent-raids storage

- [X] T012 Create the migration `backend/migrations/versions/0010_recent_raids.py` (`down_revision = "0009_guide_provenance"`):
  - the tables `recent_raids`, `recent_raid_characters` and `recent_raid_refresh`, exactly as data-model.md §1–3, with their constraints and indexes;
  - Postgres-only RLS enable, force, the `tenant_isolation` policy and grants, copied from the pattern in `0005_known_entities.py` (`_PREDICATE`, `_runtime_role`);
  - a full `downgrade()`.
- [X] T013 [P] Add the ORM models `RecentRaid`, `RecentRaidCharacter` and `RecentRaidRefresh` to `backend/app/db/models.py`, matching T012. Follow the `TrackedRaid` and `KnownPlayer` style (`_UUID`, `DateTime(timezone=True)`, `server_default=func.now()`). `RecentRaidCharacter.character_id` uses FK `user_characters.id` with `ondelete="CASCADE"`.
- [X] T014 [P] Create `backend/app/services/recent_raid_types.py` with the frozen dataclasses `ListedReport(code, title, zone_id, zone_name, guild_name, started_at, ended_at, character_ids: frozenset[uuid.UUID])` and `ReportDetails(ended_at, difficulty, bosses_pulled, bosses_killed, is_raid)` (data-model.md §4).
- [X] T015 Add repository functions to `backend/app/db/repository.py`, each taking `tenant_id=` like its neighbours:
  - `list_recent_raids(session, *, tenant_id, limit) -> list[tuple[RecentRaid, list[UserCharacter]]]`:
    - only `is_raid` rows that have at least one link to an existing `role="self"` character;
    - ordered by `started_at desc`, limited to `limit`;
    - each row's characters ordered by `UserCharacter.created_at`;
    - two queries (raids, then links joined to characters with `IN`). No N+1.
  - `upsert_listed_reports(session, *, tenant_id, reports: list[ListedReport]) -> list[str]`: inserts new rows (`is_raid=False`, `is_final=False` until details arrive), refreshes `ended_at`, `title` and `zone_*` on rows that aren't final, adds missing `recent_raid_characters` links, and returns the codes that need details (new, or `is_final=False`).
  - `set_report_details(session, *, tenant_id, code, details: ReportDetails, final_before: datetime)`: sets the details plus `details_fetched_at=now` and `is_final = details.ended_at < final_before`.
  - `get_recent_raid(session, code, *, tenant_id) -> RecentRaid | None`.
  - `get_refresh(session, *, tenant_id) -> RecentRaidRefresh | None`.
  - `claim_refresh(session, *, tenant_id, character_set: str, force: bool, min_gap_s: int, stale_s: int) -> uuid.UUID | None`:
    - first `INSERT … ON CONFLICT DO NOTHING`, using `sqlalchemy.dialects.postgresql.insert` or `sqlite.insert` chosen by `session.bind.dialect.name`;
    - then one `update(...).where(<gate from data-model §3>).values(status="running", run_id=new, started_at=now, character_set=character_set).returning(RecentRaidRefresh.run_id)`;
    - `force` only counts when `status == "failed"`.
  - `finish_refresh(session, *, tenant_id, run_id, ok: bool, error: str | None)`: `UPDATE … WHERE run_id = :run_id`, setting the status, `finished_at` and, on success, `last_success_at`. A stale `run_id` is a no-op.
- [X] T016 [P] Add the Pydantic models `RecentRaidCharacterOut`, `RecentRaidOut`, `RecentRaidsRefreshOut` and `RecentRaidsResponse` to `backend/app/schemas.py`, exactly as data-model.md §4. `status` is a `Literal`.
- [X] T017 Write `backend/tests/test_recent_raids_repo.py`, using the SQLite fixtures from `backend/tests/conftest.py`:
  - the first `claim_refresh` returns a `run_id`, and a second within `min_gap_s` returns `None`;
  - `force=True` wins only after `finish_refresh(ok=False)`;
  - a changed `character_set` opens the gate;
  - a `running` row backdated by 6 minutes can be claimed again (FR-026);
  - `finish_refresh` with the old `run_id` after a reclaim changes nothing;
  - **two separate sessions** call `claim_refresh` at the same time (`asyncio.gather`) and exactly one gets a `run_id` (SC-010);
  - `upsert_listed_reports` called twice with the same code from two characters gives 1 row and 2 links (SC-005);
  - deleting a `UserCharacter` removes its links, and `list_recent_raids` no longer returns a raid linked only to it (FR-016). Enable SQLite `PRAGMA foreign_keys=ON` in the fixture if it isn't already.

> **Implementation notes (Phase 2, 2026-10-16)**
> - `LaneLimiter` uses a FIFO of waiter futures with a synchronous `release()`, not an `asyncio.Condition`, so a cancelled holder always frees its slot without awaiting.
> - Bearer tokens are shared across loops by client id (`wcl_client._tokens`), so short-lived loops (CLI, bridge fallback) don't re-authenticate.
> - `ListedReport` gained `is_raid` (known from the zone id at list time), so raid cards show before their details arrive.
> - The concurrency-cap test moved from `test_tool_concurrency.py` to `test_wcl_async.py`.
> - Verified: 517 tests pass, the migration round-trips on Postgres, claim and upsert SQL work under RLS, and live `rateLimitData` works through both the async client and the sync bridge.

**Checkpoint**: the full suite passes on the async WCL core, the schema migrates (`uv run alembic -c backend/alembic.ini upgrade head`), and the repository is tested.

---

## Phase 3: User Story 1, see my recent raids when I arrive (Priority: P1) 🎯 MVP

**Goal**: with no chat open, the app lists up to 20 recent raids across all own characters, newest first, and fills the list in the background.

**Independent Test**: register an own character with public logs, open the app, and see the raid cards (zone, date and time, difficulty, characters, kills) within about 10 s. Reload and they appear within about 1 s (SC-001, SC-002).

### Tests for User Story 1

- [ ] T018 [P] [US1] Write the service and API tests in `backend/tests/test_recent_raids.py`. Use a fake async WCL responder: patch `backend.app.services.recent_raids.get_async_client` with an object whose `async query(query, variables, cache=True)` dispatches on `recentReports` / `reportData` / `worldData` in the query text. Tests:
  - a refresh stores raids, sets details, links characters, and leaves non-raid (Mythic+ zone) reports out of the list;
  - one report attended by 2 own characters appears once, with both names, in `GET /api/recent-raids` (SC-005);
  - `bosses_*` are `null` before details arrive;
  - with no own characters the response is `has_characters=false`, `raids=[]` and `refresh.status="idle"`, and no WCL call is made;
  - `GET /api/recent-raids` returns stored raids **without awaiting** a responder that blocks on an `asyncio.Event` (FR-010), and the response shows `refresh.status == "running"`.

### Implementation for User Story 1

- [ ] T019 [P] [US1] Add GraphQL builders to `wcl_agent/queries.py` (constitution I: query strings live in one module):
  - `recent_reports_query(n: int) -> str`, which builds aliases `c0..c{n-1}`, each `characterData { character(name: $n{i}, serverSlug: $s{i}, serverRegion: $r{i}) { recentReports(limit: $limit) { data { code title startTime endTime zone { id name } guild { name } } } } }` with matching `$n{i}: String!`… variable declarations. Use one `characterData` block per alias, or alias the `character` fields inside one `characterData`, whichever the live call in T020 accepts.
  - `report_details_query(n: int) -> str`, which builds `reportData { r{i}: report(code: $c{i}) { endTime zone { id } fights(killType: Encounters) { encounterID kill difficulty } } }`.
- [ ] T020 [US1] Create `backend/app/services/recent_raids.py` and add the **list step** (research R1):
  - `character_set_hash(chars) -> str`: sha256 of the sorted `name|server|region` in lowercase;
  - `async def fetch_listed_reports(chars: list[UserCharacter]) -> list[ListedReport]`:
    - **one** `await get_async_client().query(recent_reports_query(len(chars)), variables, cache=False)`;
    - the server slug comes from `report_tools._server_slug`, and the region is upper-case;
    - `startTime` and `endTime` in ms become UTC datetimes;
    - merge by `code` across aliases, combining `character_ids`;
    - characters whose alias returns `null` (not found) are skipped.

  **Before coding**, make one live call (`uv run python -I -c ...` with `.env` loaded) to confirm the `recentReports` pagination field is `data`, and adjust T019 if it isn't.
- [ ] T021 [US1] Add the **detail step** to `backend/app/services/recent_raids.py` (research R2):
  - `async def fetch_report_details(codes: list[str], raid_zone_ids: set[int]) -> dict[str, ReportDetails]` makes one `report_details_query(len(codes))` call (cached as usual, since it is report-scoped);
  - `bosses_pulled` and `bosses_killed` are distinct `encounterID` counts (killed means `kill is True`);
  - `difficulty` is the highest of {1, 3, 4, 5} among the boss fights, or `None`;
  - `is_raid = zone.id in raid_zone_ids`.

  Add `raid_zone_ids(zones) -> set[int]` to `wcl_agent/patch.py`. It reuses `_offers_heroic` and gets the zones from `MENU_DISCOVERY` through `await get_async_client().query(MENU_DISCOVERY)`, which is cached.
- [ ] T022 [US1] Add the refresh runner to `backend/app/services/recent_raids.py`.

  `async def run_recent_raid_refresh(tenant_id, run_id)`:
  1. Read the own characters with `tenant_scope` and close the session.
  2. Inside `with background_lane():` and `async with asyncio.timeout(settings.recent_raids_refresh_timeout_s):`:
     - run the list step;
     - in a short `tenant_scope`, call `upsert_listed_reports`;
     - run the detail step for the returned codes, in chunks of 10;
     - in a short `tenant_scope`, call `set_report_details` for each, with `final_before = now - 2h`.
  3. In `finally`, a short `tenant_scope` calls `finish_refresh` with an error code:
     - `httpx.HTTPStatusError` 429 → `rate_limited`;
     - other `httpx.HTTPError` → `wcl_unavailable`;
     - `TimeoutError` → `timeout`;
     - anything else → `unknown`, logged with `logger.exception`.

  `async def maybe_start_refresh(session, *, tenant_id, chars, force=False) -> bool`:
  - `claim_refresh(...)` with the settings values;
  - when claimed, `await session.commit()` and re-apply the scope, using `commit_and_rescope` if an identity is available, otherwise `set_scope`;
  - then `background.spawn(run_recent_raid_refresh(tenant_id, run_id), ("recent_raids", tenant_id))` and return `True`.
- [ ] T023 [US1] Create `backend/app/api/recent_raids.py` with a router (`prefix="/api/recent-raids"`) and `GET ""` → `RecentRaidsResponse` (contracts/rest-recent-raids.md):
  - load the own characters with `repo.list_own_characters`;
  - if there are any, call `maybe_start_refresh` (wrap it in `try/except Exception` and log; never fail the request);
  - return `list_recent_raids(limit=settings.recent_raids_limit)` mapped to `RecentRaidOut`, plus `get_refresh` mapped to `RecentRaidsRefreshOut` (`idle` when there is no row).

  Register the router in `backend/app/main.py`, next to `raids.router`.
- [ ] T024 [P] [US1] Add the types `RecentRaid`, `RecentRaidCharacter`, `RecentRaidsRefresh` and `RecentRaidsResponse` to `frontend/src/types.ts`. Add `getRecentRaids()` (GET `/api/recent-raids`) and `refreshRecentRaids()` (POST `/api/recent-raids/refresh`, `{ csrf: true }`) to `frontend/src/api/restClient.ts`, following `getRaids` and `investigateRaid`.
- [ ] T025 [US1] **First**, search the shadcn registry through the shadcn MCP (`search_items_in_registries` for card, item, empty, skeleton, badge, alert) and record which existing `components/ui/*` parts are used. Then create `frontend/src/components/WelcomePanel.tsx`, a memoized component with props `{ onInvestigate(reportCode: string): void; disabled: boolean }`:
  - it fetches `getRecentRaids()` on mount;
  - it renders a responsive grid of raid cards (Card/Item) showing:
    - the zone name (falling back to the title);
    - a local date and time (`toLocaleString`, weekday plus time);
    - a difficulty Badge (1 LFR, 3 Normal, 4 Heroic, 5 Mythic);
    - the character names joined with ", ";
    - "N/M bosses" when `bosses_pulled > 0`;
  - it renders the FR-007 states from the contract's state table: an Empty state with a link to `/profile`; Skeletons on first load; "No recent raids found…"; and an Alert for the failure states (the Retry action comes in T033);
  - **polling (research R6)**: while `refresh.status === "running"`, it re-fetches every 3 s, pauses when `document.visibilityState === "hidden"`, gives up after 3 minutes and clears its timers on unmount;
  - clicking a card calls `onInvestigate(raid.report_code)`;
  - styling uses only the theme tokens from `frontend/src/index.css`, and icons only from `react-icons`.
- [ ] T026 [US1] In `frontend/src/App.tsx`, render `<WelcomePanel onInvestigate={...} disabled={streaming} />` in the no-conversation state (`activeId === null && !messages.some(m => m.role === "user") && !streaming`), between the header and the Composer:
  - keep Barnaby's greeting visible above it (render the greeting message from `messages` first);
  - keep `MessageList` for every other state;
  - for now, wire `onInvestigate` to a no-op `useCallback` (T029 connects it).

  Add the panel styles to `frontend/src/styles.css`, with a mobile-friendly grid, no horizontal scroll and theme tokens.
- [ ] T027 [US1] Run the shadcn MCP audit checklist (`get_audit_checklist`) for the new UI and fix what it flags. Then run `cd frontend && npx tsc -b && npx vite build` and the backend suite.

**Checkpoint**: US1 is fully working. The welcome page lists stored and fresh raids, and every FR-007 state renders.

---

## Phase 4: User Story 2, click a raid to start investigating it (Priority: P1)

**Goal**: a raid card opens a new chat that starts the existing raid investigation, and the raid becomes a tracked raid.

**Independent Test**: click a card. A new chat opens and the bounded overview starts with no typing. The raid then appears in the sidebar's tracked raids (SC-003).

### Tests for User Story 2

- [ ] T028 [P] [US2] In `backend/tests/test_api.py`, add tests:
  - `POST /api/raids/{code}/investigate` for a code that only exists in `recent_raids` returns `201` with the same `kickoff_prompt` as `raids.kickoff_prompt_for(code)`, and `GET /api/raids` now includes it with label `"<guild> — <zone> — <YYYY-MM-DD>"`;
  - an unknown code still returns `404`;
  - another tenant's recent raid returns `404` (FR-017).

### Implementation for User Story 2

- [ ] T029 [US2] In `backend/app/api/raids.py` `investigate_raid`, when `repo.get_tracked_raid` returns `None`:
  1. Call `repo.get_recent_raid(db, report_code, tenant_id=...)`. If that is also `None`, raise the existing 404.
  2. Otherwise build the label with `services.raids._build_label(report_code, {"status": "success", "title": rr.title, "zone": rr.zone_name, "guild": rr.guild_name, "start_time_ms": rr.started_at.timestamp() * 1000})`.
  3. Call `repo.upsert_tracked_raid(db, tenant_id=..., report_code=..., label=..., zone=..., guild=..., report_started_at=rr.started_at, conversation_id=None, encounters=[])`.
  4. Continue as today.

  Run `impact` on `investigate_raid` first.
- [ ] T030 [US2] In `frontend/src/App.tsx`, connect `WelcomePanel.onInvestigate` to `handleInvestigateRaid`. After it resolves, call `void refreshRaids()` so the new tracked raid shows in the sidebar (FR-009). The existing `streamingRef` guard covers clicks during a stream (scenario 2.3). Make sure **New chat** (`newChat`) returns to the welcome state (FR-002); it already sets `activeId=null` and clears the messages.

**Checkpoint**: US1 and US2 together give the "2 clicks to last night's raid" flow.

---

## Phase 5: User Story 3, stored raids and background refresh (Priority: P2)

**Goal**: stored raids are instant and survive restarts. Final reports are never fetched again. Refreshes are gated, retryable and recover after a crash, across instances.

**Independent Test**: load once, restart, and the raids show immediately. A second refresh makes no detail query for final raids. Kill the backend mid-refresh, and a later visit after 5 minutes completes a refresh (quickstart US3).

### Tests for User Story 3

- [ ] T031 [P] [US3] In `backend/tests/test_recent_raids.py`, add tests:
  - **FR-012 / SC-004**: two refreshes with a forced gate (backdate `finished_at`), where the first stores `endTime` older than 2 h. The second refresh issues **0** `reportData` detail queries and exactly 1 `recentReports` query, with `cache=False` passed.
  - A report with `endTime` within 2 h stays `is_final=False` and is fetched again.
  - A responder raising `httpx.ConnectError` records `failed`/`wcl_unavailable` and leaves the stored rows untouched (FR-015, SC-006).
  - A responder that hangs beyond `recent_raids_refresh_timeout_s` (set to 1) records `failed`/`timeout`.
  - Adding an own character makes the next `GET` start a refresh even within 15 minutes (FR-013).
  - `POST /api/recent-raids/refresh`: `202` after a failure; `200` with the current state while running or before the gate opens; `409 no_characters` with no own characters.

### Implementation for User Story 3

- [ ] T032 [US3] In `backend/app/api/recent_raids.py`, add `POST /refresh` (`require_csrf`) per the contract: `maybe_start_refresh(..., force=True)`, returning `202` + `RecentRaidsRefreshOut` when claimed, `200` + the current state when not, and `409 {"detail": "no_characters"}`.
- [ ] T033 [US3] In `frontend/src/components/WelcomePanel.tsx`, add:
  - a **Retry** button in both failure states, which calls `refreshRecentRaids()` and then resumes polling;
  - the subtle "Couldn't refresh" note when raids exist and the status is `failed`;
  - a small Spinner with "checking for new raids…" while running with raids present;
  - "updated N min ago" from `refresh.last_success_at`.

  Map `last_error` to friendly text (`rate_limited` → "Warcraft Logs is busy, try again shortly", and so on). Raw codes are never shown.
- [ ] T034 [P] [US3] Add a "Background refreshes" note to `documentation/deployment.md`, following research R4: Cloud Run throttles CPU after a response, so recommend "CPU always allocated". The stale reclaim (5 minutes) keeps refreshes correct either way.

**Checkpoint**: US1–US3 are complete. The welcome page is production-ready on the async WCL core.

---

## Phase 6: User Story 4, responsive, cancellable Warcraft Logs access (Priority: P2), Phases B and C

**Goal**: every WCL call site is native async (no worker threads), turns cancel their lookups, and background work runs in its lane (FR-018 to FR-024).

**Independent Test**: abandon a tool-heavy turn and its lookups stop within 5 s (SC-007). The loop-lag benchmark stays under 20 ms (SC-008). A 10-character refresh doesn't delay chat lookups (SC-009). Every existing tool returns the same results (FR-023).

**Order matters (research R9)**: callees go first. A sync caller not yet converted calls a converted helper as `threading_utils.run_sync(lambda: helper(...))` until its own task removes that.

### Phase B: async tools

- [ ] T035 [US4] Update `backend/tests/wcl_fakes.py` for the transition. `FakeClient` keeps the sync `query` and gains `async def aquery`, which is exposed through an `AsyncView` whose `query` is async, with both sharing `self.calls`. `install()` monkeypatches `get_client` (the sync view) **and** `get_async_client` (the async view) in every module that binds either: `report_tools`, `tools`, `wcl_client`, `fight_time`, `benchmark`, `cooldowns` and `patch`, using `hasattr` checks. Run the suite.
- [ ] T036 [US4] Convert `wcl_agent/report_tools.py` to async:
  - every tool function, `_report_field` and `run_wcl_graphql` becomes `async def`, using `await get_async_client().query(...)`;
  - names, docstrings, parameters and return shapes stay unchanged (contract §Tool contract).

  Update the callers that are still sync:
  - `wcl_agent/fight_time.py` and `wcl_agent/benchmark.py`: `_report_field(...)` → `run_sync(lambda: _report_field(...))`;
  - `backend/app/services/raids.py`: `await get_report_metadata(code)` directly, replacing `run_in_tool_pool` (interactive lane, because it is inside a chat turn).

  Make `test_report_rankings.py` and the report parts of `test_provenance.py` `async` and `await` the tools. Run `impact` on `_report_field`, then the suite.
- [ ] T037 [US4] Convert `wcl_agent/fight_time.py` (`fetch_dead_windows` and anything else that queries) to async, replacing `gather_threads` with `aio.gather_settled`. It awaits `_report_field` directly. Update its sync callers in `benchmark.py` and `cooldowns.py` to `run_sync(...)`, and update `backend/tests/test_fight_time.py`. Run the suite.
- [ ] T038 [US4] Convert `current_patch()` in `wcl_agent/patch.py` to async. Then:
  - `backend/app/api/ws.py:372` and `backend/app/api/guides.py:45` use `with background_lane(): live_patch = await current_patch()`, removing `run_in_tool_pool` from both;
  - `cooldowns.py` uses `run_sync(...)` until T040;
  - update `backend/tests/test_guide_meta.py`.

  Run the suite.
- [ ] T039 [US4] Convert `wcl_agent/benchmark.py` (`compare_player_to_cohort`, `_fetch_report_context`, `_casts_table` and the internal fan-outs) to async. `gather_threads` becomes `aio.gather_settled`, and the `run_sync` wrappers added in T036 and T037 go away. `cooldowns.py` calls `_casts_table` with `run_sync(...)` until T040. Update `backend/tests/test_benchmark.py` and the `compare_player_to_cohort` test in `test_tool_concurrency.py`. Run the suite.
- [ ] T040 [US4] Convert `wcl_agent/cooldowns.py` (`get_cooldown_usage`, `_fetch_context`) to async and remove every remaining `run_sync` call in it. Update `backend/tests/test_cooldowns.py`. Run the suite.
- [ ] T041 [US4] Convert `wcl_agent/tools.py` (`find_encounter`, `get_rankings_distribution`, `compare_specs`, `_fetch_rankings`, `check_rate_limit`, which uses `acheck_rate_limit`, and the others that query) to async, with `gather_threads` → `gather_settled`. Tools that don't touch WCL (`get_selected_encounter`, `get_spec_options`, `create_chart`) become `async def` too, so `TOOLS` is uniform. Update `test_charts.py`, `test_artifacts.py`, `test_message_report.py` and the tools parts of `test_provenance.py`. Run the suite.
- [ ] T042 [US4] In `backend/app/services/guide.py`:
  - make `_resolve_active_spec_sync` the async `_resolve_active_spec`, awaiting `get_character_zone_rankings`;
  - `resolve_active_spec` wraps it in `with background_lane():` (FR-024) and drops `run_in_tool_pool`.

  Run `impact` on `resolve_active_spec`, then the suite.
- [ ] T043 [US4] In `wcl_agent/agent.py` `build_agent`, register `TOOLS` directly (`tools: list = list(TOOLS)`) and delete the `off_loop` import and the PERF-001 comment. In `wcl_agent/menu.py`, `select_encounter` uses `asyncio.run(get_async_client().query(MENU_DISCOVERY))` (the only sync shim). Smoke-test the CLI with `uv run python main.py`. Run the suite.

### Phase C: remove the threads

- [ ] T044 [US4] Delete `wcl_agent/threading_utils.py`:
  - move `gather_threads` (with `_capture`) into `wcl_agent/models.py` as a private `_gather_threads` for the sync SDK probes;
  - remove `run_sync`, `off_loop`, `run_in_tool_pool`, `_bridge_loop` and the tool pool.

  In `wcl_agent/wcl_client.py`, delete the sync `WCLClient` facade, `get_client()` and the sync `check_rate_limit()`. Then:
  - `grep -rn "threading_utils\|get_client()\|run_in_tool_pool\|off_loop\|gather_threads" wcl_agent backend` must find nothing except `models._gather_threads`;
  - remove `WCL_TOOL_THREADS` from `.env.example`, the README and any config;
  - remove the sync view from `backend/tests/wcl_fakes.py`;
  - update the comments in `backend/app/agent_runner.py:14` and `wcl_agent/cache.py:35` that mention `off_loop` or `run_in_tool_pool`.
- [ ] T045 [US4] Remove the `requests` dependency if nothing imports it any more (`grep -rn "import requests" wcl_agent backend main.py`): `uv remove requests`, and commit `uv.lock`. If a transitive dependency still pulls it in, that's fine; only the direct dependency goes.
- [ ] T046 [US4] Rewrite `backend/tests/test_tool_concurrency.py` for async:
  - every item in `TOOLS` is a coroutine function, and the ADK `FunctionTool(fn)._get_declaration()` keeps `tool_context` out of the schema;
  - `build_agent` registers the tools unwrapped;
  - two tool calls with a slow fake responder run concurrently (wall time ≈ one call);
  - the tenant cache scope (`set_scope_prefix`) propagates through `gather_settled`;
  - **SC-007**: start `get_report_table` through a fake transport that never responds, as an `asyncio.Task`, cancel it after 0.2 s, and assert `_limiter().in_use == 0` within 5 s.

  Delete the `off_loop` and `gather_threads` tests.
- [ ] T047 [P] [US4] Create `backend/tests/test_wcl_loop_lag.py` (`@pytest.mark.perf`, SC-008):
  - a loop-lag probe task records the drift of `await asyncio.sleep(0.005)` over 2 s;
  - meanwhile, 4 concurrent tool fan-outs run through an `httpx.MockTransport` returning a 1.3 MB JSON payload, with the cache cleared first so every call parses;
  - assert the worst-case drift is below 20 ms.

  Run it with `uv run --extra test pytest -q -m perf backend/tests/test_wcl_loop_lag.py`.

**Checkpoint**: there are no WCL worker threads left. SC-007, SC-008 and SC-009 are covered by tests, and the full suite passes.

---

## Phase 7: Polish and cross-cutting concerns

- [ ] T048 [P] Update `README.md`: a feature 013 section (the welcome page and how it refreshes), the new settings from quickstart.md, the removed `WCL_TOOL_THREADS`, and a note that WCL access is now native async with interactive and background lanes.
- [ ] T049 [P] Update `documentation/ai_guide.md` where it describes the threaded WCL tools or `off_loop`, so it matches the async client (constitution governance: runtime guidance stays consistent).
- [ ] T050 Run the quickstart.md manual verification for US1–US4 against `docker compose up --build`, including the two-instance check and the crash and stale-reclaim check. Record the results in a short note at the end of this file.
- [ ] T051 Run `node .gitnexus/run.cjs detect-changes --scope all --repo .`. Re-run it if it reports `partial` or `truncated`. Confirm that only the expected symbols and flows changed, then re-index with `node .gitnexus/run.cjs analyze --index-only`.

---

## Dependencies and execution order

### Phase dependencies

- **Phase 1 (Setup)**: none.
- **Phase 2 (Foundational)**: needs Phase 1. **It blocks every story.**
  - Inside it, T003→T005→T006→T007→T008→T010 run in sequence in `wcl_client`, `threading_utils` and `main`.
  - T009, T011, T013, T014 and T016 can run in parallel.
  - T012→T015→T017 run in sequence.
- **Phase 3 (US1)**: needs Phase 2.
- **Phase 4 (US2)**: needs US1's T023 (recent raids exist) for its backend test data. Its UI task T030 needs T026.
- **Phase 5 (US3)**: needs US1 (the service and panel). It is independent of US2.
- **Phase 6 (US4 B/C)**: needs only Phase 2, so it **can run in parallel with US1–US3**. Its tasks must stay in the order T035→T043, then T044→T047, because each conversion depends on its callees.
- **Phase 7**: after all stories.

### User story dependencies

```text
Setup ─► Foundational ─┬─► US1 ─┬─► US2
                       │        └─► US3
                       └─► US4 (B → C)        (independent of US1–US3)
```

### Parallel opportunities

- Phase 2: T009 (async client tests), T011 (background helper), T013 (models), T014 (types) and T016 (schemas) touch different files.
- US1: T018 (tests), T019 (queries) and T024 (frontend types and client) can start together. T025 (the panel) can be built against T024 while T020–T023 progress.
- US2 and US3 can proceed in parallel after US1.
- US4 Phase B can be done by a second developer alongside US1–US3. Its edits touch only `wcl_agent/*`, four backend call sites and the tests. Coordinate on `backend/app/services/raids.py` (T036) and `backend/app/services/guide.py` (T011 and T042).

### Parallel example: User Story 1

```text
Task T018: "Write service + API tests in backend/tests/test_recent_raids.py"
Task T019: "Add recent_reports_query / report_details_query builders in wcl_agent/queries.py"
Task T024: "Add RecentRaid types + getRecentRaids/refreshRecentRaids in frontend/src/{types,api/restClient}.ts"
```

---

## Implementation strategy

### MVP first (US1 + US2)

1. Phase 1 → Phase 2. The app runs on the async WCL core, and the full suite is green.
2. Phase 3 (US1) → check the welcome page lists raids.
3. Phase 4 (US2) → check one click investigates.
4. **Stop and demo**: this is the user-visible MVP ("2 clicks to last night's raid").

### Incremental delivery

1. Add US3: retry, failure states, crash recovery and deployment notes.
2. Add US4 Phase B, one module per commit, with the suite green after each.
3. Add US4 Phase C: delete the threads and add the cancellation and loop-lag tests.
4. Polish: docs, the quickstart run, detect-changes.

### Commit cadence

Commit after each task or checkpoint. Every commit must leave the suite green (constitution II) and be preceded by `detect-changes`.
