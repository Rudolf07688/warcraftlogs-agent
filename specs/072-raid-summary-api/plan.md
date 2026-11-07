# Implementation Plan: Raid summary from stored data

**Branch**: `072-raid-summary-api` | **Date**: 2026-11-07 | **Spec**: [spec.md](spec.md)

## Summary

`GET /api/raids/{report_code}/summary`: the tracked-raid check (`repo.get_tracked_raid`), then
two reads of the raw store through `fetch_visible_clause`, then a pure projection in Python into
the contract's pydantic models. No WCL client is touched.

## Technical Context

Python 3.12, FastAPI (async), SQLAlchemy 2 async (Postgres + SQLite tests), pydantic v2. Reuses
`wcl_agent` helpers: `_summary_from`, `pick_boss_fights` (kickoff's boss fights), `report_query`,
`_table_query`, `_fight_ids`, participants `_FIELDS` and `participants_from_player_details`,
`_flight_key`, `neutralise`/`_bounded`, `DIFFICULTY_NAMES`, `server_slug`.

## Constitution Check

Reuse first (the tools' own query builders and parsers), one visibility rule (no second rule:
both new reads are `fetch_visible_clause` filters), typed boundary (pydantic response models in
the service module, `schemas.py` is 074's), async throughout, no new dependency or migration.

## Design

1. **Route** (`backend/app/api/raids.py`): `GET /{report_code}/summary`, `require_session`, a
   `valid_report_code` dependency (`[A-Za-z0-9]{1,32}`, else 404) declared before `get_tenant_db`.
2. **Repository** (`backend/app/repositories/raw_fetches.py`, the only module that reads
   `raw_fetches`):
   - `read_visible_summary(session, code, *, tenant_id, since) -> (bytes, fetched_at) | None`:
     newest `own_summary` row naming `code` (`_names_report`), filtered by `fetch_visible_clause`.
   - `read_visible_parts(session, query_keys, paths, *, tenant_id, since)`: for the visible rows
     among `query_keys`, the JSON at each path (Postgres `#>`, SQLite `json_extract`), so a
     multi-MB Summary table never leaves the database whole.
3. **Service** (`backend/app/services/raid_summary.py`): pydantic models `RaidSummary`,
   `Participant`, `MyCharacter`, `Parse`; `summarize(session, code, *, tenant_id, now)` returns
   None (→ 404) for an untracked code. Keys: participants and player-details (fight 0), Summary
   table per boss fight, rankings Rankings/Historical for fight 0 and per boss fight. Every walk
   of a stored body is type-checked; a malformed part is dropped.
4. **Identity**: own characters from `repo.list_own_characters`; match by name (casefold) and
   realm slug and region where the stored row has them.

## Files

- `backend/app/api/raids.py` (route + code dependency)
- `backend/app/repositories/raw_fetches.py` (two reads)
- `backend/app/services/raid_summary.py` (new)
- `backend/tests/test_072_raid_summary.py` (new, SQLite), `backend/tests/test_072_raid_summary_pg.py` (new, Postgres)

## Risks

- Keys drift if a tool changes its query text → pinned by a test that runs the tools against a
  fake client and compares keys.
- `fetch_visible_clause` per row is a correlated EXISTS; both reads are bounded (1 row; ≤ 23 keys).
