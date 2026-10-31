# Tasks: Profile write-path hardening (036)

**Input**: plan.md, spec.md, research.md, data-model.md, contracts/service-api.md, quickstart.md
**Tests**: required by the PO acceptance criteria (one or more per AC).

## Phase 1: Setup

- [ ] T001 Baseline: run `uv run --extra test pytest -q` and `cd frontend && npm test`; record counts in specs/036-profile-write-hardening/checkpoint.md

## Phase 2: US1 sc-221, profile write path vs injected log text (P1)

**Independent test**: preamble, capability summary, validator and card tests below.

- [ ] T002 [US1] Tests: hostile `RecentRaid.title` and title-fallback `TrackedRaid.label` absent from `build_preamble`, zone/date/code present, in backend/tests/test_profile_context.py
- [ ] T003 [US1] `_raid_run_ident` zone only; `_recent_block` uses a tracked raid's label only when guild/zone/date exist, in backend/app/services/profile_context.py
- [ ] T004 [US1] Test + rule: own-message request rule in `_CAN_CHANGE`, in wcl_agent/capabilities.py and backend/tests/test_capabilities*.py
- [ ] T005 [US1] Tests: class/spec mapped to roster (canonical, class-only, unknown → null, 100-char input) for valid and skipped items; realm form (real realms pass, prose and > 24 chars fail) in backend/tests/test_profile_proposals.py
- [ ] T006 [US1] `_roster_class_spec` via `resolve_spec`, tightened `_REALM`, used in `_validate` and `_skipped`, in backend/app/services/profile_proposals.py
- [ ] T007 [US1] Test + change: identity-refused rows show target and reason only (no name, realm, spec) in frontend/src/components/ProposalCard.tsx and ProposalCard.test.tsx
- [ ] T008 [US1] Update the 029 contract text for the instruction line and realm rule in specs/029-agent-profile-proposals/contracts/

## Phase 3: US2 sc-222, identity reset + user-level RLS (P2)

- [ ] T009 [US2] Tests: identity unset after a turn (success and error) and inside a spawned task, in backend/tests/test_background.py and backend/tests/test_proposal_ws.py
- [ ] T010 [US2] `spawn` in a fresh `contextvars.Context()`, in backend/app/services/background.py
- [ ] T011 [US2] Set identity before the stream, reset its token in `finally`, in backend/app/api/ws.py
- [ ] T012 [US2] Migration backend/migrations/versions/0017_proposal_user_rls.py (down_revision 0016_profile_proposals)
- [ ] T013 [US2] Postgres test: user A can't read/update user B's proposal in one tenant with the app filter omitted, in backend/tests/test_proposal_rls_pg.py

## Phase 4: US3 sc-223, cap race + legacy duplicates (P3)

- [ ] T014 [US3] Test: legacy both-roles duplicate spellings stay two entries (remove own works, friend stays) in backend/tests/test_profile_proposals.py
- [ ] T015 [US3] `_profile` keyed by (identity, target); `_check` and `_validate` updated, in backend/app/services/profile_proposals.py
- [ ] T016 [US3] `lock_profile` + call in `add_character`, in backend/app/db/repository.py
- [ ] T017 [US3] Postgres race test: parallel adds at cap − 1 (REST and two approvals) yield exactly the cap, in backend/tests/test_proposal_race_pg.py

## Phase 5: US4 sc-225, bounded approve, reads, guide fan-out (P3)

- [ ] T018 [US4] Test: count statements for a 1-item and a 30-item approve (each action kind); record before/after in checkpoint.md; in backend/tests/test_profile_proposals.py
- [ ] T019 [US4] `add_characters`, `set_raid_roles`, `delete_characters` in backend/app/db/repository.py
- [ ] T020 [US4] `_apply` lock → load → re-validate → bulk apply, in backend/app/services/profile_proposals.py
- [ ] T021 [US4] Optional `db` on `get_proposal`/`list_proposals`; pass it from backend/app/api/conversations.py and the ws capture transaction in backend/app/api/ws.py; tests that no extra session opens
- [ ] T022 [US4] `schedule_character_guides` with a semaphore of 3 in backend/app/services/guide.py; used by `execute_proposal`; test for the bound in backend/tests/test_guide*.py

## Phase 6: US5 sc-244, docs (P4)

- [ ] T023 [US5] documentation/architecture/agent-frontend.html: proposal frame, two tool rows, counts, design links
- [ ] T024 [US5] documentation/architecture/backend-data-infra.html: RLS tables, profile_proposals (user-level RLS), migrations 0001..0017, friend cap, proposals router
- [ ] T025 [US5] specs/029-agent-profile-proposals/contracts/capability-summary.md line budget; documentation/designs/self-aware-agent/capabilities-and-tools.html `character_id` row

## Phase 7: Polish

- [ ] T026 Full suites green, Postgres tests run (quickstart §2), detect-changes clean, ownership check

## Dependencies

US1 → US2 → US3 → US4 → US5 in brief order. US3's lock is reused by US4's `_apply` (T016 before T020).
Inside a story, tests first. Parallel: T004, T007 alongside T003/T006 (different files).
