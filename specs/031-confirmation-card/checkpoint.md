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

- Sent to dev-a-029 (no answer yet): the tool result shape (`result.proposal.id`), the service
  signatures `(identity, uuid)` + `ProposalError.code`, cancel past expiry returns `expired`, guide
  tasks scheduled by `execute_proposal`, and whether a `set_message_seq`-like helper already
  exists or is planned (SM note 1: avoid two helpers).
- `types.ts` mirror built from 029's branch `schemas.py` (afedf60). Re-check field names after the
  merge.

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
