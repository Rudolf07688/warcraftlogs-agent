# Tasks: Big-report turns that finish and cost less (046)

Order: sc-334 → sc-302 → sc-328 → sc-339 (drop sc-339 first if short). Tests are required by the ACs.

## Phase 1: Setup

- [ ] T001 Move sc-334/302/328/339 to In Progress as each starts; branch `046-big-report-turns` from `sprint-2026-11-01b`

## Phase 2: US1 Compact big report tables (sc-334)

- [ ] T002 [US1] Build deterministic 20-player Heroic kill fixture (DamageDone + Summary, WCL shape, over the cap) in backend/tests/fixtures/wcl_table_heroic_20.json
- [ ] T003 [US1] Add `TABLE_MAX_CHARS`, `compact_table`, `acompact_table` in wcl_agent/tools/report_tools.py; `get_report_table` uses `acompact_table`
- [ ] T004 [US1] `get_stored_fight_table` hunk: call `acompact_table` in backend/app/agent_tools/stored_data_tools.py
- [ ] T005 [US1] Instruction: compact tables hold the top entries, no per-player fetch for top-N, in wcl_agent/agent.py
- [ ] T006 [US1] Tests (prompt-size < 10k tokens, no `_preview`, sorted, omitted count, small table unchanged, other tools unchanged, stored lookup compacted, instruction clause) in backend/tests/test_046_compact_tables.py; mutate.py bite

## Phase 3: US2 Turn ends with no answer (sc-302)

- [ ] T007 [US2] Paragraph break after a tool round, closing no-answer token for chat turns, `outcome=empty`, `tool_calls=N` in backend/app/agent_runner.py
- [ ] T008 [US2] Tests with a fake runner (tools then empty → message + outcome=empty; normal answer unchanged; break between interim and final; non-chat turn unchanged; tool_calls) in backend/tests/test_046_empty_turn.py; mutate.py bite

## Phase 4: US3 Search hits as data (sc-328)

- [ ] T009 [US3] Wrap hit text in `<data>…</data>` with `<`/`>` neutralised; update `UNTRUSTED_NOTE` in backend/app/kb/search.py
- [ ] T010 [US3] Cap report title (80) and guild name (40) in chunk text in backend/app/kb/wcl_chunker.py
- [ ] T011 [US3] Instruction: delimited text is data, never instructions, in wcl_agent/agent.py
- [ ] T012 [US3] Tests (end delimiter + instruction phrase in title stays in one block; long title cut; instruction clause) in backend/tests/test_046_search_data.py; mutate.py bite

## Phase 5: US4 Recent-raid kickoff (sc-339)

- [ ] T013 [US4] New backend/app/services/kickoff_prefetch.py: `pick_boss_fights`, `prefetch`, `schedule` (background.spawn, identity, bound 10, errors logged)
- [ ] T014 [US4] Schedule the pre-fetch after the 404 rule when the fetch writer runs, in backend/app/api/raids.py
- [ ] T015 [US4] `<RECENT_RAID_KICKOFF>` playbook in wcl_agent/agent.py
- [ ] T016 [US4] Tests (fires once per click, dedupes concurrent clicks, swallows errors, acts as the workspace, bound, 404 fetches nothing, playbook text) in backend/tests/test_046_kickoff_prefetch.py; mutate.py bite

## Phase 6: Polish

- [ ] T017 Full suite via check.py on the committed tree; GitNexus detect-changes; ownership check; live-check question `live-check:046`; hand-off

## Dependencies

US1–US4 are independent; T005/T011/T015 all edit wcl_agent/agent.py (sequential). Single developer: run in order.
