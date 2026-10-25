# Tasks: Welcome Chat with Recent Raids and Mythic+ Runs

**Input**: `/home/rudolf/dev/wcl-worktrees/dev-b/specs/022-welcome-mplus/` (plan.md, spec.md, data-model.md, contracts/, research.md)
Tests are requested (spec SC-007). WCL responses are faked; no live calls. Tasks marked **[after 020]** wait for 020's merge and the scrum master's hand-over.

## Phase 1: Setup

- [ ] T001 Run GitNexus `impact` upstream on `fetch_report_details`, `upsert_listed_reports`, `RecentRaidsResponse`, `investigate_raid` and note the risk in the plan (`specs/022-welcome-mplus/plan.md`)

## Phase 2: Foundational (blocks all stories)

- [ ] T002 Add keystone fields `startTime keystoneLevel keystoneBonus keystoneTime` to the fights selection of `REPORT_SUMMARY_FIELDS` in `wcl_agent/client/queries.py`
- [ ] T003 Add optional `start_time_ms`, `keystone_level`, `keystone_bonus`, `keystone_time_ms` to `FightSummary` in `wcl_agent/cache/cache_models.py`
- [ ] T004 Map the new fields in `_summary_from` in `wcl_agent/tools/report_tools.py`
- [ ] T005 Bump the `report_summary` key from `v1` to `v2` in `wcl_agent/cache/cache.py`; fix `backend/tests/test_wcl_cache.py` / `test_cache_families.py` only if they pin the literal
- [ ] T006 [after 020] Add settings `recent_raids_shown = 6` and `recent_mplus_shown = 6` in `backend/app/config.py`

## Phase 3: User Story 1 - 6 latest raids (P1)

**Independent test**: with 8 stored raids the GET returns the 6 newest, newest first.

- [ ] T007 [US1] Test in `backend/tests/test_recent_raids.py`: more than 6 raids returns 6 newest first; fewer returns all; replace the `recent_raids_limit == 20` assertion so it still pins the listing depth and add one for `recent_raids_shown == 6`
- [ ] T008 [US1] [after 020] Use `settings.recent_raids_shown` for the display limit in `list_recent_raids` of `backend/app/api/recent_raids.py` (listing depth `recent_raids_limit` unchanged)

## Phase 4: User Story 2 - recent Mythic+ runs (P1)

**Independent test**: faked WCL summaries with keystone fights produce stored runs; GET returns at most 6, newest first, deduped, none when absent.

- [ ] T009 [US2] [after 020] Append `RecentMplusRun` and `RecentMplusRunCharacter` to `backend/app/db/models.py` per data-model.md
- [ ] T010 [US2] Write migration `backend/migrations/versions/0014_recent_mplus_runs.py` (down_revision `0013_raw_fetches`, tables, unique key, indexes, RLS enable + tenant policy and grants like 0010)
- [ ] T011 [P] [US2] Add `MplusRun` dataclass to `backend/app/services/recent_raid_types.py`
- [ ] T012 [US2] In `backend/app/services/recent_raids.py` add `extract_mplus_runs(summary)` (completed = `kill is True` and `keystone_level > 0`; timed = `keystone_bonus >= 1`; dungeon = fight name, else zone name; start = report start + fight start) and extend `_refresh` to fetch details for the newest `MPLUS_REPORT_BATCH = 10` non-raid reports needing details and store their runs with character links
- [ ] T013 [US2] In `backend/app/db/repository.py` add `upsert_mplus_runs` (`ON CONFLICT DO NOTHING`, links only to live characters) and `list_recent_mplus_runs` (two queries mirroring `list_recent_raids`, only runs linked to an existing own character)
- [ ] T014 [P] [US2] Add `RecentMplusRunOut` and `mplus_runs` on `RecentRaidsResponse` in `backend/app/schemas.py` (small edit; 021 may need this file next)
- [ ] T015 [US2] Return `mplus_runs` (limit `recent_mplus_shown`) from `GET /api/recent-raids` in `backend/app/api/recent_raids.py`
- [ ] T016 [US2] Tests in new `backend/tests/test_recent_mplus.py`: extraction (timed, depleted listed not timed, abandoned dropped, several keys in one report, fallback dungeon name), 6-cap and ordering, no-M+ case returns an empty list, dedup across characters, run removed when its only character is deleted, tenant privacy, refresh failure leaves stored runs
- [ ] T017 [US2] Types and client in `frontend/src/types.ts` (`RecentMplusRun`, `mplus_runs`) and the WelcomePanel section: search the shadcn MCP registry, reuse `Item`/`Badge` as `RaidCard` does, add `MplusCard` and the "Your recent Mythic+ runs" section shown only when non-empty in `frontend/src/components/WelcomePanel.tsx`; run the MCP audit checklist

## Phase 5: User Story 3 - click a run to review it (P1)

**Independent test**: POST investigate for a stored run returns a conversation titled `M+ <dungeon> +<level>` with the kickoff prompt; unknown run is 404.

- [ ] T018 [US3] Add `mplus_kickoff_prompt_for` and `POST /api/recent-raids/mplus/{report_code}/{fight_id}/investigate` (repo `get_recent_mplus_run` added in `backend/app/db/repository.py`) to `backend/app/api/recent_raids.py`, creating the conversation with the explicit title
- [ ] T019 [US3] Tests in `backend/tests/test_recent_mplus.py`: endpoint 201 with explicit title (`title_source == "explicit"`), 404 for another tenant's or unknown run, invalid model 400, kickoff prompt key phrases pinned (timer result, biggest time loss per segment, deaths, interrupt coverage, one headline improvement, segment-level scope)
- [ ] T020 [US3] Add `investigateMplusRun` in `frontend/src/api/restClient.ts` and `handleInvestigateMplus` in `frontend/src/App.tsx` (mirrors `handleInvestigateRaid`, no raid refresh), wire `onInvestigateMplus` into `WelcomePanel` (`frontend/src/components/WelcomePanel.tsx`)

## Phase 6: User Story 4 - never wait on Warcraft Logs (P2)

- [ ] T021 [US4] Test in `backend/tests/test_recent_mplus.py`: GET returns stored runs without any WCL call, a failing M+ detail fetch keeps stored raids and runs and records the failed outcome, and the M+ fetch runs inside the background lane
- [ ] T022 [US4] Verify `_refresh` ordering keeps the raid path unchanged when the M+ step raises (no partial raid loss); adjust `backend/app/services/recent_raids.py` if the test shows otherwise

## Phase 7: Polish

- [ ] T023 Run `uv run --extra test pytest -q` and `npm run build` in `frontend/`; fix regressions
- [ ] T024 Index the worktree and run `detect-changes --scope all`; check `git diff --name-only 6aa641d...HEAD` lists only owned files; restore `.specify/feature.json` and `CLAUDE.md`
- [ ] T025 Live check on app 18019 / Postgres 15419 / Redis 16319 if M+ test data is available; otherwise record it as an open hand-off item in `specs/022-welcome-mplus/quickstart.md`

## Dependencies and order

Phase 2 before all stories. T006 and T009 wait for 020 (everything else can start now). T010 needs T009's column list only. US1 (T007-T008) depends on T006. US2: T011 and T014 parallel; T012 needs T002-T004, T009, T011, T013; T015 needs T013, T014; T017 needs T014. US3 needs US2 data (T013, T015). T020 needs T017 and T018.

Suggested order before 020 merges: T001-T005, T010, T011, T014, T017 (types/UI against the contract), T013 (written, run after T009). MVP: US1 + US2 + US3 (all P1).

## Sub-agent split (optional)

Frontend `T017` and `T020` (`frontend/src/components/WelcomePanel.tsx`, `frontend/src/types.ts`, `frontend/src/api/restClient.ts`, `frontend/src/App.tsx`) can go to one sonnet/medium sub-agent once T014's contract is fixed; everything backend stays with me.
