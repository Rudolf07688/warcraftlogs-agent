# Tasks: Report fights and kickoff (050)

One commit per story, in the brief's order. Tests use fixtures only.

## Phase 1: Setup

- [X] T001 Impact analysis on every edited symbol (GitNexus + text search for UNKNOWN); post HIGH/CRITICAL

## Phase 2: US4 one difficulty map (sc-330) — done first, US1 uses it

- [X] T002 [US4] Add `DIFFICULTY_NAMES` to wcl_agent/game/constants.py; remove `_DIFFICULTY_NAMES` in wcl_agent/tools/tools.py and `_DIFFICULTY` in backend/app/services/profile_context.py; import it there and in backend/app/services/name_resolver.py
- [X] T003 [US4] Test: one definition (grep-style guard) in backend/tests/test_050_report_fights.py; existing tests pass unchanged

## Phase 3: US1 last boss kill (sc-365)

- [X] T004 [US1] `boss_summary(summary)` and `last_kill(summary)` in wcl_agent/tools/report_tools.py (start time, fight id fallback, keystone runs excluded)
- [X] T005 [US1] `get_report_fights` returns `last_kill`, `bosses` (outside the capped list), `keystoneLevel` on key runs
- [X] T006 [US1] Instruction clause in wcl_agent/agent.py `<CONTEXT_RESOLUTION>`
- [X] T007 [US1] Tests: multi-kill fixture with trash, M+ keys, wipes, out-of-id-order kills, over-cap list; null case; instruction clause; mutate.py bites

## Phase 4: US2 kickoff cost (sc-358)

- [X] T008 [US2] `overview` flag on `get_report_table` + projection in wcl_agent/tools/report_tools.py
- [X] T009 [US2] Kickoff playbook only for kickoff turns in `build_instruction`; `RAID_KICKOFF_OPENING`; backend/app/api/raids.py `kickoff_prompt_for` uses it; playbook asks for overview tables from `bosses`
- [X] T010 [US2] Move the playbook test out of backend/tests/test_046_kickoff_prefetch.py into backend/tests/test_050_kickoff_overview.py; prompt-size regression test (before/after printed)

## Phase 5: US3 untrusted text (sc-351)

- [X] T011 [US3] Neutraliser (unescape + NFKC fixed point, look-alikes to parentheses) and label/section data blocks in backend/app/kb/search.py; UNTRUSTED_NOTE names them
- [X] T012 [US3] String caps in report tools (title 80, names 60, table strings 60)
- [X] T013 [US3] Update backend/tests/test_046_search_data.py pins; new backend/tests/test_050_untrusted_text.py
- [X] T014 [US3] Update specs/044-kb-search/contracts/search-knowledge.md

## Phase 6: Polish

- [X] T015 detect-changes, footprint check, full check.py run with receipt; board handoff; Shortcut Under Review
