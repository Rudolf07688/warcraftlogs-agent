# Tasks: Raw-store hardening

**Input**: `specs/051-raw-store-hardening/` (plan.md, spec.md, research.md, data-model.md)
**Tests**: required by the brief's ACs (each AC proven by a test or a recorded check).

## Phase 1: Setup

- [X] T001 Branch `051-raw-store-hardening` off `sprint-2026-11-02` in `/home/rudolf/dev/wcl-worktrees/dev-b`; stories to In Progress as each starts

## Phase 2: US1 — Index migrations don't lock writes (sc-359)

- [X] T002 [US1] Build/drop `ix_raw_fetches_summaries` CONCURRENTLY in `op.get_context().autocommit_block()` (Postgres only) in `backend/migrations/versions/0020_raw_fetch_summary_index.py`
- [X] T003 [US1] Write the concurrent-index rule as a comment in `backend/migrations/script.py.mako`

## Phase 3: US2 — Tombstones and signals (sc-353)

- [X] T004 [US2] `_Tombstones(OrderedDict)` with `floor`; `_bury` skips codes over `MAX_CODE` and raises `floor` on an in-window overflow eviction; `_stale` honours `floor` — `backend/app/services/fetch_persistence.py`
- [X] T005 [US2] `_report_statuses`: a null `r{i}` entry of our batch query is a gone code (`c{i}`) — same file
- [X] T006 [US2] `FetchWriter`: own item cap (queue unbounded in asyncio terms), `ReportGone` never capped, a capped-out own summary salvaged into `ReportGone(codes, fetched_at)` by a tracked task awaited in `stop` — same file
- [X] T007 [US2] Tests: flood > cap keeps the real tombstone's protection; gone and private signals survive a full queue; null batch entry deletes + tombstones; bound — `backend/tests/test_051_tombstones.py`

## Phase 4: US3 — Own-summary lookup (sc-354)

- [X] T008 [US3] `RawFetch.own_summary` + new index declarations, drop `ix_raw_fetches_summaries`/`RAW_SUMMARY_PREDICATE` from the model; indexes on `RawReport`/`RawFetchGrant` — `backend/app/db/models.py`
- [X] T009 [US3] Migration `0021_raw_fetch_own_summary` (down_revision 0020): column, backfill helper (old rule), indexes CONCURRENTLY in an autocommit block, downgrade reverses — `backend/migrations/versions/0021_raw_fetch_own_summary.py`
- [X] T010 [US3] `upsert_raw_fetch` writes `own_summary`; `list_visible_summaries` filters on it, drops the fetch-time bound, Postgres driver `report_codes ?| ARRAY(grant ∪ public codes since)`; `_our_summary` removed — `backend/app/repositories/raw_fetches.py`
- [X] T011 [P] [US3] SQLite tests: flag at write, 250 forged rows don't crowd out, old row visible through a recent grant — `backend/tests/test_051_own_summary.py`
- [X] T012 [P] [US3] Postgres tests: two-tenant RLS visibility, backfill helper, driver plan/read bound — `backend/tests/test_051_raw_store_pg.py`; update the 0020-index assertions in `backend/tests/test_047_stored_reports_pg.py`
- [X] T013 [US3] Before/after lookup timing (scratch script, Postgres, 200 rows) recorded for the hand-off

## Phase 5: Polish

- [X] T014 Migration up/down on throwaway Postgres from 0019 and 0020 (quickstart.md), statements logged
- [ ] T015 `mutate.py` bites for the key guards (floor, signal bypass, null entry, own_summary filter)
- [ ] T016 GitNexus detect-changes, ownership check, `check.py run --pg ansel` on the committed head, hand-off

## Dependencies

US1 → US3 (0021 follows the rule and revises 0020's index). US2 is independent. T008 → T009/T010 → T011/T012.
