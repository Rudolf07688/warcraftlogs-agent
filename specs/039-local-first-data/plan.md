# Implementation Plan: Local-first data (epic 103, first slice)

**Branch**: `039-local-first-data` | **Date**: 2026-11-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/039-local-first-data/spec.md`

## Summary

Make the global `raw_fetches` store safe to read (sc-178), cheap to write (sc-177), and then
read it before calling Warcraft Logs (sc-129). Visibility: a stored row is served to a tenant
only when every report it names is **public** (seen from WCL, per-report status table) or
**granted** to that tenant (the tenant fetched the code from WCL itself), both confirmed in
the last day (`RAW_STORE_REVERIFY_DAYS`, 1). Exactly one repository function reads the table. A WCL response that shows a
single report missing/private deletes every row naming it and evicts its Redis report keys.
Reads hook into the WCL client like the existing fetch sink: a backend-installed **fetch
source** is consulted in `AsyncWCLClient.query` (per caller, before single-flight), so the
order is Redis (callers' `get_or_load`) → store → WCL, and a store hit back-fills Redis through
the unchanged loaders. Details: [research.md](research.md), [data-model.md](data-model.md),
[contracts/raw-store.md](contracts/raw-store.md).

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async (asyncpg / aiosqlite), redis.asyncio,
httpx. No new dependency.

**Storage**: PostgreSQL 17 (JSONB, GIN, RLS); SQLite for unit tests. Migration
`0018_raw_store_visibility` (down_revision `0017_proposal_user_rls`).

**Testing**: pytest (SQLite suite) + Postgres-only tests behind `TEST_DATABASE_URL` on a
throwaway `postgres:17` (port 15439).

**Target Platform**: Linux server (Docker compose in production).

**Project Type**: web service (backend) + standalone `wcl_agent` package.

**Performance Goals**: a store hit costs ≤ 3 small indexed queries plus one payload read
(milliseconds, vs. hundreds of ms to seconds for WCL); a store lookup is bounded by a 3 s
timeout and never fails a turn.

**Constraints**: `wcl_agent` stays DB-free (fetch source / sink are callables the backend
installs); the CLI/eval path is untouched when nothing is installed; no Redis redesign.

**Scale/Scope**: one table change, two new tables, ~4 modules touched.

## Constitution Check

| Principle | Status |
|---|---|
| I. Reuse-first | Reuses the sink pattern (`set_fetch_sink`) for the source, `report_codes`, `is_finished`/`FINAL_AFTER`, `WCL_CACHE_UNFINISHED_TTL`, `_insert`, `set_scope`, the existing writer queue. One read function. |
| II. Step-wise | Three stories in order, each committed and tested on its own (sc-178 → sc-177 → sc-129). |
| III. Simplicity | No new service or dependency. Two small tables (needed by the visibility rule); one kill switch for reads. See Complexity Tracking. |
| IV. Typed contracts | `ReportGone`, `PendingWrite`, `ReportStatus` dataclasses; typed callables for sink/source. |
| V. Async | All DB/Redis I/O async; big JSON parses off the loop (existing 256 KB rule). |
| VI. GitNexus | Impact run before each symbol edit; detect-changes before each commit. |
| VII. shadcn | No UI. |
| VIII. Backlog | Stories In Progress → Under Review; follow-ups posted as `backlog:` notices. |

## Project Structure

### Documentation (this feature)

```text
specs/039-local-first-data/
├── plan.md  research.md  data-model.md  quickstart.md  checkpoint.md  tasks.md
└── contracts/raw-store.md
```

### Source Code

```text
backend/migrations/versions/0018_raw_store_visibility.py   # new
backend/app/db/models.py                 # RawFetch.payload_hash, RawReport, RawFetchGrant
backend/app/repositories/raw_fetches.py  # writes + the ONE read function + delete-on-gone
backend/app/services/fetch_persistence.py# batched writer, grants, report status, gone, logs
backend/app/services/raw_fetch_reads.py  # new: the fetch source (identity, freshness, timeout)
backend/app/main.py / config.py          # lifespan wiring, two settings
wcl_agent/client/wcl_client.py           # fetch source hook, ReportGone offer
wcl_agent/client/queries.py              # summary fields + code, visibility
wcl_agent/cache/cache.py                 # evict_report(code)
documentation/architecture/backend-data-infra.html  # store section + monitoring query
backend/tests/test_raw_fetch_*.py, test_raw_store_*_pg.py
```

**Structure Decision**: existing layout; one new service module (`raw_fetch_reads.py`), as the
brief allows.

## Complexity Tracking

| Addition | Why needed | Simpler alternative rejected because |
|---|---|---|
| `raw_reports` table | "public" and "finished" are per report, not per row; summary rows carry them | Deriving from tenant tables or each payload: no visibility there, and most report rows have no end time |
| `raw_fetch_grants` table (RLS) | the owner's "codes the tenant already references", WCL-verified | UNION over tracked/recent raids/messages: misses chat-only codes, couples to 4 RLS tables and free text |
| 1-day re-verify window | without it a store-served report never meets a refresh, so delete-on-private never fires | indefinite grants: the owner's revocation rule would be dead code for hot reports |
| `wcl_store_reads_enabled` switch | the new read path sits on every WCL call; the owner can turn it off without losing writes | none needed beyond an env flag |
