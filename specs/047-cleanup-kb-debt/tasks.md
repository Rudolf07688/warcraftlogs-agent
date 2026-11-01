# Tasks: Clean-up and KB debt

**Input**: spec.md, plan.md, research.md, data-model.md, quickstart.md
**Tests**: required by every story's ACs. One commit per story.

## Phase 1: US1 sc-336 Tests never read the real .env (P1)

- [X] T001 [US1] `backend/app/config.py`: `WCL_LOAD_DOTENV` switch gates `load_dotenv()` and `Settings.env_file`
- [X] T002 [US1] `backend/tests/conftest.py`: set `WCL_LOAD_DOTENV=0` before any app import
- [X] T003 [US1] `backend/tests/test_047_no_dotenv.py`: sentinel `.env` guard (settings, os.environ, subprocess with and without the switch)
- [X] T004 [US1] Prove the tests bite (`mutate.py`); fake `.env` run gives the same counts (`check.py --allow-env`); commit

## Phase 2: US2 sc-322 Private report stays gone (P1)

- [X] T005 [US2] `backend/app/services/fetch_persistence.py`: bury the codes a summary finds private
- [X] T006 [US2] `backend/tests/test_047_private_tombstone.py`: the race (table requested before, written after the summary) and the grant can't serve
- [X] T007 [US2] `specs/045-local-data-reads/spec.md` FR-010 as built; mutate; commit

## Phase 3: US3 sc-323 Breaker counts timeouts (P2)

- [X] T008 [US3] `backend/app/services/raw_fetch_reads.py`: consecutive timeouts, connection errors open at once
- [X] T009 [US3] `backend/tests/test_047_breaker.py`: one timeout closed, 3 open, connection error opens, success resets; mutate; commit

## Phase 4: US4 sc-324 Strict, bounded lookup (P2)

- [X] T010 [US4] Migration `backend/migrations/versions/0020_raw_fetch_summary_index.py` + index on `RawFetch` in `backend/app/db/models.py`
- [X] T011 [US4] `backend/app/repositories/raw_fetches.py`: `list_visible_summaries` verifies our fixed query key + exact codes, projects fields in SQL, statement timeout
- [X] T012 [US4] `backend/app/agent_tools/stored_data_tools.py`: caller passes the timeout (outside the `get_stored_fight_table` hunk)
- [X] T013 [US4] `backend/tests/test_047_stored_reports.py`: forged op / inexact codes never returned (SQLite); Postgres: index plan + projection bytes bounded
- [X] T014 [US4] guard test unchanged; mutate; `check.py --pg`; commit

## Phase 5: US5 sc-326 Local-answer rate (P3)

- [X] T015 [US5] `wcl_agent/cache/cache.py`: `_Load.external`, joiners and lock waiters note external
- [X] T016 [US5] `backend/app/api/ws.py`: open the turn before the preamble
- [X] T017 [US5] `backend/tests/test_047_local_rate.py`: joiner counted, lock waiter counted, preamble call counted; mutate; commit

## Phase 6: US6 sc-255 Message numbering race (P3)

- [X] T018 [US6] `backend/app/db/repository.py`: lock the conversation row in `_next_seq`
- [X] T019 [US6] `backend/tests/test_047_message_seq_pg.py`: two concurrent sessions on Postgres; mutate against old code; commit

## Phase 7: Hand-off

- [ ] T020 detect-changes, ownership check, rebase on sprint tip, `check.py run --pg ansel` on the committed head
- [ ] T021 Stories to Under Review, board handoff, `live-check:047` question
