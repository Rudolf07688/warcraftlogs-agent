# Tasks: Participant Resolution

**Input**: `specs/030-participant-resolution/` (plan.md, spec.md, research.md, data-model.md, contracts/)
**Verify**: `uv run --extra test pytest -q` (backend), `npm run build` in `frontend/`.
**Ordering rule**: tasks touching `wcl_agent/agent.py`, `backend/app/api/ws.py`, `backend/tests/test_prompt_contract.py` are LAST (phase 5) and wait for 029 to merge. Run GitNexus `impact` before each edit of an existing symbol.
**Hold**: no implementation until the scrum master sends "GO implement 030".

## Phase 1: Setup

- [X] T001 Run GitNexus impact (upstream) on `_report_fields`, `build_preamble`, `_recent_block` and `REPORT_SCOPED_TOOLS`; re-run on the live worktree and compare with the plan's Impact section (`build_preamble` is HIGH: kwargs stay optional and output stays byte-identical)
- [X] T002 Add inferred `playerDetails` fake builders (raid of 40 with pets, M+ of 5, missing realm, spec swapper) to `backend/tests/test_participants_tool.py`, labelled Inferred, using the shape in `backend/tests/test_guide_pipeline_datasheet.py`

## Phase 2: User Story 1 - participants with class and role (P1)

**Goal**: `get_report_participants` returns compact rows. **Test**: `pytest backend/tests/test_participants_tool.py`.

- [X] T003 [US1] Tests in `backend/tests/test_participants_tool.py`: raid (40 players, pets/NPCs excluded, at most 6,000 chars), M+ (5 players, at most 1,500, rows at most 120), realm null kept, spec swapper one row with most-played spec and matching role, missing keys tolerated, empty or unknown report gives the standard error, request failure gives the error shape, no `_truncated`
- [X] T004 [US1] Implement `participants_from_player_details` and `get_report_participants` in `wcl_agent/tools/participants.py` using `_report_fields`, `_fight_ids`, `with_envelope`, `roster_snapshot()` (no new query, no cache family)
- [X] T005 [US1] Add `get_report_participants` to `REPORT_SCOPED_TOOLS` in `backend/app/services/raids.py`, with a test in `backend/tests/test_participants_tool.py` that a successful call tracks the raid
- [X] T006 [P] [US1] Add tool label to `frontend/src/toolLabels.ts` and `frontend/src/lib/spells.ts` (both already list `get_report_player_details`; add the new tool next to it); run `npm run build` in `frontend/`

## Phase 3: User Story 3 - filters on rows (P2)

- [X] T007 [US3] Test in `backend/tests/test_participants_tool.py` on faked data: "except the shaman" and "only the healers" applied to the returned rows give the expected sets (proves rows carry class and role; filtering stays model-side, no filter args)

## Phase 4: User Story 2 - run candidates in the preamble (P1)

**Goal**: Barnaby has the candidates. **Test**: `pytest backend/tests/test_profile_context.py`.

- [X] T008 [US2] Tests in `backend/tests/test_profile_context.py`: report codes on the Raids line; "Recent M+ runs" and "Recent raids" lines (at most 5 each, newest first, trimmed to about 600 chars, with report code and fight id); several candidates listed; nothing stored leaves output byte-identical
- [X] T009 [US2] Implement the two lines and the report codes in `backend/app/services/profile_context.py` (`_recent_block`, `build_preamble` gets optional kwargs defaulting empty)

## Phase 5: AFTER 029 MERGES ONLY (do not start before the scrum master says so; then rebase onto the sprint tip)

- [X] T010 [US2] `backend/app/api/ws.py` `_build_turn_preamble`: read `repo.list_recent_raids` and `repo.list_recent_mplus_runs` (limit 5) and pass them to `build_preamble`; run impact first
- [X] T011 [US1] Register `get_report_participants` in `wcl_agent/agent.py` in 029's `TOOL_GROUPS`/`TOOLS` (not backend `extra_groups`)
- [X] T012 [US2] Add the `<RUN_RESOLUTION>` guidance to `wcl_agent/agent.py` (D5 order, kind mapping, one-candidate confirm, at most 5 candidates, filter on rows)
- [X] T013 [US2] Clause test in `backend/tests/test_prompt_contract.py` for the D5 guidance (deterministic check for SC-003)

## Phase 6: Hand-off

- [X] T014 Full backend test run, frontend build, `node /home/rudolf/dev/warcraftlogs-agent/.gitnexus/run.cjs analyze --force` then `detect-changes --scope all --repo .`, ownership check against the grant, restore `CLAUDE.md` and `.specify/feature.json`, then report to the scrum master

## Dependencies

T001, T002 first. T003 before T004. T005, T006 after T004. T007 after T004. T008 before T009. Phase 4 is independent of phases 2-3 (so phases 2-4 can be done in any order). Phase 5 only after 029 merges: T010 after T009; T013 after T012.

## Parallel

T006 with T005/T007; T008-T009 with T003-T005 (different files). No sub-agents proposed: the feature is small, one developer is simplest.

## Strategy

MVP is phase 2 (tool usable without preamble). Then phase 4, then phase 5 after the rebase.
