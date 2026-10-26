# Tasks: In-chat confirmation card, profile refresh and bubble width

**Input**: `specs/031-confirmation-card/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: Required (sc-207 AC 5, spec FR-021).

**Gate tags**: **[NOW]** = granted now and independent of 029. **[AFTER-029]** = only after the scrum
master says "029 MERGED, rebase" (the files are 029-held or import 029's service). Every [NOW] task
uses a fake proposal typed from the contract (029's `ProfileProposalOut` field names).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1–US5 from spec.md

## Phase 1: Setup (test runner)

- [X] T001 [NOW] Add dev deps `vitest@^3.2.4`, `@testing-library/react@^16.3`, `@testing-library/dom@^10.4`, `jsdom@^26` and the script `"test": "vitest run"` in `frontend/package.json` (run `npm install -D …` in `frontend/` so `frontend/package-lock.json` updates; nothing else in the manifests changes)
- [X] T002 [NOW] Create `frontend/vitest.config.ts`: `defineConfig` from `vitest/config`, `@vitejs/plugin-react`, `test: { environment: "jsdom", include: ["src/**/*.test.tsx"] }` (R6). The runner is verified with the first test (T010)

## Phase 2: Foundational (shared types, transport, event channel)

- [X] T003 [P] [NOW] In `frontend/src/types.ts`, add `ProposalStatus`, `ProposalValidation`, `ProposalItemResult`, `ProposalItem`, `ProfileProposal` and `ProposalDecision` exactly as in data-model.md (029's field names), plus `Message.proposals?: ProfileProposal[]` and `ConversationDetail.proposals?: ProfileProposal[]`
- [X] T004 [P] [NOW] In `frontend/src/api/wsClient.ts`, add `| { type: "proposal"; proposal: ProfileProposal }` to `Frame` with a short comment (feature 031)
- [X] T005 [NOW] In `frontend/src/api/restClient.ts`, add `approveProposal(id)` and `cancelProposal(id)` (`send<ProposalDecision>("POST", `/api/profile/proposals/${id}/approve|cancel`, undefined, { csrf: true })`). Extend `getConversation` so proposals with a `message_seq` attach to the message with that `seq` (`message.proposals`), next to the artifact mapping; `proposals` stays on the returned detail (depends on T003)
- [X] T006 [P] [NOW] Create `frontend/src/lib/profileEvents.ts`: `ProfileChange`, `notifyProfileChanged(change)` (posts on `BroadcastChannel("wcl-profile")` when available, then dispatches `CustomEvent("wcl-profile-changed")` on `window`) and `useProfileChanged(cb)` (subscribes to both in a `useEffect`, holds `cb` in a ref, unsubscribes on unmount). Guard `typeof BroadcastChannel`

## Phase 3: US1 — See exactly what Barnaby proposes (P1)

**Goal**: A proposal under Barnaby's answer renders as a card with one row per item, skipped rows marked, and "Approve N".
**Independent test**: Component test with a fake proposal; build passes.

- [X] T007 [US1] [NOW] Create `frontend/src/components/ProposalCard.tsx` (pending rendering): shadcn `Card` (Header/Title/Description/Action/Content/Footer), `ItemGroup` + `Item variant="outline" size="sm"` per item with `ItemContent`/`ItemTitle` (action + target + name) / `ItemDescription` (realm · REGION · spec class · "played X" · "role: Y"), and a `Badge` in `ItemActions`. One `LABELS` map from the design (`#card`, unknown → "not applied"). Skipped rows are dimmed. "Approve N" (`Button`) + "Cancel" (`Button variant="secondary"`). N = 0 → Approve disabled and "Nothing to apply". "Expires HH:MM" in the description. `role="group"` + `aria-labelledby`, a visually hidden `aria-live="polite"` region, card root `tabIndex={-1}`. Names and realms are plain text. Avatars are added in T021
- [X] T008 [US1] [NOW] In `frontend/src/components/MessageList.tsx`, render `m.proposals?.map(p => <ProposalCard key={p.id} …/>)` after the charts in agent bubbles. New props `looseProposals: ProfileProposal[]` (standalone cards after the messages, before `LiveMessage`) and `onFollowUp`. The memo stays intact
- [X] T009 [US1] [NOW] In `frontend/src/App.tsx`, add `pendingProposalsRef`. `case "proposal"` pushes into it; `done` attaches it as `proposals` on the agent message; `error` moves it into new `looseProposals` state; `sendText`/`newChat` reset it; `selectConversation` sets `looseProposals` to `detail.proposals?.filter(p => p.message_seq == null) ?? []`. Pass `looseProposals` to `MessageList`
- [X] T010 [P] [US1] [NOW] Create `frontend/src/components/ProposalCard.test.tsx` (pending part): a fake proposal (4 valid + 1 `duplicate_friend`) shows 5 rows, the 5th "Skipped · already a friend", and the button "Approve 4". All-invalid → Approve disabled + "Nothing to apply". A hostile name (`<img src=x onerror=…>` / `**bold**`) renders as literal text. Run `npm test`

## Phase 4: US2 — Approve or cancel, and see the result (P1)

**Goal**: Approve applies through 029's service. The card shows per-item results, and one follow-up line is saved. Cancel writes nothing.
**Independent test**: Component tests with a mocked restClient; backend REST tests.

- [X] T011 [US2] [NOW] In `frontend/src/components/ProposalCard.tsx`, add the actions: the first click sets `busy` (both buttons disabled, `Spinner` in the clicked one); call `approveProposal`/`cancelProposal`; on 200 take `res.proposal`, call `onFollowUp(conversation_id, res.follow_up)` when it isn't null, and focus the card. `ApiError.message` `proposal_expired` / `proposal_cancelled` / `proposal_applied` → set that status locally (R4); any other error → `Alert variant="destructive"` "Couldn't apply. Try again." / "Couldn't cancel. Try again." and back to pending. Result badges come from `result` (Added / Removed / Role set / Skipped · / Failed ·), and the live region gets "Applied: N added, M skipped" etc.
- [X] T012 [US2] [NOW] In `frontend/src/App.tsx`, add a stable `appendFollowUp(conversationId, message)` (`useCallback`) that appends the message when `conversationId === activeIdRef.current`, and pass it as `onFollowUp` to `MessageList`
- [X] T013 [P] [US2] [NOW] Extend `frontend/src/components/ProposalCard.test.tsx` (`vi.mock("../api/restClient")`): approve → per-item results + `onFollowUp` called once; cancel → "Cancelled" and no `approveProposal` call; a double click calls `approveProposal` once (a pending promise); a rejected request → the alert is shown and the card is pending again; 409 `proposal_expired` → expired text
- [X] T014 [US2] [AFTER-029] In `backend/app/schemas.py`, add `ProposalFrame`, `ProposalDecisionOut` and `ConversationDetail.proposals: list["ProfileProposalOut"] = []` (data-model.md)
- [X] T015 [US2] [AFTER-029] Create `backend/app/api/proposals.py`: router `/api/profile/proposals`; `POST /{proposal_id}/approve` and `/cancel` (`require_csrf`; the line is saved in a short `tenant_scope`, R2); `get_proposal` first, then `execute_proposal` / `cancel_proposal`; `ProposalError` → 404 `not_found` / 409 code; cancel returning `expired` → 409 `proposal_expired`; when this call moved the proposal out of pending, save `follow_up_text(...)` (or "Cancelled. Your profile is unchanged.") with `repo.add_message(session, proposal.conversation_id, "agent", …, tenant_id=…)` and return it as `MessageOut`. `follow_up_text` is a pure function with `_LABELS` (contracts/proposal-routes.md)
- [X] T016 [US2] [AFTER-029] In `backend/app/main.py`, add `from .api import proposals` (with the existing api imports) and `app.include_router(proposals.router)`
- [X] T017 [P] [US2] [AFTER-029] Create `backend/tests/test_proposal_routes.py` (SQLite fixtures `as_user`/`tenant_b`, proposals created through 029's `create_proposal`): approve → 200 applied, friends added, one follow-up message saved; second approve → same result, `follow_up` null, still one message, no second write; cancel → no profile change, cancelled, the line saved; expired (move `expires_at` into the past) → 409 `proposal_expired` for approve and cancel, no message; cancel after approve → 409 `proposal_applied`; another tenant's id → 404; missing CSRF → 403; approval goes through `profile_proposals.execute_proposal` (monkeypatched spy called once); `follow_up_text` unit cases (the design's three examples + "Nothing was applied.")

## Phase 5: US3 — The profile updates without a reload (P2)

**Goal**: An approve refreshes the profile page and welcome panel in every tab, and a second card with the same id takes the new state.
**Independent test**: Component test of the broadcast path; manual two-tab check.

- [X] T018 [US3] [NOW] In `frontend/src/components/ProposalCard.tsx`, call `notifyProfileChanged({ proposal, targets })` after an approve that applied ≥ 1 item (targets = distinct `target` of applied items), and `useProfileChanged` to take `change.proposal` when `change.proposal.id === proposal.id`
- [X] T019 [P] [US3] [NOW] In `frontend/src/components/WelcomePanel.tsx`, add `useProfileChanged(c => { if (c.targets.includes("own")) void load(); })`
- [X] T020 [US3] [AFTER-029] In `frontend/src/components/profile/CharactersTab.tsx`, add `useProfileChanged(() => void refresh())`, and move `ClassAvatar` (prop typed `{ name: string; class_name: string | null }`) into the new `frontend/src/components/profile/ClassAvatar.tsx` (SM grant: an export from CharactersTab pulled the lazy profile module into the chat bundle)
- [X] T021 [US3] [AFTER-029] In `frontend/src/components/ProposalCard.tsx`, render `<ItemMedia><ClassAvatar char={item} … /></ItemMedia>` per row (R7)
- [X] T022 [P] [US3] [NOW] Extend `frontend/src/components/ProposalCard.test.tsx`: a same-tab `notifyProfileChanged` with the same id and status `applied` switches a pending card to Applied; a different id leaves it pending

## Phase 6: US4 — The card always shows its real state (P2)

**Goal**: Expired renders without a request. A reload shows every card under its answer in its real state, and unlinked ones render standalone.
**Independent test**: Component test (expired); WS protocol test (frame → link at done → reload).

- [X] T023 [US4] [NOW] In `frontend/src/components/ProposalCard.tsx` + `ProposalCard.test.tsx`: shown status = expired when pending and `Date.now() >= expires_at` (at render, and re-checked on click before any request); text "This proposal expired. Ask Barnaby again." in an `Alert`, no Approve. Tests: past `expires_at` → expired with no request; status `applied`/`cancelled` from props render their end state
- [X] T024 [US4] [AFTER-029] In `backend/app/api/ws.py` `_handle_tool_end`, when `name == "propose_profile_changes"` and `ok`: parse `result["proposal"]["id"]`, `await profile_proposals.get_proposal(identity, id)`, `_send(ws, ProposalFrame(proposal=…))`, return the id. Bad id / `ProposalError` → `logger.warning`, no frame, `None`. Annotate the return as `uuid.UUID | None`
- [X] T025 [US4] [AFTER-029] In `backend/app/repositories/profile_proposals.py`, add `set_message_seq(session, ids, seq, *, tenant_id, user_id)`: one `UPDATE … WHERE id IN ids AND tenant_id AND user_id AND message_seq IS NULL` (R1); a no-op for empty `ids`
- [X] T026 [US4] [AFTER-029] In `backend/app/api/ws.py` `_handle_turn`, collect the ids `_handle_tool_end` returns, and in the done session right after `assign_message_seq_to_turn_captures` call `set_message_seq(...)` when any were collected
- [X] T027 [US4] [AFTER-029] In `backend/app/api/conversations.py` `get_conversation`, set `detail.proposals = await profile_proposals.list_proposals(identity, conv_id)`
- [X] T028 [P] [US4] [AFTER-029] Create `backend/tests/test_proposal_ws.py` (fake socket + patched `stream_response`, as in `test_model_fallback_ws.py`): a stream yielding a `propose_profile_changes` `tool_end` (real proposal from `create_proposal`) sends a `proposal` frame (the stored `ProfileProposalOut`) before `done`; after done its `message_seq` is the agent message's seq; `GET /api/conversations/{id}` returns it; another tenant's id in the tool result → no frame; a stream that raises after the proposal → the proposal keeps `message_seq` null
- [X] T029 [US4] [AFTER-029] Add an end-to-end happy path to `backend/tests/test_proposal_ws.py`: faked WCL (`wcl_fakes`, M+ fixture), a scripted stream that calls the real `get_report_participants` and the real `propose_profile_changes` with the shaman left out → proposal frame → `POST …/approve` → `GET /api/profile` lists every player except the shaman as new friends (design `#tests`)

## Phase 7: US5 — Chat bubbles use the screen width well (P3)

**Goal**: Bubbles take a share of the chat column with a cap, with no page-level horizontal scroll.
**Independent test**: Headless Chrome at 390/1280/1920.

- [X] T030 [P] [US5] [NOW] In `frontend/src/styles.css`: `.message { max-width: min(90%, 1200px); min-width: 0; overflow-wrap: anywhere; }`, `.message.user { max-width: min(75%, 900px); }`, remove the `.message.agent` `max-width`, and `.welcome-panel { max-width: min(90%, 1200px); }` (R5)
- [X] T031 [US5] [NOW] Build and serve with `vite preview` on port 18031. With headless Chrome at 390, 1280 and 1920, check `scrollWidth <= innerWidth` and the bubble widths on a page with long messages, a wide table and long code. Record the numbers in checkpoint.md / the hand-off

## Phase 8: Polish & cross-cutting

- [X] T032 Run the shadcn MCP audit checklist (`get_audit_checklist`) on `ProposalCard.tsx` and fix what it flags
- [X] T033 `cd frontend && npm test && npm run build`; `uv run --extra test pytest -q` (no new failures vs base)
- [X] T034 `git checkout -- CLAUDE.md .specify/feature.json`; ownership check (`git diff --name-only 1685bd5...HEAD` + uncommitted ⊆ grant); `node /home/rudolf/dev/warcraftlogs-agent/.gitnexus/run.cjs analyze --force` then `detect-changes --scope all --repo .` in the worktree (not partial or truncated)
- [ ] T035 Hand-off to the scrum master: branch, base, commits, files, test results, risks, how to verify each AC

## Dependencies & execution order

- **[NOW] block** (before 029 merges): T001 → T002; T003–T006 (T005 after T003); US1 T007 → T008 → T009, T010; US2 T011 → T012, T013; US3 T018, T019, T022; US4 T023; US5 T030 → T031. sc-208 (T030–T031) is independent of everything else.
- **[AFTER-029] block** (after "029 MERGED, rebase"): T014 → T015 → T016 → T017; T020 → T021; T024 → T025 → T026 → T027 → T028 → T029.
- Polish T032–T035 last.

## Parallel opportunities

T003/T004/T006 (different files); T010/T013/T022 are the same test file, so they run in sequence but can be written alongside the card; T019 and T030 are independent of the card; T017 and T028 are separate backend test files. There are no sub-agents (plan), so this is ordering freedom only.

## Implementation strategy

1. sc-208 first (smallest, verifiable at once), then the test runner + types + card (US1 → US2 → US3/US4 frontend) against a fake proposal. Commit per slice.
2. After "029 MERGED, rebase": the backend slice (frame, link, reload, routes) with its tests, then `CharactersTab` + avatars.
3. Polish, then hand-off.
