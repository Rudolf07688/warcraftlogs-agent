# Research: Clean-up and KB debt

## R1 (sc-336) How the suite stops reading .env

- **Decision**: `backend/app/config.py` reads `WCL_LOAD_DOTENV` (default on; `0`/`false`/`no`
  switch it off) once at import. Off: no `load_dotenv()`, and `Settings.model_config.env_file` is
  None. `backend/tests/conftest.py` sets `WCL_LOAD_DOTENV=0` at its very top, before it imports
  any app module (pytest imports the conftest before any test module).
- **Why**: `load_dotenv()` walks up from `config.py`'s folder, so any test that imports the
  backend loads the checkout's `.env` into `os.environ` whatever the cwd; `env -i` doesn't help.
  An explicit switch is visible and testable; it also lets a developer run the app without its
  `.env`.
- **Alternatives**: detect pytest via `sys.modules` (implicit, prod code knowing about tests);
  move `load_dotenv()` into `main.py` (not in the footprint, and tests import `main.py` too);
  drop `env_file` only (leaves the `load_dotenv()` path).
- `wcl_agent/cli.py` loads `.env` inside `_main()` only, which no test runs: unchanged.

## R2 (sc-322) Tombstone on the summary's private signal

- **Decision**: in `_store_one`, the codes a summary finds private are buried (`_bury(gone,
  item.fetched_at)`) before their rows are deleted, exactly like a `ReportGone`.
- **Why**: a fetch requested at or before the moment WCL said "private" is stale; `_stale`
  already drops it. The summary's `fetched_at` is the time the private status was observed.
- 045 FR-010 is rewritten to the in-process design (per process, 10 min TTL, 1024 cap, lost on
  restart, accepted for one uvicorn worker).

## R3 (sc-323) Breaker

- **Decision**: `Breaker` gains `timeouts` (consecutive count) and `TIMEOUTS_TO_OPEN = 3`.
  `StoreSource` classifies: a timeout (asyncio timeout, pool wait) calls `breaker.timed_out()`,
  which opens on the 3rd in a row or when it was the half-open trial; any other outage (OSError,
  OperationalError, InterfaceError, invalidated connection) calls `failed()`, which opens at once.
  A success resets the count.
- Note `TimeoutError` is a subclass of `OSError`: the timeout check comes first.

## R4 (sc-324) Strict, bounded character lookup

- **Our row**: the row keeps no query text, but its key is `sha256(query + " " + params)`. For a
  row of `ReportSummary` with params `{code}` or `ReportsBatch` with params `{c0..cn-1}`, the
  server recomputes the key from its own fixed query text and the stored params; equal keys prove
  the row came from our query (the model's `run_wcl_graphql` may name a query `ReportSummary` but
  can't produce that key). The params must also give exact codes (`exact_report_codes`) equal to
  the row's `report_codes`, else the row is dropped.
- **Bounded**: migration 0020 adds a partial index `ix_raw_fetches_summaries` on
  `raw_fetches (fetched_at DESC) WHERE operation_name IN ('ReportSummary','ReportsBatch')`;
  the query keeps exactly that predicate, orders by `fetched_at DESC` and limits, so Postgres
  walks the index. `SET LOCAL statement_timeout` (2 s) applies to the transaction on Postgres.
  The database projects each report object to `code, title, startTime, zone.name,
  masterData.actors[].name` in the existing body shape, so the caller's parser is unchanged.
- Visibility stays `fetch_visible_clause` (guard test unchanged).
- **Alternatives**: a players lookup column (bigger migration, backfill; YAGNI); verifying
  "ours" in SQL (would re-implement JSON serialisation in SQL).

## R5 (sc-326) Local-answer rate

- **Joiners**: `get_or_load`'s `_Load` gains `external`; `note_external_call()` also marks the
  running load. The shared flight returns it; a caller that joined calls `note_external_call()`
  when the load went to WCL. A nested load passes its flag to the enclosing one.
- **Lock waiters**: `_wait_for_winner` notes an external call when it gets the other process's
  value (it can't tell how that process loaded it; external is the safe side).
- **Preamble**: `ws._handle_turn` opens the turn (`set_refresh_actor`) before
  `_build_turn_preamble`; a failure there closes it again.
- The client's own single-flight already notes each waiter in its own context (unchanged).

## R6 (sc-255) Message numbering

- **Decision**: `_next_seq` first locks the conversation row (`SELECT id FROM conversations WHERE
  id = :conv AND tenant_id = :tenant FOR UPDATE`). Under READ COMMITTED the following
  `max(seq)` statement sees the other transaction's committed row. SQLite ignores `FOR UPDATE`.
- **Alternatives**: retry on unique violation with a savepoint (more code, races remain visible
  in logs); a per-conversation counter column (migration).
