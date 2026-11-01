# Implementation Plan: Local data reads

**Branch**: `045-local-data-reads` | **Date**: 2026-11-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/045-local-data-reads/spec.md`

## Summary

Make the 039 DB-first read cheap and fail-fast (sc-295), close the revocation-lag and gone-vs-write
races (sc-296), count probe outcomes and locally answered turns in the existing cache stats
(sc-132), and give the agent three exact lookup tools over the stored data (sc-131). Approach:
one SQL visibility clause (`fetch_visible_clause`) shared by every reader; the probe moves into the
WCL client's single-flight and lane slot, keyed by workspace; a process-wide breaker; DB and Redis
tombstones ordered by request start; per-load and per-turn holders carried in context variables.
No migration, no new dependency.

## Technical Context

**Language/Version**: Python 3.12 (backend + `wcl_agent`)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async (asyncpg / aiosqlite), redis.asyncio, Google ADK (tools)

**Storage**: Postgres 17 (pgvector image) / SQLite in tests; Redis (fakeredis in tests)

**Testing**: pytest (`env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q`), Postgres-only tests on `wcl-045-pg:15445`

**Target Platform**: Linux container (compose)

**Project Type**: web service + agent package

**Performance Goals**: probe miss ≤ 2 SQL statements, hit ≤ 4; stall cost ≤ one probe timeout per 30 s

**Constraints**: the 039 guard (only `raw_fetches.py` reads `raw_fetches`) and its tests stay unchanged; `wcl_agent` stays DB-free; `ws.py` untouched

**Scale/Scope**: 4 stories, 10 pts, ~7 source files + tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I Reuse-first | Reuses `read_visible_fetch`, `get_or_load` metrics/flush, `summarize`/`read_stats`, `set_refresh_actor` turn hook, `ToolGroup`, report query builder, the resolver. One visibility definition (`fetch_visible_clause`) replaces the Python loop. | PASS |
| II Small verified steps | Story order sc-295 → sc-296 → sc-132 → sc-131; each FR lands with its test; Stop 2 after sc-295+sc-296. | PASS |
| III Simplicity | No migration (tombstone reuses `raw_reports`), no new table, no Lua (write-then-check ordering), breaker is a module dataclass, no per-key probe cache. | PASS |
| IV Typed boundaries | `StoredFetch` dataclass (client↔source), `BatchResult` (writer↔043 hook), `StoreStats`/`LocalAnswerStats` Pydantic models in `CacheStats`, typed tool results. | PASS |
| V Async backend | All DB/Redis calls async; big payload stays bytes (no loop decode); no blocking calls added. | PASS |
| VI GitNexus | Impact run on all risky symbols (below); detect-changes before each commit. | PASS |
| VII shadcn | No UI. | N/A |
| VIII Backlog sync | Stories moved to In Progress; Under Review at hand-off. | PASS |

### GitNexus impact (upstream, worktree index)

| Symbol | Risk | Real callers (text-search confirmed) | Mitigation |
|---|---|---|---|
| `read_visible_fetch` | CRITICAL (5 flows, all via the probe) | `read_stored_fetch` only (+ sc-131 tools later, 044 joins the clause) | Same signature and result semantics; 039 visibility tests unchanged; new statement-count tests; PG run on 15445 |
| `read_stored_fetch` | HIGH | client `_stored` ← `query` (all WCL calls); `main.py` installs it | Becomes a source object with the same call shape; fail-open kept; breaker tests per transition |
| `AsyncWCLClient._fetch` / `query` | HIGH / UNKNOWN (dynamic) | every WCL tool (report_tools, roster, menu, benchmark, cooldowns, recent_raids, guide pipeline, evals) | Network path unchanged when no source is installed (CLI, evals, tests); flight key unchanged without a source; existing client tests stay green |
| `_offer` / `FetchedResponse` | HIGH (file-level noise) | `_fetch` only constructs it; writer + repository consume | New field `requested_at` has a default; nothing else constructs it |
| writer `_store_one` / `store_batch` / `upsert_raw_fetch` / `grant_codes` / `delete_report` | LOW / UNKNOWN | `FetchWriter` only | Writer tests (order, batch fallback, gone) stay green; `store_batch` result becomes `BatchResult` (contract 5) |
| `get_or_load` / `_load_and_store` / `get_many_or_load` | UNKNOWN (dynamic) | 10 files (report tools, roster, menu, participants, guide pipeline, main, recent_raids) | Holder only skips writes when flagged; default path byte-identical; cache family tests stay green |
| `evict_report` | UNKNOWN | writer `_evict` only | Adds one SET before the SCAN |
| `set_refresh_actor` | UNKNOWN | `ws.py` turn start/end, report_tools reads the actor | Actor behaviour unchanged (`test_refresh_actor_reset`); turn holder added beside it |
| `read_stats` / `CacheStats` | UNKNOWN / HIGH (import noise) | `/api/admin/cache-stats` only | Additive fields with defaults |

## Design

### sc-295 probe (research R1-R4)

```
query(q, v) ─ flight key = (q, v) + source.scope()   # scope only when a source is installed
   └─ _fetch (shared by same-workspace callers)
        ├─ lane slot ─ probe (breaker → timeout 400 ms → read)   # holds ≤ 6 connections per loop
        │     hit → return StoredFetch (no cost log, no sink)
        ├─ 429 block check
        └─ network (unchanged)
```

Probe statements (`read_visible_fetch`):

1. `SELECT report_codes, fetched_at FROM raw_fetches WHERE query_key = :k` — none → miss (1 stmt).
2. `SELECT code, visibility, end_time_ms, checked_at FROM raw_reports WHERE code IN (...)` — freshness in Python; stale → miss (2 stmts).
3. `SELECT set_config('app.tenant_id', :t, true)` — only with a tenant and a code not public-confirmed.
4. `SELECT <clause(tenant)> AS visible, <clause(None)> AS shared, CASE WHEN <clause(tenant)> THEN <payload as bytes> END FROM raw_fetches WHERE query_key = :k AND fetched_at = :f` — visible false → not_visible; no row → miss (row changed).

Breaker (process-wide, `raw_fetch_reads.py`):

```
        timeout / connection error
CLOSED ───────────────────────────────► OPEN(until = now + 30 s)
  ▲                                         │ now ≥ until
  │ trial succeeds (hit/miss/not_visible)   ▼
  └──────────────────────────────────── HALF_OPEN ── trial in flight: other callers skip
                                            │ trial times out / connection error → OPEN
                                            │ trial cancelled or other error → HALF_OPEN (slot freed)
```

Writer: scope set once per tenant per transaction (`_scope_tenant`, one statement, remembered in
`store_batch`); grant upsert `WHERE granted_at < :at - 1 h`; `upsert_raw_fetch` returns whether the
payload changed (`RETURNING`), `store_batch` returns `BatchResult(gone, changed)` (contract 5).

### sc-296 races (research R5-R7)

- **Back-fill**: the source returns `StoredFetch(content, shared)`; `query()` (in each waiter's own
  context) calls `cache.mark_unshareable()` when `shared` is false. `get_or_load` /
  `get_many_or_load` open a per-load holder (ContextVar to a mutable object, so the loader's sub-tasks
  share it) and skip the Redis SET and memo when it is marked.
- **Race 1**: `delete_report` keeps a `raw_reports` tombstone (`visibility='gone'`, `checked_at =
  seen_at`). `FetchedResponse.requested_at` = request start. `_store_one` skips the whole item (row,
  status, grant) when any of its stored codes has a tombstone with `checked_at >= requested_at`.
  A later fetch requested after the tombstone writes normally; a newer summary status replaces it.
- **Race 2**: `evict_report` SETs `wcl:v1:gone:<code>` (TTL `lock_ms`) before the SCAN. After a
  report-family SET (`wcl:v1:report:<code>:…`), the writer checks `EXISTS` and DELs its own key.
  Either the SET precedes the SCAN (scan deletes it) or follows the tombstone (check deletes it).

### sc-132 counters (research R8)

One hash `wcl:metrics:v1:local:<day>`: `store_hit`, `store_miss`, `store_not_visible`,
`store_timeout`, `turns`, `local_turns`, via the existing `_counts`/flush. `set_refresh_actor(uid)`
opens a turn holder; `set_refresh_actor(None)` counts the turn (local when unmarked) and clears it.
`query()` marks the holder on any network call (also on failure). `read_stats` adds `store` and
`local_answers`.

### sc-131 tools (research R9)

`backend/app/agent_tools/stored_data_tools.py`, a `ToolGroup("Stored data", …)`:
- `list_stored_fights(report_code)` → key of `REPORT_SUMMARY {"code"}` → `read_visible_fetch` (probe
  freshness) → fights (id, encounter, difficulty, kill, start, size), ≤ 100.
- `get_stored_fight_table(report_code, data_type, fight_id=0, source_id=0, ability_id=0,
  hostility_type="Friendlies")` → the exact query the table tool sends (shared builder) →
  `read_visible_fetch` → `table` through `_acap`.
- `list_stored_reports_for_character(name, realm, region)` → resolver → `list_visible_summaries`
  (new in `raw_fetches.py`: ReportSummary rows filtered by `fetch_visible_clause`, newest first,
  scan ≤ 200) → roster match on the normalised name → ≤ 25 reports.
- Every miss, invisible or stale row → `{"status": "not_stored", "hint": "use the WCL report tools"}`.

## Project Structure

### Documentation (this feature)

```text
specs/045-local-data-reads/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/  (visibility-clause.md, fetch-source.md, cache-stats.md, stored-data-tools.md)
├── checklists/requirements.md
└── tasks.md
```

### Source Code — exact files per story (the grant list for the gate)

| Story | Files (edit) | Tests |
|---|---|---|
| sc-295 | `backend/app/repositories/raw_fetches.py`, `backend/app/services/raw_fetch_reads.py`, `backend/app/services/fetch_persistence.py`, `backend/app/config.py`, `wcl_agent/client/wcl_client.py`, `wcl_agent/cache/cache.py` (probe counter recording only) | `backend/tests/test_raw_store_reads.py`, `test_raw_fetch_client.py`, `test_raw_fetch_writer.py`, `test_raw_store_pg.py`, new `test_raw_store_probe.py` |
| sc-296 | `wcl_agent/cache/cache.py`, `wcl_agent/client/wcl_client.py`, `backend/app/repositories/raw_fetches.py`, `backend/app/services/fetch_persistence.py`, `backend/app/services/raw_fetch_reads.py` | new `backend/tests/test_raw_store_races.py`, `test_raw_fetch_writer.py`, `test_cache_families.py` |
| sc-132 | `wcl_agent/cache/cache.py`, `wcl_agent/client/wcl_client.py`, `backend/app/schemas.py` (`CacheStats` + 2 new models only), `backend/app/api/cache_stats.py` (only if the response needs it; likely unchanged) | `backend/tests/test_cache_stats.py`, new `test_local_answer.py` |
| sc-131 | new `backend/app/agent_tools/stored_data_tools.py`, `backend/app/repositories/raw_fetches.py` (`list_visible_summaries`), **`backend/app/agent_runner.py`** (one import + `extra_groups=(PROFILE_TOOLS, STORED_DATA_TOOLS)`; sequenced), **`wcl_agent/tools/report_tools.py`** (extract the 3-line `report_query(field_calls, var_decls)` builder from `_report_fields` so the tool computes the exact key; fallback if not granted: duplicate the f-string with a pinning test) | new `backend/tests/test_stored_data_tools.py` |

Not touched: `ws.py`, `main.py`, `tenancy/context.py`, `conftest.py` (breaker reset is an autouse
fixture inside my test modules), the 039 guard test, docs outside `specs/045`.

`documentation/ai_guide.md` mentions `read_stats`; a one-line update there is optional — posted as
`backlog:` rather than requested.

**Structure Decision**: existing layout (backend/app + wcl_agent); one new module for sc-131.

## Complexity Tracking

None.
