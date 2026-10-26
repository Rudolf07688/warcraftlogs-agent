# Checkpoint: 031 confirmation card (resume point)

**Worktree**: `/home/rudolf/dev/wcl-worktrees/dev-b` · **Branch**: `031-confirmation-card` · **Base**:
`1685bd5` (sprint-2026-10-26 with 027, 028 and 030 merged) · **Developer**: dev-b-031 · **SM**:
`scrum-master` · **Peer**: `dev-a-029` (owns the proposal service)

## Gates

- Spec signed off (SM, 2026-10-26). Q1 = A (agent `min(90%, 1200px)`, user `min(75%, 900px)`, the
  welcome panel follows the agent value). Q2 = A (no live follow-up line in a second tab). SC-003 is
  qualitative and checked manually.
- Plan approved + grant (SM, 2026-10-26). Tasks + this checkpoint → waiting for the SM's
  "GO implement 031".
- Shortcut: sc-207, sc-208 In Progress (iteration 161). Leave them In Progress at hand-off.

## Files owned

- **Now**: `frontend/package.json` + `package-lock.json` (the 4 dev deps + the `test` script only),
  `frontend/vitest.config.ts` (new), `frontend/src/styles.css`, `types.ts`, `api/wsClient.ts`,
  `api/restClient.ts`, `lib/profileEvents.ts` (new), `components/ProposalCard.tsx` + `.test.tsx`
  (new), `components/MessageList.tsx`, `App.tsx`, `components/WelcomePanel.tsx`,
  `specs/031-confirmation-card/**`.
- **After "029 MERGED, rebase"**: `backend/app/api/ws.py` (`_handle_tool_end` + the link at done),
  `backend/app/schemas.py` (ProposalFrame, ProposalDecisionOut, ConversationDetail.proposals),
  `backend/app/api/proposals.py` (new), `backend/app/main.py` (one include_router),
  `backend/app/api/conversations.py`, `backend/app/repositories/profile_proposals.py` (ONE
  `set_message_seq` helper), `frontend/src/components/profile/CharactersTab.tsx` (subscribe + export
  `ClassAvatar`), `backend/tests/test_proposal_{ws,routes}.py` (new).
- Never commit: `CLAUDE.md`, `.specify/feature.json` (set locally to this feature dir; restore before
  each commit).

## Decisions (beyond the design; see research.md)

R1 link only this turn's proposal ids at done · R2 the follow-up line is saved only when this call
left pending · R3 cancel on expired → 409 `proposal_expired` · R4 a 409 on the card sets the state
locally, with no GET route · R5 CSS values · R6 vitest 3.2.x (Vite 5), separate config, explicit
imports · R7 reuse `ClassAvatar` (after 029) · R8 `looseProposals` state for unlinked or failed-turn
proposals · R9 follow-up appended only for the active conversation.

## Open questions

- None blocking. dev-a-029 confirmed (029 @ 8e9bf9e): success result `{"status":"success",
  "proposal": <json>, "note"}`, with `result["proposal"]["id"]` a str UUID (an error has no
  `proposal` key); service functions `(identity, uuid)` each in their own `tenant_scope`;
  `ProposalError.code` in `backend.app.services.profile_proposals`; cancel past expiry stores and
  returns `expired` (no raise); execute past expiry raises `proposal_expired`; execute on applied
  returns it unchanged; execute on cancelled raises `proposal_cancelled`; cancel on applied raises
  `proposal_applied`; guide tasks are scheduled by `execute_proposal`. No `set_message_seq`
  equivalent exists or is planned, so 031 writes it (filter tenant_id AND user_id AND message_seq IS
  NULL). The status is computed on read (pending past expiry reads as `expired`). A skipped item
  has `result.code` = its validation code.
- `types.ts` mirror built from 029's branch `schemas.py` (afedf60). Re-check field names after the
  merge.

## Baseline and progress

- Backend baseline before any code change (base 1685bd5 + docs): `uv run --extra test pytest -q`
  → **1083 passed, 3 skipped, 1 deselected**.
- [NOW] done: T001–T013, T018, T019, T022, T023, T030. `npm test`: 12 passed. `npm run build`:
  clean.
- T031 widths (throwaway harness `frontend/harness-031/`, untracked, never commit; preview on 18031,
  chrome-headless-shell): 1920 user 900 / agent 1200 (base 820/860), page width = viewport; 1280
  user 708 / agent 850, page width = viewport; a long URL no longer overflows the bubble (base
  scrollWidth 1508 > 858). 390: the page is 698 wide before AND after (fixed 260px sidebar +
  header controls, no mobile layout = sc-175). Escalated to the SM (A/B/C), decision pending.
- T032 audit checklist run once (named imports ok, no new deps, tsc clean, no eslint in repo, no
  Playwright MCP, so the headless Chrome harness was used). Re-run after T021 (avatars).

## Where implementation starts

`/speckit-implement` once GO arrives. Order: T030–T031 (sc-208), T001–T002 (runner), T003–T006,
T007–T013, T018/T019/T022/T023. Then wait for "029 MERGED, rebase" → T014–T017, T020–T021,
T024–T029 → T032–T035.

## Notes

- Ports for throwaway services: app 18031, Postgres 15431, Redis 16331. No docker compose, never
  read the owner's `.env`.
- GitNexus impact (pre-edit, all LOW): `_handle_tool_end`, `_handle_turn`,
  `assign_message_seq_to_turn_captures`, `getConversation`; UNKNOWN resolved by text search for
  `get_conversation` (HTTP route), `MessageListImpl` (App only) and `App` (main.tsx only).
- Backlog suggestion sent to the SM: a rem-based bubble cap.
- Observation (not in scope): `restClient.getConversation` already attaches artifacts by seq, so
  the sc-213 "charts not restored on reload" bug may sit elsewhere (e.g. figure rebuild or
  `PlotlyArtifact`). Mention it to the SM at hand-off for sc-213 triage.
