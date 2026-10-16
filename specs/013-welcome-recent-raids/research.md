# Research: Welcome Page with My Recent Raids

**Feature**: 013-welcome-recent-raids | **Date**: 2026-10-16

All the "NEEDS CLARIFICATION" items in the plan's Technical Context are resolved below. Each entry gives the decision, why it was made, and what else was considered.

---

## R1. Where the recent raids come from

**Decision**: Use `characterData.character(name, serverSlug, serverRegion).recentReports(limit: 20)`. One GraphQL request fetches every own character at once, one alias each (`c0` … `c9`). Each report returns only list fields: `code`, `title`, `startTime`, `endTime` and `zone { id name }`.

**Rationale**:
- On 2026-10-16 the live schema was introspected with the app's credentials. `Character.recentReports(limit: Int = 10, page: Int = 1): ReportPagination` exists, and `Report` has `code`, `title`, `startTime`, `endTime`, `zone`, `fights(killType, difficulty, …)` and `visibility`.
- One aliased request costs one network round trip, whether the user has 1 character or 10.
- `limit: 20` per character means that even a user with one character can fill the 20-raid list (FR-004).
- `ReportPagination` itself could not be introspected because WCL returned an internal error. It is assumed to use the standard Laravel pagination shape (`data`, `has_more_pages`). The first implementation task confirms this with one live call.

**Alternatives considered**:
- `reportData.reports(guildID | userID, …)` can only filter by guild or uploader. Raids the user attended as a pug or under someone else's upload would be missed.
- Ranking queries per character: `zoneRankings` only covers ranked boss kills. It misses wipe nights and gives no report list.

## R2. Fetching details once, and filtering to raids

**Decision**: Fetch in two steps.

1. **List step**, once per refresh: the R1 query. **It always bypasses the WCL cache.** The cache rule `is_report_scoped` doesn't match `recentReports`, so the query would get the 1-hour leaderboard TTL, which is longer than the 15-minute refresh. The async client gets a `cache=False` option for this.
2. **Detail step**, only for codes that are new or not yet final: one aliased `reportData` request. Each code (`r0` … `rN`) asks for `endTime` and `fights(killType: Encounters) { encounterID kill difficulty size }`. This query is report-scoped, so the cache treats it as immutable as usual.

From the details the system works out:
- `bosses_pulled`: the number of distinct `encounterID`s;
- `bosses_killed`: the number of distinct `encounterID`s with `kill = true`;
- `difficulty`: the highest raid difficulty among the boss fights.

**Is it a raid?** A report counts as a raid when its zone offers raid difficulties. This reuses the zone data `MENU_DISCOVERY` already provides (the same source as `patch.py`'s `_offers_heroic`). Mythic+ dungeon zones don't offer heroic. Non-raid reports are **stored** with `is_raid = false`, so they are never fetched again, but they are left out of the welcome list. A raid-zone report with only trash fights is still a raid, with `bosses_pulled = 0`.

**Is it final?** A report is final when `endTime` is more than 2 hours in the past. Live logs keep moving `endTime` forward. A report that isn't final is fetched again on the next refresh, and a final one never is (FR-012, SC-004).

**Rationale**: This meets FR-012 exactly, and the zone check needs no extra request because `MENU_DISCOVERY` is already cached for the process.

**Alternatives considered**:
- Fetching `fights` inside the list query: it would re-pull fights for all 20 × N reports on every refresh, which breaks FR-012.
- Filtering by fight `size ≥ 10`: it needs the detail step first and gets trash-only raid nights wrong.

## R3. Who owns stored raids: the tenant, or the whole app?

**Decision**: Stored raids are **per tenant**, under row-level security, like `tracked_raids` and `known_players`.

**Rationale**: FR-017 requires privacy. Every tenant table already uses the RLS predicate, so a per-tenant table needs no new policy shape.

**Alternatives considered**: A shared, immutable report-details table would save fetches when guildmates share a raid. It was rejected for now (Simplicity, Principle III): it needs a second, non-RLS table and a join. SC-004 is "at most once per user", so it is met either way. This can be revisited if WCL point usage becomes a problem.

## R4. Coordinating refreshes across instances (clarification Q2)

**Decision**: There is one `recent_raid_refresh` row per tenant, and that row is the lock. To claim a refresh:

```sql
INSERT INTO recent_raid_refresh (tenant_id) VALUES (:t) ON CONFLICT DO NOTHING;
UPDATE recent_raid_refresh
   SET status = 'running', run_id = :new_run, started_at = now()
 WHERE tenant_id = :t
   AND (status <> 'running' OR started_at < now() - interval '5 minutes')      -- FR-026 stale reclaim
   AND (:force OR finished_at IS NULL
        OR finished_at < now() - interval '15 minutes'                          -- FR-013 gate
        OR character_set <> :current_set)                                       -- new own character
RETURNING run_id;
```

- If a row comes back, the caller has won the claim and starts the refresh task.
- The task records its outcome with `UPDATE … WHERE run_id = :mine`. A run that was reclaimed after going stale therefore can't overwrite the newer run.
- `:force` is only allowed when the last outcome was `failed`. That is the Retry case (FR-015). Even a forced claim can't take over a run that is still live and not stale.

**Rationale**:
- This is the design the QA report suggests (PERF-208 and PERF-210, report §013). It costs one statement, works the same on one instance or many, needs no new infrastructure and recovers by itself after crashes.
- `UPDATE … RETURNING` works on both Postgres and SQLite 3.35+, which is the test database.
- `character_set` holds a stable hash of the sorted own-character identities, so adding a character starts a refresh straight away (FR-013, scenario 3.5).

**Alternatives considered**:
- An in-memory set: this is how guides work today, and it breaks on restart and with several instances.
- `pg_advisory_lock`: it is held per connection and released if that connection drops. It doesn't record outcomes and doesn't exist on SQLite.
- Cloud Tasks or a scheduler: this was Option C, rejected in the clarification.

**Cloud Run note**: by default Cloud Run throttles CPU once a request has finished. An in-process refresh started by `GET /api/recent-raids` may then run slowly, but it doesn't break: the stale reclaim (FR-026) and the client's polling still produce a correct result. The deployment doc gets a note recommending "CPU always allocated". Choosing a deployment setup is out of scope.

## R5. Running the refresh in the background

**Decision**:
- `GET /api/recent-raids` returns the stored raids and the refresh state immediately.
- If the claim succeeds, the handler first commits the claim. It then schedules `run_recent_raid_refresh(tenant_id, run_id)` through a shared background-task helper and holds no database transaction while it does.
- The task body runs inside `background_lane()` (R7) and under `asyncio.timeout(120)`. It uses short tenant-scoped transactions (`tenant_scope`) only for reading characters and writing results, never around WCL calls.
- A `try/finally` always records `succeeded` or `failed` (FR-026).

**DRY**: `guide.py`'s `_spawn` (which holds GC-safe task references and removes duplicate keys) moves to `backend/app/services/background.py` as `spawn(coro, key)`. Both guides and recent raids use it. Duplicate keys are still removed in memory, as a cheap first filter. The database claim (R4) is the real lock.

**Rationale**: This follows the existing guide pattern, with the durability it was missing added (PERF-208). It needs no job queue (Principle III).

## R6. How the welcome page learns about new raids

**Decision**: Polling.
- While `refresh.status == "running"`, the welcome page calls `GET /api/recent-raids` every 3 s.
- It stops when the status leaves `running`, when the page is hidden (`document.visibilityState`), or after 3 minutes.
- Because the server reclaims runs older than 5 minutes, a stuck `running` state ends by itself.

**Rationale**: It meets FR-014 with no new transport. The QA report notes that a WebSocket push would first need the full-duplex socket (PERF-202), which is out of scope.

**Alternatives considered**: Server-Sent Events or pushing over the existing chat WebSocket. Both are more work for no user-visible gain at a 3 s cadence.

## R7. The async WCL client (PERF-201)

**Decision**: Replace `requests` and threads with one `AsyncWCLClient` built on a shared `httpx.AsyncClient`. httpx is already a dependency (`pyproject.toml`), so nothing new is added.

| Concern | Today | New |
|---|---|---|
| HTTP | `requests.Session` in the tool thread | `httpx.AsyncClient` (`Timeout(connect=5, read=60)`, `Limits(max_connections=16)`), one per event loop, closed in the lifespan |
| Concurrency cap | `threading.BoundedSemaphore(6)` | `LaneLimiter` (R8), per event loop |
| Single-flight | `threading.Event` with a 90 s wait | A dict mapping each key to a **shared `asyncio.Task`** plus a waiter count. Callers `await asyncio.shield(task)`. A caller that is cancelled decrements the count, and the task is cancelled only when no callers are left (FR-019 and the edge case "a cancelled lookup was shared") |
| Timeout | read timeout only | Also `asyncio.timeout(75)` around each fetch. The task is cancelled and its slot freed (FR-021) |
| Cache | parsed objects, `deepcopy` on every get and set | **Raw response bytes**, parsed with `json.loads` on each hit. Nothing mutable is shared (FR-022), the deepcopy goes away and PERF-105 is closed. Parsing costs about 9 ms/MB on the loop (measured by QA). Payloads over 2 MB are parsed with `asyncio.to_thread(json.loads, …)` |
| Auth | `threading.Lock` | `asyncio.Lock`, per client |
| Tenant cache scope | `ContextVar`, copied into threads | The same `ContextVar`, which now propagates naturally |

The tools become `async def`. Google ADK supports coroutine function tools directly: it awaits them, runs parallel calls concurrently and cancels them with the turn. So `off_loop`, `run_in_tool_pool` and the 32-thread pool are deleted. `gather_threads` is replaced for WCL fan-out by `gather_settled(*aws)`, which is `asyncio.gather(..., return_exceptions=True)` and keeps today's "exception in its slot" behaviour. If the parent is cancelled, the gather cancels its children.

**Sync callers that remain**:
- `menu.select_encounter()` (the CLI's start-up prompt, which runs before `asyncio.run`) uses `asyncio.run(client.query(...))`. This is the only sync shim.
- `models.py` probes model providers with sync SDK clients, not WCL, so it is out of scope (FR-018 is WCL-only). It keeps a local thread-gather helper, which moves into `models.py` so that `threading_utils.py` can be deleted.

**Rationale**: This is QA PERF-201's suggested fix. It brings real cancellation, removes GIL contention (QA measured 35 ms average and 157 ms worst-case loop lag) and makes the WCL calls awaitable, so lanes and timeouts can be built on them.

**Alternatives considered**:
- `aiohttp`: it would be a new dependency, and httpx is already installed.
- Keeping the threads but adding cancel flags: it doesn't fix GIL contention, and `requests` has no clean way to cancel a request.

## R8. Lanes (PERF-211)

**Decision**: A small `LaneLimiter` with `total = WCL_MAX_CONCURRENCY` (6) and `background_cap = WCL_BACKGROUND_CONCURRENCY` (2):
- **interactive**: takes a slot whenever `in_use < total`.
- **background**: takes a slot only when `in_use < total`, `bg_in_use < background_cap` **and** no interactive caller is waiting. Background work therefore gives way to queued chat work (FR-020).
- It is built on one `asyncio.Condition`. Releasing a slot calls `notify_all`, and waiters check their own condition again.

The lane is stored in a `ContextVar` (`wcl_lane`, default `"interactive"`) and set by the `background_lane()` context manager. Guide spec resolution, `current_patch` and the recent-raid refresh all run inside `background_lane()` (FR-024). Chat tools need no change because they use the default lane.

**Per-turn cap (PERF-106)**: out of scope. The spec names only lanes, and adding it here would grow the side mission.

**Rationale**: About 40 lines with no dependency, and every rule in FR-020 is directly testable (SC-009).

**Alternatives considered**:
- Two separate semaphores (6 and 2): background work could still take interactive slots while chat is queued.
- `asyncio.PriorityQueue` dispatch: it needs a dispatcher task, which is more machinery for the same behaviour.

## R9. Migrating in phases without two clients

**Decision**: Three phases. Each one ships with the app fully working (Principle II).

1. **Phase A, the async core.** Add `AsyncWCLClient` and `LaneLimiter`, and switch the cache to bytes. The sync `WCLClient.query` becomes a **bridge**: it captures the running loop when `off_loop` / `run_in_tool_pool` dispatches the call (stored in a ContextVar copied into the thread) and runs the async query there with `asyncio.run_coroutine_threadsafe(...).result()`. Everything immediately shares one client, one cache, one cap and the lanes. Cancellation doesn't work yet, because threaded callers can't be cancelled.
2. **Phase B, async tools.** Convert the tool modules to `async def`, one module per step, callees first: `report_tools` → `fight_time` → `patch` → `benchmark` → `cooldowns` → `tools` (`fight_time`/`benchmark` call `report_tools._report_field`; `cooldowns` calls `benchmark`, `fight_time` and `patch`). Until a caller's own step, an unconverted sync caller runs a converted helper with `threading_utils.run_sync(...)`, which goes through the captured loop like the query bridge. Each converted module is registered with ADK directly instead of through `off_loop`. The backend callers (`ws.py`, `guides.py`, `services/raids.py`, `services/guide.py`) await directly.
3. **Phase C, cleanup.** Delete the bridge, `off_loop`, `run_in_tool_pool`, the tool pool and `gather_threads`, plus `threading_utils.py`, and the `WCL_TOOL_THREADS` setting. Update `test_tool_concurrency.py` into an async concurrency and cancellation test.

The welcome page's own WCL calls (R1, R2) are written against `AsyncWCLClient` from the start (spec assumption).

**Rationale**: The bridge is a short-lived adapter that lets Phase A ship lanes and the bytes cache before any tool changes. Without it there would be one large change touching six modules at once.

## R10. Starting an investigation from the welcome page

**Decision**: Extend the existing `POST /api/raids/{report_code}/investigate`. When no tracked raid exists for the code but a stored **recent raid** does, the handler first adds the tracked raid using the recent raid's fields: the label is built by the existing `_build_label`, plus zone, guild and `report_started_at`. It then continues exactly as today. The frontend reuses `investigateRaid()` and then refreshes the sidebar's raid list.

**Rationale**:
- FR-008 and FR-009 require the same kickoff and that the raid becomes a tracked raid. One endpoint and one kickoff source stay true to DRY (Principle I).
- A 404 for codes that are neither tracked nor recent stays as it is, so no arbitrary report codes can be injected.

**Alternatives considered**: A separate `/api/recent-raids/{code}/investigate` would duplicate the conversation-creation and kickoff logic.

## R11. Where the welcome page lives

**Decision**: The welcome page **is the no-conversation state** (`activeId === null` with no user message). It renders a `WelcomePanel` above the existing Composer and in place of the empty message list. Barnaby's greeting stays above the raid list:
- **New chat** in the sidebar returns the user to it (FR-002).
- Sending a message from the Composer starts an ordinary chat (FR-003).
- On first load the app is already in this state (FR-001).

**Rationale**: It needs no new route and no change to navigation, and it reuses the existing new-chat and greeting flow. The spec assumption ("inside the existing app layout, with the sidebar still visible") is met.

**UI parts (Principle VII)**: Card, Item, Badge, Skeleton, Empty, Button and Alert are all already in `components/ui/`. The shadcn MCP search during implementation confirms nothing better fits. Nothing is expected to be hand-built.

## R12. Measuring the success criteria

- **SC-007, cancellation**: a test starts an async tool whose fake transport never responds, cancels the turn's task and asserts that the in-flight count returns to 0 within 5 s.
- **SC-008, loop lag**: an extended version of QA's micro-benchmark. It runs a loop-lag probe (`asyncio.sleep(0.005)` drift) while 4 concurrent fake-transport tool fan-outs return 1.3 MB payloads, and asserts a worst case under 20 ms. It goes in the backend test suite, marked `perf`.
- **SC-009, lanes**: a `LaneLimiter` unit test. With background holding its 2 slots and a further background waiter queued, an interactive acquire succeeds immediately. While interactive waiters are queued, background acquires are blocked.
- **SC-010, two instances**: a test with two independent DB sessions calling `claim_refresh` at the same time. Exactly one gets a `run_id`. A row in `running` state backdated by 6 minutes can be claimed again.
