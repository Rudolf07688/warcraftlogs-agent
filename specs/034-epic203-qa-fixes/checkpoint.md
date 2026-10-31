# Checkpoint: 034 epic-203 QA fixes (resume point before /speckit-implement)

**Who**: `dev-b-034` (track B). Scrum master `scrum-master`; peer `dev-a-032` (no file overlap).
**Worktree**: `/home/rudolf/dev/wcl-worktrees/dev-b`, branch `034-epic203-qa-fixes`, base
`sprint-2026-10-31` @ `b963463`. Brief: `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-31/briefs/034-epic203-qa-fixes.md`.
**Stories**: sc-241, sc-242, sc-243: In Progress, iteration 254. Never move them to Done; Under
Review only when the scrum master says so.

## Gate status

- Spec signed off (scrum master, 2026-10-31); clarifications Q1–Q3 = A (encoded in spec.md).
- Plan sent with the file list, Constitution Check and GitNexus impact. **Waiting for**: the ownership
  grant (incl. OK on the flagged `ProfileChangeIn` HIGH/CRITICAL), approval of the sub-agent split,
  and **OWNER GO** relayed by the scrum master. No code before all three.

## Decisions (see research.md R1–R9)

- sc-241: keep the tool annotation `list[ProfileChangeIn]` (schema unchanged). ADK 2.10 passes
  failed items as raw dicts (verified). Service parses per item: `_blank` realm → `invalid_realm`,
  region → `invalid_region`, else `model_validate` → `invalid_item`; display row fallback
  `add`/`friend`, strings clipped. `ProfileChangeIn` before-validator lower-cases roles; unknown
  `played_role` → None; unknown `raid_role` → invalid_item. Tool catch-all → plain error.
- sc-242: keyword-only `on_transition(db, proposal)` hook on `execute_proposal`/`cancel_proposal`,
  run inside the `FOR UPDATE` transaction only on `pending → applied|cancelled`. `_decide` drops
  the pre-lock read and saves the follow-up through the hook. `repository.py` not touched.
- sc-243: `turnConvRef` in `App.tsx` (set in `sendText` and on `meta`); `done`/`error` attach
  only when it equals `activeIdRef`; dedupe loose cards by proposal id. Label "Preparing profile
  changes"; spell `GiScrollQuill`/GOLD/"Inscribing the changes".
- Out of scope: the `done` answer still lands in the open chat; the message-seq race across two
  different proposals (the scrum master passes it to the PO); sc-214/219/221/225.

## Files (requested grant)

Edit: `backend/app/schemas.py` (ProfileChangeIn only), `backend/app/services/profile_proposals.py`,
`backend/app/agent_tools/profile_tools.py`, `backend/app/api/proposals.py`, `frontend/src/App.tsx`,
`frontend/src/toolLabels.ts`, `frontend/src/lib/spells.ts`, `backend/tests/test_profile_tools.py`,
`backend/tests/test_profile_proposals.py`, `backend/tests/test_proposal_routes.py`.
Create: `backend/tests/test_proposal_race_pg.py`, `frontend/src/App.test.tsx`, `specs/034-epic203-qa-fixes/**`.
Never commit: `CLAUDE.md`, `.specify/feature.json` (modified locally by speckit; restore before commit).

## Where implementation starts

`tasks.md` T001 (re-index + baseline), then US1 T002–T008 → US2 T009–T013; US3 T014–T018 in
parallel (proposed sub-agent). Postgres for T010/T013: container `wcl-034-pg`, port 15434
(quickstart.md §2). App/Redis ports if ever needed: 18034 / 16334. No live LLM/WCL; never read `.env`.

## Open questions

None for the product. Pending only the grants above.
