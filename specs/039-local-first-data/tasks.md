# Tasks: Local-first data (039)

**Input**: specs/039-local-first-data/ (plan, spec, research, data-model, contracts/raw-store.md)
**Tests**: required by the brief's ACs (each story lists its tests).

## Phase 1: Setup

- [X] T001 Start Postgres `wcl-039-pg` on port 15439 and run `uv sync --extra test` in the worktree; record the green baseline test count

## Phase 2: Foundational

- [X] T002 Migration `backend/migrations/versions/0018_raw_store_visibility.py`: `raw_fetches.payload_hash`, `raw_reports`, `raw_fetch_grants` (+ RLS tenant_isolation, grants); downgrade reverses
- [X] T003 Models `RawReport`, `RawFetchGrant`, `RawFetch.payload_hash` in `backend/app/db/models.py`
- [X] T004 Settings `raw_store_reverify_days` (7) and `wcl_store_reads_enabled` (True) in `backend/app/config.py`

## Phase 3: US1 sc-178 visibility rule (P1)

**Goal**: a stored row is served only to tenants allowed by the rule; gone reports are deleted.
**Independent test**: `backend/tests/test_raw_store_visibility.py`, `backend/tests/test_raw_store_pg.py`.

- [X] T005 [US1] `REPORT_SUMMARY_FIELDS` gains `code visibility` in `wcl_agent/client/queries.py`
- [X] T006 [US1] `ReportGone` + gone detection in `_fetch` (single-report query, `reportData.report` null) in `wcl_agent/client/wcl_client.py`
- [X] T007 [US1] `evict_report(code)` (SCAN `wcl:v1:report:<escaped>:*` + DEL, fail open) in `wcl_agent/cache/cache.py`
- [X] T008 [US1] Repository: `grant_codes`, `record_report_status`, `delete_report`, `read_visible_fetch` (the one read function) in `backend/app/repositories/raw_fetches.py`
- [X] T009 [US1] Writer: `PendingWrite` with tenant from `current_identity` in `offer`; grants on success; report status from summary bodies; `ReportGone`/private → delete + evict, in `backend/app/services/fetch_persistence.py`
- [X] T010 [US1] Tests (SQLite): A can't read B-only code; public row shared; stale grant/public (> 7 days) hidden; batch row needs every code; long code never visible; gone deletes all rows + status; Redis keys evicted (fake_redis); no-identity fetch grants nothing; guard test: only the repository selects `RawFetch` — `backend/tests/test_raw_store_visibility.py`
- [X] T011 [US1] Client tests: null report offers `ReportGone` not the response; batch / validation error / HTTP error don't — `backend/tests/test_raw_fetch_client.py`
- [X] T012 [US1] Postgres tests: RLS hides another tenant's grants with the app filter omitted; JSONB delete via `report_codes ?`; full visibility path on PG — `backend/tests/test_raw_store_pg.py`
- [X] T013 [US1] Update existing writer/store tests to the batch store signature — `backend/tests/test_raw_fetch_writer.py`, `backend/tests/test_raw_fetch_store.py`; commit US1

## Phase 4: US2 sc-177 writer hardening (P2)

**Goal**: unchanged payloads aren't rewritten, batched commits, edge cases safe, monitoring.
**Independent test**: `backend/tests/test_raw_fetch_writer.py`, `backend/tests/test_raw_fetch_store.py`.

- [ ] T014 [US2] `write_fetch`: hash (sans `_cost`), SELECT stored hash, same → `fetched_at` only, else upsert with hash; op name `[:120]`; `report_code` None when > 32; NUL escape strip — `backend/app/repositories/raw_fetches.py`
- [ ] T015 [US2] Consumer batches ≤ 20 items per transaction, per-item retry on non-timeout errors; `_Throttle.flush()` on stop; failure logs = class + SQLSTATE — `backend/app/services/fetch_persistence.py`
- [ ] T016 [US2] Tests: unchanged vs changed payload; batch of N = 1 commit (counting sessions); one bad item loses only itself; long code/op name and `\u0000` stored (SQLite + PG); throttle flushed on stop; DB error log has no params — `backend/tests/test_raw_fetch_store.py`, `backend/tests/test_raw_fetch_writer.py`, `backend/tests/test_raw_store_pg.py`
- [ ] T017 [US2] Monitoring query + retention rule in `documentation/architecture/backend-data-infra.html` (and quickstart §3); commit US2

## Phase 5: US3 sc-129 DB-first reads (P3)

**Goal**: Redis → store → WCL; finished report data served without a WCL call.
**Independent test**: `backend/tests/test_raw_store_reads.py`.

- [ ] T018 [US3] `FetchSource` + `set_fetch_source`; `query` consults it per caller before single-flight — `wcl_agent/client/wcl_client.py`
- [ ] T019 [US3] `read_stored_fetch` (no codes → None; identity tenant; 3 s timeout; freshness R6; errors → None) — `backend/app/services/raw_fetch_reads.py`
- [ ] T020 [US3] Lifespan: install/uninstall the source when persistence + reads are enabled — `backend/app/main.py`
- [ ] T021 [US3] Tests: finished-report hit makes 0 WCL calls; live row older than 120 s refetched, younger served; hidden row = miss + WCL; store error/timeout falls back; Redis back-filled (fake_redis, second read 0 store reads); joined single-flight caller of another tenant isn't served; no source → unchanged (CLI path) — `backend/tests/test_raw_store_reads.py`; commit US3

## Phase 6: Polish

- [ ] T022 Bypass attempt on the visibility rule; record what was tried and what stopped it
- [ ] T023 Full suite (clean env) + PG suite + migration round trip; GitNexus detect-changes; ownership check
- [ ] T024 Board: live-check:039 question, handoff; stories → Under Review

## Dependencies

Setup → Foundational → US1 → US2 → US3 → Polish. US2 builds on US1's writer; US3 needs US1's
read function. If US1 runs long, US3 is dropped (owner's rule), not rushed.
