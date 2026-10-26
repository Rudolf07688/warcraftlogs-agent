# Checkpoint: 029 capability summary + profile proposal tools

Resume point for a fresh context. Agent `dev-a-029` (developer); scrum master `scrum-master`;
peer `dev-b-030`.

## Where things stand (2026-10-26)

- Worktree `/home/rudolf/dev/wcl-worktrees/dev-a`, branch `029-agent-profile-proposals`, base
  `1da8bca` (sprint-2026-10-26; the sprint tip moved to 139a0e7, artefacts only, so no rebase).
- Commits: 5555799 spec · c97d4b6 D13 clarification · c8690dd plan docs · (next) tasks + checkpoint.
- Shortcut: sc-204 and sc-205 are **In Progress** (iteration 161). Leave them there; the scrum
  master says when they go to Under Review.
- Gates:
  - spec **signed off**;
  - D13 answered (app-facts line, existing features only);
  - plan gate package sent, waiting for the ownership grant;
  - tasks gate (+ sub-agent split) next.

  **No code until the scrum master sends "GO implement 029".**
- `.specify/feature.json` is modified locally (points at this spec) and is never committed.
  Restore it and `CLAUDE.md` before each commit (`git checkout -- CLAUDE.md .specify/feature.json`),
  or commit only explicit paths.

## Baseline (AC 8)

`uv run --extra test pytest -q` on 1da8bca (code-identical to cf370e8): **1066 passed,
3 skipped, 1 deselected** (72 s).

## Decisions (binding)

- Design C1–C14 and `#proposal-contract`; sprint decisions D4–D11; D13 (app-facts line: Profile
  page, welcome-screen recent raids / Mythic+ runs, PDF download, boss checkboxes, model
  picker; no chat filter, no Raids page).
- Research R1–R10 refine the design. The main points:
  1. `ProfileChangeIn` strings have no length limits, so the checks are per item.
  2. The no-tool-name check applies only to the `<TOOLS>` section.
  3. The realm regex allows parentheses.
  4. The validator simulates the profile in item order.
  5. The friend-limit message carries no number.
  6. Proposal row helpers live in `backend/app/repositories/profile_proposals.py`.
  7. ws.py changes 2 lines: the import and the `.set`.
- Migration: revision `0016_profile_proposals`, down_revision `"0015_rescan_mplus_runs"`.
- Ports for any throwaway service: app 18029, Postgres 15429, Redis 16329. Use `docker run`,
  never `docker compose`, and never read the owner's `.env`.

## Files owned (pending the grant; see plan.md "exact file list", 23 rows)

wcl_agent/{capabilities.py (N), agent.py, tools/tools.py, tools/report_tools.py};
backend/app/{agent_runner.py, agent_tools/__init__.py (N), agent_tools/profile_tools.py (N),
services/profile_service.py (N), services/profile_proposals.py (N),
repositories/profile_proposals.py (N), api/profile.py, api/ws.py (2 lines), tenancy/context.py,
schemas.py, db/models.py, db/repository.py};
backend/migrations/versions/0016_profile_proposals.py (N);
frontend/src/components/profile/CharactersTab.tsx;
backend/tests/{test_capabilities.py (N), test_profile_tools.py (N), test_profile_proposals.py (N),
test_prompt_contract.py}; specs/029-agent-profile-proposals/**.
`backend/tests/test_profile.py` must stay unchanged.

## Proposed sub-agent split (awaiting approval)

S1 = US1 (T009–T015), sonnet/high, exclusive files wcl_agent/capabilities.py,
wcl_agent/agent.py, wcl_agent/tools/tools.py, wcl_agent/tools/report_tools.py,
backend/tests/test_capabilities.py, backend/tests/test_prompt_contract.py. Everything else is
mine. Sub-agents don't commit.

## Grant (2026-10-26)

The plan was approved at c8690dd. Everything is granted, including the 2 ws.py lines and
migration 0016, **except** `wcl_agent/agent.py`, `backend/app/api/ws.py` and
`backend/tests/test_prompt_contract.py`. Those take effect after 030 merges: wait for
"030 MERGED, rebase", rebase onto the sprint tip, and only then edit them (T000). S1 also
starts only after that. Shared-runner fail-closed tests were added to T027 (SM note).

## Implementation progress (after GO, 2026-10-26)

Commits:
- afedf60: phases 2 and 4 plus S1's renderer.
- 44de352: service and tool.
- (next): RLS test tightening and this checkpoint.

| Area | Tasks | Status |
|---|---|---|
| Foundational | T001–T008 | done |
| US4 | T016–T020 | done (`test_profile.py` unchanged and green) |
| US2 | T021, T022, T024, T026 | done |
| US3 | T029–T033 | done |
| US1, part 1 | T009, part of T013 (S1: `capabilities.py` + renderer tests, 15 green) | done |

Full suite after 44de352: 1126 passed, 6 skipped (3 of them Postgres-only), 1 deselected.

**Open** (all after "030 MERGED, rebase"):
- T010–T012, the rest of T013, T014, T015 (S1: agent.py, docstrings, prompt contract);
- T023 (ws.py, 2 lines);
- T025 (`_get_runner`);
- T027 backend-agent registration test, T028 scripted turn;
- T034–T038.

**T033 Postgres run (2026-10-26)**: `docker run postgres:17` on port 15429 with dummy
credentials. Steps: `alembic upgrade 0002_auth_tenancy` → `bootstrap_admin` (dummy env) →
`upgrade head` (… → 0016_profile_proposals) → `downgrade -1` (→ 0015; the table and policy
are gone) → `upgrade head` (0016).

After the second upgrade:
- `relrowsecurity` and `relforcerowsecurity` are both `t`;
- the policy `tenant_isolation` uses `tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`;
- `wcl_app` has SELECT/INSERT/UPDATE/DELETE.

`TEST_DATABASE_URL=…wcl_app…:15429` ran `test_rls.py` (3) plus the 3 `profile_proposals`
RLS tests: 6 passed. The insert test asserts the error is "row-level security". The
container is stopped.

## Implementation complete (2026-10-26)

- Rebased onto sprint-2026-10-26 @ 1685bd5 (030 merged).
- S1 did agent.py (TOOL_GROUPS with get_report_participants in "Report deep-dive"; the
  hand-written list, including 030's temporary line, removed; <RUN_RESOLUTION> kept), the
  docstrings and test_prompt_contract.py (4 tests).
- I did ws.py (2 lines), the _get_runner registration, D15's `backend/app/db/timestamps.py`
  (`as_utc`), the backend-runner registration test and the offline scripted agent turn.
- Full suite: **1152 passed, 6 skipped, 1 deselected**, no failures. `npm run build` is green.
- Backend Gemini `<TOOLS>` summary (largest set): 3,267 chars; longest tool line 144.
- GitNexus `analyze --force` + `detect-changes --scope all`: 13 files, risk "critical",
  driven by `build_agent`/`_get_runner` (the HIGH risk accepted at the plan gate). No
  unexpected symbols.
- Ownership: every changed path is on the grant (plus D15's timestamps.py).
  `.specify/feature.json` is never committed. `test_profile.py` is unchanged.

## Open questions

- Waiting for the scrum master: confirmation of S1 at the tasks gate, "030 MERGED, rebase",
  and "GO implement 029".
- D13 wording: the SM's resync listed a "Raids page", but the base has none (routes are
  /app, /profile, /admin/users). The line names "recent raids and Mythic+ runs on the welcome
  screen" instead (flagged to the SM).

## Where implementation starts (after GO)

tasks.md T001 → T002 → Phase 2 (T003–T008), launching S1 on Phase 3 in parallel at the same
time, then Phase 4 (T016–T020), Phase 5 (T021–T028), Phase 6 (T029–T033) and Phase 7.
Run GitNexus `impact` before editing each existing symbol (results are in plan.md; HIGH:
`build_agent`, `_get_runner`).
