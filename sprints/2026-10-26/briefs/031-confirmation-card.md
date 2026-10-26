# Brief 031 — In-chat confirmation card, profile refresh and bubble width

- **Feature:** 031 · **Branch:** `031-confirmation-card` (set `GIT_BRANCH_NAME=031-confirmation-card` for `/speckit-specify`; spec dir `specs/031-confirmation-card/`)
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b` (track B). Before you start, the scrum master resets it to the sprint tip.
- **Base ref:** the `sprint-2026-10-26` @ `1685bd5` (030 merged)
- **Stories:** sc-207 (3) Confirm agent-initiated profile changes in chat and refresh the profile UI; sc-208 (1) Chat bubbles scale with screen width instead of a fixed size.
- **Peer:** track A developer on 029 (`dev-a-029`). It owns the proposal service you call.
- **Sprint files:** plan `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-26/plan.md` (section 031 and the overlap table), decisions `.../decisions.md` (D4, D6, D8–D13 binding), ownership `.../ownership.md`.
- **Design (the agreed input; cite it, don't re-derive it):**
  `documentation/designs/self-aware-agent/participants-and-confirmation.html` (`#transport`, `#card`,
  `#followup`, `#refresh`, `#edges`, `#tests`, `#files`) and the contract in
  `capabilities-and-tools.html#proposal-contract` / `#proposal-service-api`.

## Acceptance criteria (verbatim from plan.md)

1. *(sc-207)* When a proposal tool returns, the browser gets the proposal (frame or
   call per the 028 design) and the chat shows a confirmation card: each item's action,
   name, realm, class/role and validation result, with **Approve** and **Cancel**.
   Built from shadcn registry parts via the MCP, audit checklist run.
2. *(sc-207)* Approve executes the proposal through 029's service; the card then shows
   the per-item result and Barnaby posts a short follow-up line (per the design).
   Cancel writes nothing and the card shows it was cancelled.
3. *(sc-207)* After approval, the profile page and the friend lists update without a
   page reload.
4. *(sc-207)* Double-clicking Approve applies the change once. An expired proposal
   shows a clear "this proposal expired, ask again" state. A reload mid-confirmation
   shows the card in its real state (pending, applied, cancelled or expired).
5. *(sc-207)* Tests: a component test of the card (pending/approved/cancelled/expired),
   a WS (or REST) protocol test for proposal → approve → result, and a backend test
   that approval goes through the shared service.
6. *(sc-208)* User and agent bubbles take a percentage of the chat column instead of a
   fixed px width, with a sensible cap on very wide screens. At 390px, 1280px and
   1920px there's no horizontal page overflow; wide tables and code scroll inside the
   bubble.
7. Frontend build, typecheck and tests pass; backend suite has no new failures.

## Decisions already made (in the design and decisions; don't reopen them)

- Transport: a server→client WS `proposal` frame from `ws._handle_tool_end` (on tool
  `propose_profile_changes`; it re-reads the stored proposal). Approve and cancel go over REST:
  `POST /api/profile/proposals/{id}/approve` and `/cancel` in a new `backend/app/api/proposals.py`,
  with `require_csrf`, calling **only** 029's `profile_proposals` service (get/list/execute/cancel,
  `ProposalError` → 404/409).
- `message_seq`: set at turn end through the `repo.assign_message_seq_to_turn_captures` pattern
  (ws.py ~335). The conversation reload returns `list_proposals(...)` (`ConversationDetail.proposals`).
- Card (D4): **Approve all valid / Cancel**, no per-item toggles (sc-214 is a follow-up). Skipped
  rows are shown and never applied. Each row shows `played_role` for information (D9). shadcn parts:
  card, item, badge, button, spinner, alert (all installed). Only `ProposalCard.tsx` is a hand-built
  composition.
- Follow-up line: server-built and facts only (no model call). D10: the outcome does not enter the
  ADK session.
- Refresh: a new `frontend/src/lib/profileEvents.ts` (BroadcastChannel plus a same-tab event), with
  `CharactersTab` and `WelcomePanel` subscribing. This covers two tabs.
- Test runner: add `vitest`, `@testing-library/react` and `jsdom` as **dev dependencies only**, with
  a Complexity Tracking entry in your plan (the product owner accepted this).
- sc-208: replace the fixed `max-width: min(820px, 100%)` / `min(860px, 100%)` rules in
  `frontend/src/styles.css` (around lines 252, 283 and 828) with a percentage of the chat column
  plus a cap.

## Sequencing (ownership)

- **Start now, independent of 029:** sc-208 (styles.css, MessageList.tsx), the test runner
  (frontend manifests), `ProposalCard.tsx` + its component test against a fake proposal typed from the
  contract, `profileEvents.ts`.
- **Only after 029 merges** (029 holds them until then): `backend/app/api/ws.py` (frame plus
  message_seq assignment), `backend/app/schemas.py` (ProposalFrame, ConversationDetail.proposals),
  `frontend/src/components/profile/CharactersTab.tsx` (subscribe; 029 adds the friend_limit
  message), and everything that imports 029's service (proposals.py, conversations.py, main.py
  include_router, the backend tests). The scrum master tells you "029 MERGED, rebase".
- `frontend/src/types.ts` is yours. Mirror `ProfileProposalOut` from the contract table, using
  029's field names exactly.

## Footprint (tentative; becomes the grant after /speckit-plan)

From the 028 design's `#files` section: `backend/app/api/ws.py`, `backend/app/schemas.py`,
`backend/app/api/proposals.py` (new), `backend/app/main.py` (one include_router line),
`backend/app/api/conversations.py`, `frontend/src/api/wsClient.ts`, `frontend/src/types.ts`,
`frontend/src/api/restClient.ts`, `frontend/src/components/ProposalCard.tsx` (new),
`frontend/src/lib/profileEvents.ts` (new), `frontend/src/components/MessageList.tsx`,
`frontend/src/App.tsx`, `frontend/src/components/profile/CharactersTab.tsx`,
`frontend/src/components/WelcomePanel.tsx`, `frontend/src/styles.css`, `frontend/package.json`
+ `frontend/package-lock.json` (dev deps), the vitest config, tests, `specs/031-confirmation-card/**`.

## Working rules

- shadcn MCP: it reports "no configured registries", so pass `registries: ["@shadcn"]` explicitly.
  Run the audit checklist after any add.
- GitNexus impact before every edit (`_handle_tool_end`, `_handle_turn`, `get_conversation`,
  `MessageList`), and flag HIGH.
- Ports for any throwaway app or DB: app **18031**, Postgres **15431**, Redis **16331**. Use your own
  `docker run` containers (never `docker compose` or the default ports). Never read the owner's `.env`.
- Before change detection, run `node /home/rudolf/dev/warcraftlogs-agent/.gitnexus/run.cjs analyze --force`
  in your worktree.
- For 390/1280/1920 checks: use headless Chrome on a built preview, on your app port.
- No scope creep: sc-207 + sc-208 only. Extras go to the scrum master as Backlog suggestions.
- Never push. Restore `CLAUDE.md` and `.specify/feature.json` before each commit.
