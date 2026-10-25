# Implementation Plan: Welcome Chat with Recent Raids and Mythic+ Runs

**Branch**: `022-welcome-mplus` | **Date**: 2026-10-25 | **Spec**: [spec.md](spec.md)

## Summary

Cap the welcome raid list at 6 shown and add a second list of the 6 most recent Mythic+ runs. M+ runs ride on feature 013's refresh: the same claim, record and background lane. The refresh's detail step also examines the non-raid reports it already lists, via the shared `report_summary` fetch with four keystone fields added to the fights query. Each completed keystone fight is stored as a tenant-owned `recent_mplus_runs` row, linked to the own characters in that report. A one-click run opens a chat with a server-owned M+ kickoff and the explicit title "M+ <dungeon> +<level>".

## Technical Context

**Language/Version**: Python 3.12 (FastAPI, async SQLAlchemy), TypeScript/React.
**Storage**: PostgreSQL, tenant RLS (new migration `0014`). Redis shared WCL cache (unchanged).
**Testing**: `uv run --extra test pytest -q`; `npm run build` in `frontend/`.
**Constraints**: no WCL wait on the welcome GET (013 FR-010); WCL only through `get_async_client()` in the background lane (so 020's write-through applies); no change to `wcl_client.py`.

## Constitution Check

I (reuse): reuses the 013 refresh/claim, `load_report_summaries`, `_own_character_link`, `kickoff_prompt_for`'s pattern and the `RaidCard` visual. No second WCL path. PASS.
II: three slices (backend caps, M+ data, UI). PASS.
III: one table pair is justified in Complexity Tracking. PASS.
IV/V: new Pydantic out-models; async handlers. PASS.
VI: impact checks run before every edit (see Risks).
VII: Welcome M+ card reuses the existing shadcn `Item`/`Badge` used by `RaidCard`; MCP registry search and audit run in implementation.

## Design

1. **Caps (FR-001/002).** New settings `recent_raids_shown = 6`, `recent_mplus_shown = 6` (`config.py`). `recent_raids_limit` (20) keeps its meaning: WCL listing depth, plus the cap on how many raid reports get details per refresh (`_refresh`'s `[: recent_raids_limit]` slice is left as is; shrinking it to 6 would leave older raids without details for no gain). The API passes `recent_raids_shown` to `repo.list_recent_raids`.
2. **Query (WCL).** `REPORT_SUMMARY_FIELDS` fights gain `startTime keystoneLevel keystoneBonus keystoneTime`. `FightSummary` gains `start_time_ms`, `keystone_level`, `keystone_bonus`, `keystone_time_ms` (optional); `_summary_from` in `wcl_agent/tools/report_tools.py` maps them. The `report_summary` cache key moves `v1` to `v2` so summaries cached without keystone fields are not served (24 h TTL otherwise).
3. **Detail step.** `_refresh` also takes the newest `MPLUS_REPORT_BATCH = 10` non-raid reports in `need` (new or not final), fetches their summaries with the existing `fetch_report_details` batching, and extracts runs: a fight with `keystone_level > 0` and `kill is True` is a completed run (abandoned and unfinished are dropped); `timed = keystone_bonus >= 1`; dungeon = fight name, falling back to the report zone name; `started_at = report start + fight start`. Rows are upserted (`ON CONFLICT DO NOTHING`, run key `(tenant_id, report_code, fight_id)`) with character links copied from the report's `ListedReport.character_ids`. A run is final once stored.
4. **Read.** `repo.list_recent_mplus_runs(tenant, limit)` mirrors `list_recent_raids` (two queries, only runs linked to an existing own character). `GET /api/recent-raids` returns `mplus_runs` next to `raids`, still never waiting on WCL. No M+ rows means an empty list and no section.
5. **Kickoff.** `POST /api/recent-raids/mplus/{report_code}/{fight_id}/investigate` (CSRF; the run must be one of the tenant's own stored runs, else 404) creates the conversation with title `M+ <dungeon> +<level>` (explicit via `create_conversation(title=...)`) and returns `InvestigateResponse`. `mplus_kickoff_prompt_for(report_code, fight_id, dungeon, level)` lives in `api/recent_raids.py` beside it; wording per FR-016. The frontend sends it as the first turn, as for raids.
6. **UI.** `WelcomePanel` renders a "Your recent Mythic+ runs" section after raids, only when `mplus_runs` is non-empty, using a new `MplusCard` with the `RaidCard` markup (Item, Badge for Timed/Depleted, dungeon + `+level`, date, characters). `onInvestigateMplus(reportCode, fightId)` goes through new `investigateMplusRun` in `restClient.ts` and a `handleInvestigateMplus` in `App.tsx` mirroring `handleInvestigateRaid` (it does not need `refreshRaids`).

## Complexity Tracking

| Addition | Why | Simpler alternative rejected |
|---|---|---|
| Tables `recent_mplus_runs`, `recent_mplus_run_characters` (migration 0014, RLS like 0010) | Runs must show instantly and stay tenant-private; a report holds several runs, so they cannot live in `recent_raids` | Deriving at read time from cached summaries: a cache miss would make the welcome GET wait on WCL |

## Project Structure

Files created or modified (see the ownership request):

```text
backend/app/services/recent_raids.py          # M+ extraction in _refresh
backend/app/services/recent_raid_types.py     # MplusRun value object
backend/app/api/recent_raids.py               # mplus_runs in GET, investigate endpoint, kickoff
backend/app/schemas.py                        # RecentMplusRunOut, response field   [verify free]
backend/app/db/repository.py                  # upsert/list/get mplus runs          [verify free]
backend/app/db/models.py                      # append RecentMplusRun(+Character)   [after 020 merges]
backend/app/config.py                         # 2 display-cap settings              [after 020 merges]
backend/migrations/versions/0014_recent_mplus_runs.py   # new, down_revision 0013_raw_fetches
wcl_agent/client/queries.py                   # keystone fields in REPORT_SUMMARY_FIELDS
wcl_agent/cache/cache_models.py               # FightSummary keystone fields
wcl_agent/cache/cache.py                      # report_summary key v1 -> v2
wcl_agent/tools/report_tools.py               # _summary_from maps keystone fields
frontend/src/components/WelcomePanel.tsx, frontend/src/types.ts,
frontend/src/api/restClient.ts, frontend/src/App.tsx
backend/tests/test_recent_mplus.py (new), backend/tests/test_recent_raids.py (cap assertions)
backend/tests/test_wcl_cache.py / test_cache_families.py                              # only if they pin the v1 key
specs/022-welcome-mplus/**
```

## Risks

- WCL keystone field semantics (`kill` on a depleted finish, fight `name` as dungeon, `keystoneBonus` 0 for depleted) come from the WCL v2 schema as documented; no live call is possible without credentials in this sprint, so tests use fixtures and the first live look is a hand-off item.
- `repo.list_recent_raids` signature is unchanged; `fetch_report_details` is unchanged. Impact checks for `_refresh`, `list_recent_raids`, `_summary_from`, `REPORT_SUMMARY_FIELDS` run before editing.

## Impact analysis (GitNexus, worktree index, 2026-10-25)

| Symbol | Risk | Callers / note |
|---|---|---|
| `REPORT_SUMMARY_FIELDS` | UNKNOWN (module const) | Text search: used only by `REPORT_SUMMARY` and `report_summaries_query` in `queries.py`, which only `report_tools.load_report_summary(ies)` call. Every consumer (tools, guides, recent raids) goes through that one loader. |
| `_summary_from` | LOW | The two `load` closures in `load_report_summary(ies)` |
| `FightSummary` | not indexed (pydantic) | Text search: built only in `_summary_from`; new fields are optional with defaults, so old readers and cached values still validate |
| `keys.report_summary` | not indexed | Tests call `keys.report_summary(...)`, none pins the literal key; 020 does not touch it. One-time cold cache for summaries in shared Redis (they refill on demand) |
| `_refresh` | HIGH (4 processes, all the 013 refresh flow itself: `run_recent_raid_refresh`, `maybe_start_refresh`, API list and refresh) | Edited by this feature on purpose; covered by `test_recent_raids.py` plus new M+ tests; the raid path is unchanged and asserted by the existing tests |
| `repository.list_recent_raids` | LOW | Single caller `api.recent_raids.list_recent_raids`; signature unchanged |

WCL cost: the four added fields are scalars on fights already requested. WCL charges query points per object fetched, not per scalar field, so the summary query's cost is unchanged for every caller. Payload grows by roughly 4 small numbers per fight.
