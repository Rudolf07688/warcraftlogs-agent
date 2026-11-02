# Implementation Plan: Raw-store hardening

**Branch**: `051-raw-store-hardening` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/051-raw-store-hardening/spec.md`

## Summary

Three hardening stories on the raw WCL store (features 020/039/045/047):

1. **sc-359**: migration 0020 and the new 0021 build and drop indexes `CONCURRENTLY` inside
   `op.get_context().autocommit_block()`; the rule goes into `backend/migrations/script.py.mako`.
2. **sc-353**: tombstone overflow inside the in-flight window raises a stale floor instead of
   forgetting the protection; gone signals bypass the queue caps and a dropped own summary is
   salvaged into a codes-only gone signal; a null entry of a stored batch summary is a gone signal.
3. **sc-354**: `raw_fetches.own_summary` set at write time and backfilled by 0021; the lookup
   filters on it in SQL, drops the `fetched_at >= since` bound, and on Postgres reads only
   own-summary rows naming a code granted to the tenant or confirmed public inside the window
   (partial GIN index). No per-row key re-derivation.

## Technical Context

**Language/Version**: Python 3.12 · **Primary Dependencies**: SQLAlchemy 2 async, Alembic,
asyncpg · **Storage**: Postgres 17 (pgvector image) in prod, SQLite in most tests ·
**Testing**: pytest via `check.py` (`--pg` for the Postgres-only tests), `pg.py` for migration
up/down · **Project Type**: web service backend · **Performance Goals**: the stored-reports
lookup reads rows proportional to the recently confirmed reports, not to history; no Python work
per row · **Constraints**: tombstone memory fixed (1024 entries + one timestamp); no new
dependencies; migrations don't lock `raw_fetches` writes · **Scale/Scope**: 4 source files, 2
migrations, template, tests.

## Constitution Check

- **I Reuse**: `_report_statuses` parses salvaged summaries (no second parser); the backfill reuses
  `_flight_key`, `exact_report_codes` and the query builders; visibility stays the one
  `fetch_visible_clause`.
- **II Small steps**: one story at a time, each with its tests (order 359, 353, 354).
- **III Simplest**: a floor timestamp instead of a second eviction policy; a boolean column instead
  of query-text storage; no driver on SQLite (results identical, it is a perf filter).
- **IV Typed**: `_Tombstones(OrderedDict)` with a typed `floor`; no new boundary types.
- **V Async**: big salvaged bodies parse via `asyncio.to_thread` (existing helper).
- **VI GitNexus**: impact run (board `risk:051`): `upsert_raw_fetch` HIGH, signature unchanged.
- **VII/VIII**: no UI; Shortcut states moved per story.

Gate: PASS.

## Project Structure

```text
backend/migrations/script.py.mako                      # the CONCURRENTLY rule (comment)
backend/migrations/versions/0020_raw_fetch_summary_index.py   # CONCURRENTLY + autocommit
backend/migrations/versions/0021_raw_fetch_own_summary.py     # new: column, backfill, indexes
backend/app/db/models.py                               # RawFetch.own_summary + index decls
backend/app/repositories/raw_fetches.py                # flag at write, lookup rewrite
backend/app/services/fetch_persistence.py              # tombstones, signals, null entries
backend/tests/test_051_tombstones.py                   # new (sc-353, SQLite)
backend/tests/test_051_own_summary.py                  # new (sc-354, SQLite)
backend/tests/test_051_raw_store_pg.py                 # new (sc-354 RLS + backfill, 359 up/down)
backend/tests/test_047_stored_reports_pg.py            # index assertions updated (decision)
```

## Risks

- **Backfill on a big table**: one pass over the summary rows' keys/params (no payloads), updates
  in chunks of 1000 keys; the column add is metadata-only on Postgres 11+.
- **Planner ignoring the GIN driver**: proved with `EXPLAIN` under `enable_seqscan=off` and an
  `EXPLAIN ANALYZE` read count, like 047.
- **Floor too eager**: under a flood, in-flight report fetches aren't stored (availability only);
  normal traffic never overflows 1024 tombstones in 10 minutes.
- **Signals bypass caps**: codes only, one per WCL answer while full; WCL's point budget bounds it.
