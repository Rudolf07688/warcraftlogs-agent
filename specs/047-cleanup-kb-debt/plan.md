# Implementation Plan: Clean-up and KB debt

**Branch**: `047-cleanup-kb-debt` | **Date**: 2026-11-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/047-cleanup-kb-debt/spec.md`

## Summary

Six small debt fixes, one per story, each the smallest change that closes its root cause:
an explicit "no .env" switch for the test suite (sc-336); a tombstone on the summary's private
signal (sc-322); a breaker that counts timeouts (sc-323); a strict, indexed, projected
stored-reports lookup (sc-324, migration 0020); "went to WCL" passed from a shared load to its
joiners and the turn opened before its preamble (sc-326); a row lock that serialises message
numbering (sc-255). Design choices: [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.14 (uv)
**Primary Dependencies**: FastAPI, SQLAlchemy 2 async (asyncpg / aiosqlite), pydantic-settings,
python-dotenv, redis-py (fake in tests)
**Storage**: Postgres 17 + pgvector (prod), in-memory SQLite (most tests)
**Testing**: pytest + pytest-asyncio; `check.py run --pg ansel` for the Postgres-only tests
**Target Platform**: Linux container, one uvicorn worker
**Project Type**: web service (backend only in this feature)
**Performance Goals**: character lookup reads a projection (a few KB per row), not full payloads
**Constraints**: no live WCL/LLM calls; no new dependency; migration 0020 only
**Scale/Scope**: 6 stories, 10 points

## Constitution Check

| Principle | Status |
| --- | --- |
| I Reuse | `fetch_visible_clause` stays the one visibility rule; `_flight_key` / `exact_report_codes` / the fixed summary queries prove "our row"; the existing tombstone and `note_external_call` are extended, not duplicated. |
| II Small steps | One story per commit, verified before the next. |
| III Simplicity | Env switch, counter, flag, row lock, one partial index. No new service, setting surface or column. |
| IV Typed | Repository keeps its bytes boundary; breaker stays a dataclass. |
| V Async | All DB work stays async; the projection decode stays off the loop. |
| VI GitNexus | Impact run; `get_or_load` / `_shared` CRITICAL (board `risk:047`): additive change only. |
| VII shadcn | No UI. |
| VIII Backlog | Stories sc-336, sc-322, sc-323, sc-324, sc-326, sc-255 move In Progress → Under Review. |

Gate: pass, nothing in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/047-cleanup-kb-debt/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md, tasks.md, checkpoint.md
```

### Source Code (repository root)

```text
backend/app/config.py                         # sc-336 dotenv switch
backend/tests/conftest.py                     # sc-336 sets the switch before app imports
backend/app/services/fetch_persistence.py     # sc-322 bury summary-private codes
specs/045-local-data-reads/spec.md            # sc-322 FR-010 as built
backend/app/services/raw_fetch_reads.py       # sc-323 breaker counts timeouts
backend/app/repositories/raw_fetches.py       # sc-324 strict + projected summaries
backend/app/agent_tools/stored_data_tools.py  # sc-324 caller: unchanged (same body shape, cut down)
backend/app/db/models.py                      # sc-324 index declaration
backend/migrations/versions/0020_raw_fetch_summary_index.py
wcl_agent/cache/cache.py                      # sc-326 joiners / lock waiters count external
backend/app/api/ws.py                         # sc-326 open the turn before the preamble
backend/app/db/repository.py                  # sc-255 lock the conversation row
backend/tests/test_047_*.py                   # new tests, one file per story
```

**Structure Decision**: existing backend layout; new tests in new files only.

## Complexity Tracking

None.
