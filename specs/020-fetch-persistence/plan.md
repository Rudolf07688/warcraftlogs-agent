# Implementation Plan: Fetch persistence foundation

**Branch**: `020-fetch-persistence` | **Date**: 2026-10-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/020-fetch-persistence/spec.md`

## Summary

Every successful Warcraft Logs GraphQL response that reaches the API is handed, in
constant time, from the single WCL client to a process-wide **fetch sink**. In the
backend app the sink is a bounded background **writer** that upserts one row per query
key into a new global `raw_fetches` table (migration `0013`). The client's injected
`_cost` field is stripped and the JSON is decoded **inside the database**, so no Python
JSON work happens on the event loop. The writer starts and stops with the FastAPI
lifespan. Everywhere else (CLI, evals, tests that don't opt in) the sink is `None` and
nothing changes. Research: [research.md](research.md). Data model:
[data-model.md](data-model.md). Contracts: [contracts/fetch-sink.md](contracts/fetch-sink.md).

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async (asyncpg on Postgres, aiosqlite in
tests), Alembic, httpx. No new dependency.

**Storage**: PostgreSQL (JSONB, GIN). The tests use SQLite via `metadata.create_all`, like
every existing table.

**Testing**: pytest + pytest-asyncio (auto mode); `wcl_fakes.mock_async_client` for a
real client over `httpx.MockTransport`; the `session_factory` / `patched_db` fixtures for
the SQLite store. Migration up/down/up is a live check on a throwaway Postgres
(quickstart).

**Target Platform**: Linux container (backend), same as today.

**Project Type**: Web service (FastAPI backend plus the standalone `wcl_agent` package).

**Performance Goals**: The hand-off on the fetch path is O(1): one `put_nowait` and one
`len()`. No parse, no serialisation and no awaits.

**Constraints**: The writer holds at most 500 responses and 64 MB of response bytes.
Shutdown drains for at most 5 s. The `wcl_agent` package must not import backend or DB
code (FR-013).

**Scale/Scope**: WCL is rate-limited to a few calls per second, so a sequential
one-row-per-transaction writer has a large margin. The table grows by one row per
distinct query.

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. DRY / reuse | Pass | The query key is the client's existing single-flight key (`_flight_key`, already computed in `query`), passed through rather than recomputed. The operation name reuses `_OP_RE` through one new helper, `operation_name()`, which `_log_cost` uses too. Settings follow the existing `Settings` / `.env.example` pattern. The repository reuses the dialect-insert idea of `repository._insert` (imported, not copied). The finality rule stays `normalize.is_finished` (only documented here, see research R2). |
| II. Step-wise | Pass | Slices: (1) client sink plus helpers, tested; (2) model, migration and repository, tested on SQLite and then on live Postgres; (3) writer plus lifespan wiring, tested; (4) live check. |
| III. Simplicity | Pass | One sink callable, not an event bus. An `asyncio.Queue` with a byte counter. One sequential writer task, one row per transaction. No retention job and no readers. |
| IV. Typed contracts | Pass | `FetchedResponse` is a frozen dataclass at the client/backend boundary. Settings are typed pydantic fields. |
| V. Async backend | Pass | DB writes use the async session. JSON decoding happens in Postgres (`CAST(... AS jsonb) #- '{data,_cost}'`), so nothing heavy runs on the loop. |
| VI. GitNexus | Pass | Impact was run on the worktree index. See "Impact" below. HIGH/CRITICAL results were reported to the scrum master before any edit. |
| VII. shadcn | N/A | No UI. |
| VIII. Backlog | Pass | sc-127 is In Progress; sc-128 moves to In Progress when its slice starts. |

### Impact (GitNexus, worktree index at 823e0ff)

| Symbol | Risk | Note |
|---|---|---|
| `AsyncWCLClient._fetch` | HIGH | This is the single chokepoint for every WCL call (datasheet, benchmark, recent raids…), so HIGH is inherent. The change is a trailing O(1) `_offer(...)` call after the success checks, plus a new `key` parameter. No test calls `_fetch` directly (text search). |
| `AsyncWCLClient.query` | CRITICAL | Only change: pass the already computed `key` to `_fetch`. The return value and behaviour are unchanged. |
| `_log_cost` | HIGH | Only change: use `operation_name(query)` instead of the inline `_OP_RE.match`. The log line is identical. |
| `Settings` | CRITICAL (48) | Additive: three new fields with defaults. |
| `lifespan` | UNKNOWN | Called by FastAPI (`FastAPI(lifespan=lifespan)`, text search: the only reference). No test runs the real lifespan (`test_startup` uses its own app). |

## Design

### 1. Client sink (`wcl_agent/client/wcl_client.py`)

- `@dataclass(frozen=True) class FetchedResponse`: `query_key: str`, `query: str`,
  `variables: dict[str, Any]` (a shallow copy), `content: bytes` (raw response body,
  `_cost` still inside), `fetched_at: datetime` (UTC).
- `FetchSink = Callable[[FetchedResponse], None]`, a module global `_fetch_sink`, and
  `set_fetch_sink(sink: FetchSink | None)`. The sink is process-wide, like `_tokens`.
- `AsyncWCLClient.query` passes its `key` to `_fetch`. `_fetch(query, variables, key)`
  calls `_offer(...)` right before `return content`. That point is after
  `raise_for_status` and the GraphQL `errors` check, so failures are never offered
  (FR-004). Single-flight waiters share one `_fetch` task, so a call is offered once
  (FR-003, US1-4).
- `_offer` returns immediately when no sink is set. Otherwise it calls the sink inside
  `try/except Exception` and logs at debug level: a broken sink can never fail a fetch
  (FR-007).
- Pure helpers, used by the backend off the fetch path:
  - `operation_name(query) -> str | None`, which reuses `_OP_RE`.
  - `report_codes(query, variables) -> list[str]`: every `report(code: $var)` or
    `report(code: "LIT")` argument in order, deduplicated and stripped, with variable
    values resolved from `variables` (FR-015).

### 2. Table (`backend/app/db/models.py`, migration `0013_raw_fetches`)

See [data-model.md](data-model.md). The primary key is `query_key` (64-char sha256 hex).
Columns: `operation_name` (nullable), `params` JSONB, `report_code` (nullable, btree
index), `report_codes` JSONB array (NOT NULL, default `[]`, GIN index), `fetched_at`
timestamptz, `payload` JSONB. No RLS. The runtime role gets DML (same as `0007`/`0011`).
`down_revision = "0012_conversation_pin_title"`.

### 3. Repository (`backend/app/repositories/raw_fetches.py`)

`async def upsert_raw_fetch(session, fetched: FetchedResponse) -> None`. It does a
dialect `INSERT … ON CONFLICT (query_key) DO UPDATE SET payload, fetched_at, params,
operation_name, report_code, report_codes … WHERE raw_fetches.fetched_at <
excluded.fetched_at`. The latest fetch wins, and an older write that loses a race
between processes never overwrites a newer one (spec edge case).

The payload is bound as **text** and turned into JSON by the database:

- Postgres: `CAST(:payload AS jsonb) #- '{data,_cost}'`
- SQLite: `json_remove(:payload, '$.data._cost')`

So the caller-visible response is stored (FR-009) with no Python `json.loads`/`dumps` of
the body. `content.decode()` is the only Python work on the body. It is a memcpy-speed
UTF-8 decode, and it runs in the writer task, not on the fetch path.

### 4. Writer (`backend/app/services/fetch_persistence.py`)

| Concern | Decision |
|---|---|
| Owner | One `FetchWriter` per app process, created in `lifespan` and kept on `app.state.fetch_writer`. Its single `asyncio.Task` runs on the app's loop. |
| Hand-off | `offer(fetched)` is registered as the client sink. If it is called on the writer's loop thread, it runs `_enqueue` directly; from any other thread it goes through `loop.call_soon_threadsafe`, because the client supports several loops while the sink is process-wide. `_enqueue` checks both bounds and calls `put_nowait`. It never awaits. |
| Bounds | `asyncio.Queue(maxsize=WCL_FETCH_PERSIST_QUEUE_MAX)` (500) plus a running total of `len(content)` capped at `WCL_FETCH_PERSIST_QUEUE_MB` (64 MB). A response bigger than the whole byte cap is dropped. |
| Overflow | Drop the **new** response, increment `dropped`, and log one warning per 60 s with the count since the last warning (`_Throttle`). |
| Write | Sequential: `get()`, then `store(fetched)` inside `asyncio.timeout(10)`, then `task_done()`. The default `store` opens `db_session.SessionLocal()` (looked up through the module, so `patched_db` repoints it in tests), calls `upsert_raw_fetch` and commits. One row per transaction. |
| Errors | Any exception from `store` is caught and counted. It's logged with the same 60 s throttle (first one at once, with the exception text). The loop carries on with the next item (FR-007). A DB that hangs costs at most 10 s per item; the queue fills and further responses are dropped, never blocked. |
| Shutdown | `stop(grace_s=5)`: unregister the sink first (`set_fetch_sink(None)`, so nothing new arrives), then `asyncio.wait_for(queue.join(), 5)`. On timeout, count `qsize()` (plus the in-flight item) as dropped and log it. Finally cancel the task and await it. Called in `lifespan` **before** `aclose_clients()` and `engine.dispose()` (FR-011). |
| Disabled | With `WCL_FETCH_PERSIST_ENABLED=false`, lifespan creates no writer and the sink stays `None`. |
| No lifespan | CLI, evals and tests: nobody calls `set_fetch_sink`, so `_offer` is a single `is None` check (FR-010). Tests that need persistence start a `FetchWriter` themselves with a fake or SQLite store. |

### 5. Lifespan wiring (`backend/app/main.py`)

The writer starts before `_boot` is created, because the boot's roster step fetches from
WCL. `stop()` runs after the boot task is cancelled and before
`aclose_clients()`/`engine.dispose()`.

### 6. Settings (`backend/app/config.py`, `.env.example`)

`wcl_fetch_persist_enabled: bool = True`, `wcl_fetch_persist_queue_max: int = 500`,
`wcl_fetch_persist_queue_mb: int = 64`, each documented in `.env.example` next to the
WCL cache block.

## Project Structure

### Documentation (this feature)

```text
specs/020-fetch-persistence/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/fetch-sink.md
├── checklists/requirements.md
└── tasks.md            (/speckit-tasks)
```

### Source Code (files this feature creates or modifies)

```text
wcl_agent/client/wcl_client.py                 # modify: FetchedResponse, sink, _offer, helpers, key → _fetch
backend/app/db/models.py                       # modify: append RawFetch at end of file
backend/migrations/versions/0013_raw_fetches.py  # new
backend/app/repositories/raw_fetches.py        # new: upsert_raw_fetch
backend/app/services/fetch_persistence.py      # new: FetchWriter, default store
backend/app/config.py                          # modify: 3 settings
backend/app/main.py                            # modify: lifespan start/stop
.env.example                                   # modify: 3 documented settings
backend/tests/test_raw_fetch_client.py         # new: sink offers, helpers
backend/tests/test_raw_fetch_store.py          # new: model + upsert on SQLite
backend/tests/test_raw_fetch_writer.py         # new: write-through, DB down, full queue, shutdown
```

`wcl_agent/cache/**` is not touched: the cache sits above the client, so a cache hit
never reaches `_fetch` (FR-003). The tentative grant can be released.

**Structure Decision**: The existing layout. The client-side hook lives in
`wcl_agent/client/` (it stays DB-free), and the persistence lives in the backend
(`repositories/` for the SQL, `services/` for the background writer).

## Complexity Tracking

| Addition | Why needed | Simpler alternative rejected because |
|---|---|---|
| A separate `report_codes` JSONB column plus GIN index, besides `report_code` | PO condition (decision 17): batch rows must be findable by report code without parsing GraphQL. | Putting the key inside `params` would make `params` no longer the exact variables sent, which sc-129 needs to match or replay a query, and it could collide with a real variable name. The GIN index is cheap: arrays hold 0 to 10 short codes. |
| A dialect-specific payload expression (`CAST … #-` vs `json_remove`) | Keeps all JSON decoding of multi-MB bodies off the event loop (constitution V). | Parsing in a thread still leaves SQLAlchemy's JSON bind (`json.dumps`) on the loop. |
| `call_soon_threadsafe` path in `offer` | The sink is process-wide, but the client supports several loops/threads. | Without it, a fetch on another thread would touch an `asyncio.Queue` that isn't thread-safe. |
