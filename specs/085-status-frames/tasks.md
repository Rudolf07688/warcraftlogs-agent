# Tasks: Status frames and turn costs (085)

**Input**: specs/085-status-frames/ (spec, plan, research, data-model, contracts)
**Tests**: requested (security-core: hostile inputs and bounds first, then the fix; one mutation bite per guard).

## Phase 1: Setup

- [X] T001 Branch `085-status-frames` from 4fc12a3 in /home/rudolf/dev/wcl-worktrees/dev-b; stories sc-582/sc-583 In Progress

## Phase 2: Foundational

- [X] T002 [P] Status text helper `cleanStatus` (strip bidi/zero-width controls, clamp 120 code points) in frontend/src/lib/statusText.ts
- [X] T003 [P] `statusStore` + `useTurnStatus` (status, thought, notice, quietSince; immutable snapshot) in frontend/src/lib/statusStore.ts

## Phase 3: User Story 1 - saved answer never holds retracted text (P1)

**Independent test**: scripted retracting turns cut by cancel/drop; stored = reload, no retracted text.

- [X] T004 [US1] Tests first in backend/tests/test_085_status_frames.py: cancel during the interim send (no retracted text stored; no DB scope open during the send); second tab during the partial save (old turn not cancelled, stored = reload); drop after a retraction with nothing kept stores "(no response)"
- [X] T005 [US1] Update the SEC-002 drop test in backend/tests/test_080_thinking_ws.py (drop on the interim send now stores the placeholder, not the retracted text); same for the drop-at-tool_start test
- [X] T006 [US1] ws.py `_run_chat_turn`: clear tokens before sending `interim`, remember the retraction; on `WebSocketDisconnect` with a retraction and no tokens persist "(no response)" in backend/app/api/ws.py
- [X] T007 [US1] mutate.py bite: restore send-before-clear → T004 cancel test fails; drop placeholder removed → drop test fails

## Phase 4: User Story 2 - retry/fallback notices under the cards (P2)

**Independent test**: card + `model_retry` frame → status line shows the label; odd values plain and bounded.

- [X] T008 [US2] Tests first: backend/tests/test_085_status_frames.py retry record with NaN/negative/huge numbers → valid JSON frame (json.dumps allow_nan=False) matching the contract example; frontend/src/App.thinking.test.tsx retry and fallback labels under cards, long/markup ids, NaN numbers, `<script>`, zero-width and RTL-override text (plain, ≤120, controls gone, dir=auto)
- [X] T009 [US2] ws.py: build `ModelRetryFrame` with finite non-negative numbers in backend/app/api/ws.py
- [X] T010 [US2] App.tsx writes the status store (notice on model_retry/fallback, cleared by other status events); TurnStatus shows `thought ?? notice ?? generic` under cards, text through `cleanStatus`, `dir="auto"` in frontend/src/App.tsx and frontend/src/components/MessageList.tsx
- [X] T011 [US2] mutate.py bite on `cleanStatus` control stripping and on the ws.py NaN guard

## Phase 5: User Story 3 - cheaper turns (P3)

**Independent test**: preamble query columns; App render count over 50 thinking frames.

- [X] T012 [P] [US3] Tests first: backend/tests/test_085_status_frames.py preamble reads 2 columns from profile_settings, no user_characters query; backend/tests/test_085_main_selection_pg.py another tenant's row is invisible under RLS; frontend/src/App.thinking.test.tsx 50 thinking frames → App/MessageList render count unchanged, latest thought shown; backend test: a turn with 50 thinking frames opens as many DB scopes as one with none
- [X] T013 [US3] `repo.get_main_selection` in backend/app/db/repository.py; `_build_turn_preamble` uses it in backend/app/api/ws.py
- [X] T014 [US3] Move status/thought/quietSince out of App state into the store; MessageList drops those props; LiveMessage subscribes (frontend/src/App.tsx, frontend/src/components/MessageList.tsx, frontend/src/components/MessageList.test.tsx)

## Phase 6: Polish

- [X] T015 Full area runs (`check.py run --as edda --base 4fc12a3`), GitNexus detect-changes, facts, board hand-off, stories Under Review

## Dependencies

T002/T003 before T010/T014. US1 (backend) and US2/US3 frontend parts are independent; T009 and T006 both edit ws.py (sequential).
