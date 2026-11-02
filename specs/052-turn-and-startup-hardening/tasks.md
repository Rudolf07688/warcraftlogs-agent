# Tasks: Turn and startup hardening

**Input**: spec.md, plan.md, research.md, contracts/interfaces.md. Tests first in every phase
(the brief asks for edge-case tests before the state-machine code). One commit per story.

## Phase 1: Setup

- [X] T001 Branch `052-turn-and-startup-hardening` off `sprint-2026-11-02`; spec, plan, tasks in specs/052-turn-and-startup-hardening/

## Phase 2: US1 Breaker counts workspaces, not bursts (sc-355)

- [X] T002 [US1] Tests in backend/tests/test_052_breaker.py: one turn's parallel timeouts keep it closed and the turn stops probing; two turns' timeouts open it; mostly slow store with an odd success opens it; healthy store with sporadic timeouts stays closed; connection error opens at once; half-open trial unchanged; is_open side-effect free; window expiry
- [X] T003 [US1] ~~`current_turn_key()` in wcl_agent/cache/cache.py~~ Superseded by the P7 rework (b7b66ae): the breaker keys on the workspace (tenant id), no turn key exists
- [X] T004 [US1] Sliding-window Breaker + per-workspace skip (P7 rework; was per turn) + `is_open()` in backend/app/services/raw_fetch_reads.py
- [X] T005 [US1] Update the 047 "N in a row" tests that encode the old rule in backend/tests/test_047_breaker.py; existing trial tests unchanged
- [X] T006 [US1] Commit

## Phase 3: US2 Per-operation probe counters (sc-332)

- [X] T007 [US2] Tests in backend/tests/test_052_store_ops.py: record and summarize per op; endpoint shape
- [X] T008 [US2] `record_store(outcome, op)` + `summarize_local` by_operation in wcl_agent/cache/cache.py; pass the op from backend/app/services/raw_fetch_reads.py
- [X] T009 [US2] `StoreStats.by_operation` in backend/app/schemas.py (grant board #15)
- [X] T010 [US2] Commit

## Phase 4: US3 Investigate limit and careful pre-fetch (sc-352)

- [X] T011 [US3] Tests in backend/tests/test_052_investigate.py: 429 over the limit (before 404); no pre-fetch while the breaker is open (state unchanged); failing commit schedules nothing
- [X] T012 [US3] `wcl_investigate_per_minute` in backend/app/config.py and .env.example; `investigate_limiter` in backend/app/auth/rate_limit.py
- [X] T013 [US3] Limit + commit-then-schedule in backend/app/api/raids.py (investigate_raid hunk only); breaker gate in backend/app/services/kickoff_prefetch.py
- [X] T014 [US3] Commit

## Phase 5: US4 Turn accounting survives failures (sc-357)

- [X] T015 [US4] Tests in backend/tests/test_052_turn_accounting.py: preamble failure and setup-commit failure abandon the turn uncounted and clear the actor; next turn counts only itself; unshareable joiner with a local reload is local; final save failure sends the error frame and ends the turn
- [X] T016 [US4] `abandon_turn()` and joiner order in wcl_agent/cache/cache.py
- [X] T017 [US4] Setup wrap and save handling in backend/app/api/ws.py
- [X] T018 [US4] Commit

## Phase 6: US5 No silent start on the dev secret (sc-356)

- [X] T019 [US5] Tests in backend/tests/test_052_startup_secrets.py: refuse on non-local site; local hosts start; warning names each default without values
- [X] T020 [US5] `insecure_defaults` / `check_startup_secrets` in backend/app/config.py; call at lifespan start in backend/app/main.py; note in .env.example
- [X] T021 [US5] Commit

## Phase 7: US6 One set_config, cached proxies (sc-270)

- [X] T022 [US6] Tests in backend/tests/test_052_scope_and_proxies.py: one execute on a postgres-dialect session; parse once per value
- [X] T023 [US6] backend/app/tenancy/context.py one statement; backend/app/config.py cached parse; backend/app/auth/rate_limit.py tuple type
- [X] T024 [US6] Commit; full suite with `--pg` later covers RLS

## Phase 8: US7 Both-limited deadline (sc-297)

- [X] T025 [US7] Test in backend/tests/test_052_retry_deadline.py with a fake clock where requests take time; sc-268 `sleeps` fixture advances the fake clock in backend/tests/test_model_fallback.py
- [X] T026 [US7] Deadline in wcl_agent/llm/model_retry.py
- [X] T027 [US7] Commit

## Phase 9: Polish

- [X] T028 Mutation-check each new guard with mutate.py; detect-changes; full `check.py run --pg`; hand-off

## Dependencies

Stories are independent; US3's breaker gate uses US1's `is_open()`. Order = brief order.

## Phase 10: QA fix round 2026-11-02 (branch qa-fix-tomas)

- [X] T029 BUG-001: `pick_boss_fights` from `report_tools.boss_summary` (no key runs); tests in backend/tests/test_052_qa_prefetch.py
- [X] T030 PERF-003: `report_tools.load_report_table` (raw whole-raid table, the query `get_report_table` sends); the pre-fetch warms raw tables; test that the turn reads them from the store
- [X] T031 BUG-003: `Breaker.skips(workspace)`; `schedule()` skips while the store skips the workspace
- [X] T032 ws.py: the turn's temp folder is created inside the guarded setup (test_052_turn_accounting.py)
- [X] T033 BUG-004: frontend/src/lib/investigateError.ts, a 429 names the limit
- [X] T034 SPEC-001/002/005/008: spec, research, data model, contract, tasks aligned with the workspace breaker, `store_by_operation` + "custom" and the weak-secret rule
