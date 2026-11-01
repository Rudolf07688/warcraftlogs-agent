# Tasks: Local data reads (045)

**Input**: `specs/045-local-data-reads/` (plan.md, spec.md, research.md, data-model.md, contracts/)
**Tests**: required by every AC ("tested ..."); each implementation task ships with its test.
Run suites in a clean env: `env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q`.

## Phase 1: Setup

- [X] T001 Record the baseline: full SQLite suite count and the 039 visibility tests (`backend/tests/test_raw_store_visibility.py`, `test_raw_store_reads.py`, `test_raw_store_041.py`) green; note counts in `specs/045-local-data-reads/checkpoint.md`

## Phase 2: Foundational (blocks US1-US4)

- [X] T002 Add `fetch_visible_clause(raw_fetch_id, *, tenant_id, since)` (contract 3) in `backend/app/repositories/raw_fetches.py`, with clause-level tests (public, granted, expired check, overlong code, no codes, `tenant_id=None`, value and column forms) in `backend/tests/test_raw_store_probe.py`
- [X] T003 Rewrite `read_visible_fetch` on the clause per plan statements 1-4 (lookup, statuses, conditional one-statement `set_config`, visibility+shared+payload bytes pinned to `fetched_at`), returning a typed result (body bytes + shared + outcome) in `backend/app/repositories/raw_fetches.py`; 039 tests unchanged and green; statement-count tests (miss 1, stale 2, hit ≤ 4, all-public hit without set_config) in `backend/tests/test_raw_store_probe.py`

## Phase 3: US1 sc-295 cheap, fail-fast probe and writer (P1)

**Independent test**: hung session → one bounded wait then no probe for 30 s; fake source inside single-flight; writer round trips counted.

- [X] T004 [US1] Add `raw_store_probe_timeout_ms: int = 400` to `backend/app/config.py`
- [X] T005 [US1] Breaker (closed/open/half-open, trial slot, cancellation frees the trial) + probe timeout + outcome mapping in `backend/app/services/raw_fetch_reads.py`; tests for every transition with a hung session and a connection error, and "non-connection error is a miss, breaker stays closed" in `backend/tests/test_raw_store_probe.py` (autouse breaker reset fixture in that module)
- [X] T006 [US1] Make the source an object (`__call__` → `StoredFetch | None`, `scope()` → tenant id or "") keeping the name `read_stored_fetch` in `backend/app/services/raw_fetch_reads.py`; update `backend/tests/test_raw_store_reads.py` for the new return type
- [X] T007 [US1] Client: `StoredFetch`, `FetchSource` Protocol, flight key with `source.scope()`, probe inside `_fetch` in a lane slot before the 429 block check, no cost log / sink on a stored answer, in `wcl_agent/client/wcl_client.py`; tests (10 identical calls → 1 probe; two scopes → 2 flights; probe holds a lane slot; blocked budget still serves stored; no source → unchanged key) in `backend/tests/test_raw_fetch_client.py`
- [X] T008 [US1] Probe counters: `record_store(outcome)` into the `local` metrics hash in `wcl_agent/cache/cache.py`, called once per probe from `backend/app/services/raw_fetch_reads.py`; test in `backend/tests/test_raw_store_probe.py`
- [X] T009 [US1] Writer: one-statement `_scope_tenant` set once per tenant per transaction; grant refresh only when > 1 h older; `upsert_raw_fetch` returns changed (RETURNING); `store_batch` returns `BatchResult(gone, changed)` (contract 5) in `backend/app/repositories/raw_fetches.py` and `backend/app/services/fetch_persistence.py`; tests (statement count per item, unchanged grant not rewritten, changed flags) in `backend/tests/test_raw_fetch_writer.py`
- [X] T010 [US1] Postgres run of the probe + writer + 039 PG tests on `wcl-045-pg:15445` (`backend/tests/test_raw_store_pg.py`, add a PG statement-count + RLS-scoped grant hit case)
- [X] T011 [US1] PERF-007 decision posted on the board (`scope:045:perf-007`)

## Phase 4: US2 sc-296 revocation lag and races (P2)

**Independent test**: fakeredis + SQLite writer, no network.

- [X] T012 [US2] Load holder + `mark_unshareable()` in `get_or_load` / `_load_and_store` / `get_many_or_load` (skip SET and memo) in `wcl_agent/cache/cache.py`; client marks it per waiter when `shared` is false in `wcl_agent/client/wcl_client.py`; tests (granted-only hit → no Redis key; public hit → key; gather sub-task marking) in `backend/tests/test_raw_store_races.py`
- [X] T013 [US2] Race 1 (tombstone moved into the writer process, board #63; `delete_report` unchanged): `FetchedResponse.requested_at`; `_store_one` skips items requested at/before a tombstone in `backend/app/repositories/raw_fetches.py`, `backend/app/services/fetch_persistence.py`, `wcl_agent/client/wcl_client.py`; tests (stale table after gone → no row, no grant; later fetch → stored; newer summary replaces tombstone; tombstoned code not visible) in `backend/tests/test_raw_store_races.py`
- [X] T014 [US2] Race 2: Redis tombstone in `evict_report`, check-after-write for report-family keys in `wcl_agent/cache/cache.py`; tests (loader SET after eviction → gone; before → scanned; non-report family unaffected) in `backend/tests/test_raw_store_races.py`
- [X] T015 [US2] Stop 2: full suite + PG tests, detect-changes, commit, hand-off for sc-295 + sc-296; post `released` for `fetch_persistence.py`, `config.py`, `raw_fetches.py`

## Phase 5: US3 sc-132 local-answer rate (P2)

- [ ] T016 [US3] Turn holder opened/closed by `set_refresh_actor`, `turns`/`local_turns` counted, in `wcl_agent/cache/cache.py`; client marks network calls (success or failure) in `wcl_agent/client/wcl_client.py`; tests (no WCL call → local; one network call → not; stored hit → local; failed call → not; thread/sub-task marking) in `backend/tests/test_local_answer.py`
- [ ] T017 [US3] `read_stats` adds `store` and `local_answers`; `StoreStats`, `LocalAnswerStats` and the `CacheStats` fields in `backend/app/schemas.py`; tests (window sums, rates, degraded shape) in `backend/tests/test_cache_stats.py`

## Phase 6: US4 sc-131 exact lookups (P3) — after resolver merge + `raw_fetches.py` back from Ansel

- [ ] T018 [US4] `list_visible_summaries(session, *, tenant_id, since, limit)` via `fetch_visible_clause` in `backend/app/repositories/raw_fetches.py`
- [ ] T019 [US4] Shared `report_query(field_calls, var_decls)` builder in `wcl_agent/tools/report_tools.py` (if granted; else pinned duplicate)
- [ ] T020 [US4] Tools + `STORED_DATA_TOOLS` group in `backend/app/agent_tools/stored_data_tools.py`; tests (visible, not visible == not stored byte-identical, stale, resolver error, outside a turn, bounds) in `backend/tests/test_stored_data_tools.py`
- [ ] T021 [US4] Register the group in `backend/app/agent_runner.py` (when granted)

## Phase 7: Polish

- [ ] T022 Full suite, PG tests, detect-changes, ownership check, commit, final hand-off; stories to Under Review; live-check question on the board

## Dependencies

T002 → T003 → US1 (T004-T011) → US2 (T012-T014, needs `StoredFetch` from T007) → Stop 2 → US3 (T016-T017, needs T008) → US4 (T018-T021, needs resolver + grants). T004 ∥ T002. T013 ∥ T014 (different code paths, same test file: sequential edits).

## Implementation strategy

MVP = Phase 2 + US1 (contract 3 for 044 lands first). Stop 2 merges US1+US2. Then US3, then US4.
