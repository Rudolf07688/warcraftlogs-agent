# Research: 045 local data reads

## R1 Probe timeout and breaker
- **Decision**: 400 ms default (`RAW_STORE_PROBE_TIMEOUT_MS`), breaker 30 s, half-open with one trial. Opens on a connection error at once and on the 3rd consecutive timeout (the half-open trial: its first). Failures are `TimeoutError`, `OSError`, SQLAlchemy `OperationalError`/`InterfaceError`/pool `TimeoutError` and any `DBAPIError` with `connection_invalidated`. Other errors: a miss.
- **Rationale**: a healthy local Postgres answers in 1-5 ms; a hit is worth it only when fast (QA PERF-001). A bug shouldn't disable the store for everyone.
- **Alternatives**: per-loop breaker (DB health is process-wide, not per loop); counting failures before opening (first answer: one stall already costs a turn; 047 sc-323 changed it to 3 consecutive timeouts, because one slow read must not disable the store for 30 s).

## R2 Statement budget
- **Decision**: lookup → statuses → (set_config) → visibility+payload pinned to `fetched_at`. Miss 1, stale 2, hit 3-4.
- **Rationale**: meets the AC with plain portable SQL; freshness stays a Python callback as contract 3 requires.
- **Alternatives**: LATERAL `jsonb_array_elements_text` / `json_each` join folding statuses into the lookup (hit 3 always) — dialect branches for one statement; rejected for simplicity. Folding `set_config` into the same statement — evaluation order vs. the RLS policy isn't guaranteed.

## R3 Probe inside single-flight
- **Decision**: probe runs in `_fetch` in a lane slot; flight key = `_flight_key` + `source.scope()` (tenant id or "") when a source is installed.
- **Rationale**: dedupes identical concurrent probes, caps DB connections at the lane limit (PERF-004), keeps visibility per workspace. Without a source (CLI, evals, tests) the key is unchanged.
- **Alternatives**: a module semaphore in the source (keeps N duplicate probes); single flight across workspaces (leaks a grant to a joiner — rejected).
- **Note**: the probe precedes the 429 block check so stored answers keep working while WCL is blocked.

## R4 Payload bytes (PERF-006)
- **Decision**: Postgres `convert_to(payload::text, 'UTF8')` (bytea → `bytes` from asyncpg); SQLite `CAST(payload AS BLOB)`.
- **Rationale**: removes the asyncpg text decode and `str.encode` on the loop; `jsonb_out` stays in the database.

## R5 Back-fill signal
- **Decision**: `StoredFetch.shared` = every code public (SQL clause with `tenant_id=None`). Each waiter in `query()` marks the current load holder when not shared; `get_or_load`/`get_many_or_load` skip SET + memo.
- **Rationale**: the waiter's own context reaches its loader's holder (ContextVar → mutable object survives `gather` copies).
- **Alternatives**: tenant-aware Redis keys for non-public reports (more keys, every caller changes).

## R6 Race 1 (stale write after gone)
- **Decision**: tombstone status `gone` in `raw_reports` + `FetchedResponse.requested_at`; writer skips items requested at/before a tombstone of any of their codes.
- **Evidence it is real**: `_offer` stamps `fetched_at` at response arrival; a table request started before a summary's `report: null` and answered after it is queued after the gone and re-inserts its row; the tenant's grant (kept by `delete_report`) makes it visible again for the re-verify window.
- **Alternatives**: ordering by `fetched_at` alone (arrival time doesn't order requests); a tombstone table (migration).

## R7 Race 2 (loader refills Redis after eviction)
- **Decision**: Redis tombstone `wcl:v1:gone:<code>` (TTL `lock_ms`, longer than the 75 s query timeout) set before the SCAN; report-family writes check after SET and delete their own key.
- **Rationale**: write-then-check ordering is safe without Lua: SET before SCAN → scanned; SET after tombstone → check deletes.

## R8 Turn boundary
- **Decision**: `set_refresh_actor` (called by `ws.py` at turn start/end) opens/closes a per-turn usage holder.
- **Alternatives**: wrap `stream_response` in `agent_runner.py` (sequenced file, also used outside turns); edit `ws.py` (Ansel's).

## R9 Exact lookups
- **Decision**: exact keys through `read_visible_fetch` for fights and tables; a visible-summaries list query for characters; one `not_stored` result for absent, invisible and stale.
- **Rationale**: the visibility rule is the only gate; identical results never leak existence.
