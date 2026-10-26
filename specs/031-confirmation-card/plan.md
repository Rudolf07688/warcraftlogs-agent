# Implementation Plan: In-chat confirmation card, profile refresh and bubble width

**Branch**: `031-confirmation-card` | **Date**: 2026-10-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/031-confirmation-card/spec.md` (signed off 2026-10-26)

## Summary

The agent's `propose_profile_changes` tool (029) stores a pending proposal. 031 delivers it to the
browser as a typed WS `proposal` frame, re-read from storage. The frame is linked to the turn's
answer at `done` and returned again on conversation reload. The proposal renders as a confirmation
card built from installed shadcn parts. **Approve** and **Cancel** go over REST
(`POST /api/profile/proposals/{id}/approve|cancel`), which calls only 029's proposal service and saves
one server-built follow-up line. After an approve, a browser-side `profileEvents` channel refreshes
the profile page and the welcome panel in every tab. sc-208 swaps the fixed bubble `max-width`s for
a share of the chat column plus a px cap. Every transport and UX decision comes from the agreed
design (`participants-and-confirmation.html` `#transport` `#card` `#followup` `#refresh` `#edges`
`#tests` `#files`) and the 027 contract (`capabilities-and-tools.html#proposal-contract`,
`#proposal-service-api`). This plan does not re-derive them. Research covers only the points those
documents leave to the implementer.

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript 5.5 + React 19 (frontend)

**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy async (existing); React, Tailwind v4,
shadcn/ui parts already installed (card, item, badge, button, spinner, alert, avatar). New
**dev-only**: `vitest@^3.2.4`, `@testing-library/react@^16.3`, `@testing-library/dom@^10.4`,
`jsdom@^26` (see Complexity Tracking).

**Storage**: 029's `profile_proposals` table (migration 0016, `message_seq` column). 031 adds no
migration. The follow-up line is an ordinary `messages` row.

**Testing**: pytest (`uv run --extra test pytest -q`) over the SQLite fixtures (`as_user`,
`patched_db`); the frontend gets vitest + jsdom (`npm test` in `frontend/`).

**Target Platform**: Linux server (Docker) + evergreen browsers (BroadcastChannel is available in all
of them; guarded anyway).

**Project Type**: Web application (`backend/` + `frontend/`).

**Performance Goals**: No new per-turn cost. The frame costs one extra short read (`get_proposal`),
and only after a successful proposal tool call. No polling.

**Constraints**: No DB connection is held while the model streams (PERF-006). The routes call only
029's service (D6, plan overlap table). The outcome stays out of the ADK session (D10).
`MessageList` keeps its memo (PERF-010): the new props are stable callbacks and arrays held in state.

**Scale/Scope**: ≤ 30 items per proposal; one card per proposal; a handful of proposals per chat.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. DRY & reuse | The proposal shape is defined once (029's `ProfileProposalOut`) and mirrored once in `types.ts`. Service calls go only through `profile_proposals`. Linking at `done` sits in the same transaction as `assign_message_seq_to_turn_captures`. Reload attaches proposals in `getConversation`, next to the existing artifact-by-seq mapping. Avatars reuse `ClassAvatar` (exported from `CharactersTab.tsx`, not copied). The follow-up wording reuses one label map per language (server and card; this is the design's choice). Error codes come from `ApiError.message`, as `CharactersTab` does. | Pass |
| II. Step-wise | Slices: (1) sc-208 CSS, verified at 3 widths; (2) test runner + types + card + component test; (3) profileEvents + subscriptions; (4, after 029) backend frame/routes/reload + tests; (5) App wiring. Each slice is built or tested before the next. | Pass |
| III. YAGNI | No server push, no WS inbound frame, no polling, no per-item toggles (D4), no new GET route (a 409 maps to the state locally). Only new runtime file on the backend: `api/proposals.py`. Dev deps justified below. | Pass (1 entry) |
| IV. Typed contracts | `ProposalFrame`, `ProposalDecisionOut` and `ConversationDetail.proposals` are Pydantic models. The frontend `Frame` union and `ProfileProposal` types mirror them. | Pass |
| V. Async FastAPI | New routes are `async def`. Service calls are awaited, and each opens its own tenant transaction. | Pass |
| VI. GitNexus | Upstream impact run (see below). All LOW. The UNKNOWN results are confirmed by text search. | Pass |
| VII. shadcn MCP | Searched `@shadcn` for card, item, alert, spinner and confirm. Every part needed is installed (`card`, `item`, `badge`, `button`, `spinner`, `alert`, `avatar`). "confirm" has no registry item. `alert-dialog` doesn't fit, because the card is inline in the chat, not modal. **Hand-built:** only `ProposalCard.tsx`, the composition of those parts (design `#card`): no registry block covers a list of proposed changes with approve and cancel. The audit checklist runs after the card is built. | Pass |
| VIII. Backlog sync | Stories sc-207/sc-208 In Progress. Backlog suggestion for the SM: rem-based bubble cap (Q1 option C). | Pass |

**GitNexus upstream impact (index 1 commit behind; it'll be re-run on the worktree before
commit):**

| Symbol | Risk | Direct callers | Notes |
|---|---|---|---|
| `ws._handle_tool_end` | LOW | 1 (`_handle_turn`) | process `chat`; return type gains `uuid \| None` |
| `ws._handle_turn` | LOW | 1 (`chat`) | process `chat`; only the done-step grows |
| `conversations.get_conversation` | UNKNOWN → LOW | route only (HTTP; tests via `/api/conversations/{id}`) | text search: no Python callers |
| `repo.assign_message_seq_to_turn_captures` | LOW | 1 (`_handle_turn`) | not modified; the proposal link runs next to it |
| `MessageListImpl` / `MessageList` | UNKNOWN → LOW | `App.tsx` only | text search |
| `App` | UNKNOWN → LOW | `main.tsx` only | text search |
| `getConversation` (restClient) | LOW | 1 (`App.selectConversation`) | |

## Project Structure

### Documentation (this feature)

```text
specs/031-confirmation-card/
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── proposal-frame.md        # WS frame + done-linking + reload
│   ├── proposal-routes.md       # approve / cancel REST + follow-up line
│   └── frontend-card.md         # ProposalCard props, states, profileEvents API
├── checkpoint.md        # written before implement
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/app/
├── api/ws.py                     # _handle_tool_end → proposal frame; _handle_turn → link at done   (after 029)
├── api/proposals.py              # NEW approve/cancel routes + follow-up line builder               (after 029)
├── api/conversations.py          # get_conversation → detail.proposals                               (after 029)
├── main.py                       # one include_router line                                           (after 029)
├── schemas.py                    # ProposalFrame, ProposalDecisionOut, ConversationDetail.proposals  (after 029)
└── repositories/profile_proposals.py  # + set_message_seq(session, ids, seq, …) helper              (after 029, grant from 029's file)
backend/tests/
├── test_proposal_ws.py           # NEW protocol test (+ e2e happy path with fakes)                   (after 029)
└── test_proposal_routes.py       # NEW REST + follow-up + service-spy tests                          (after 029)

frontend/
├── package.json, package-lock.json   # dev deps + "test" script                                     (now, grant)
├── vitest.config.ts                  # NEW jsdom config                                              (now)
└── src/
    ├── styles.css                    # sc-208 bubble widths                                          (now)
    ├── types.ts                      # ProfileProposal & co., Message.proposals, ConversationDetail.proposals (now)
    ├── api/wsClient.ts               # Frame union: proposal                                         (now)
    ├── api/restClient.ts             # approveProposal / cancelProposal; getConversation attaches proposals (now)
    ├── lib/profileEvents.ts          # NEW notifyProfileChanged / useProfileChanged                  (now)
    ├── components/ProposalCard.tsx   # NEW card                                                      (now; ClassAvatar import after its export)
    ├── components/ProposalCard.test.tsx  # NEW component test                                       (now)
    ├── components/MessageList.tsx    # render cards per message + standalone cards                   (now)
    ├── components/WelcomePanel.tsx   # subscribe (own changed → load())                              (now)
    ├── App.tsx                       # pendingProposalsRef, attach on done/error/reload, follow-up append (now)
    └── components/profile/CharactersTab.tsx  # subscribe → refresh(); export ClassAvatar             (after 029)
```

**Structure Decision**: Existing web-app layout. The only new runtime modules are
`backend/app/api/proposals.py`, `frontend/src/lib/profileEvents.ts` and
`frontend/src/components/ProposalCard.tsx`.

## Design decisions left to this plan (details in research.md)

- **R1 Linking at done**: `_handle_turn` collects the proposal ids `_handle_tool_end` sent and stamps
  only those (`set_message_seq` in 029's row-helper module, in the same session as
  `assign_message_seq_to_turn_captures`). A proposal from a failed turn keeps `message_seq = null`
  and stays a standalone card, as `#edges` requires. Stamping "all unlinked" like artifacts would
  move such a card under the next answer.
- **R2 Follow-up**: the route reads `get_proposal` first. It saves a line only when this call moved
  the proposal out of `pending` (applied or cancelled) and returns it as `follow_up`; repeats return
  `null` (Q2 = A). The line is built by a pure function in `api/proposals.py`.
- **R3 Cancel on expired**: 029's `cancel_proposal` returns the proposal with status `expired`.
  The route turns that into 409 `proposal_expired`, matching the design's REST table.
- **R4 409 on the card**: `proposal_expired`, `proposal_cancelled` and `proposal_applied` set the
  card's status locally without another request. The rows keep their last known detail; the next
  reload or broadcast fills in the results. 404 and other errors show the alert and return the card
  to pending.
- **R5 Bubble widths** (Q1 = A): `.message` → `min(90%, 1200px)`; `.message.user` → `min(75%,
  900px)`; `.welcome-panel` → `min(90%, 1200px)`; the `.message.agent` override is removed. A
  `min-width: 0` / `overflow-wrap: anywhere` guard on the bubble keeps long tokens inside, and the
  existing `.markdown pre/table { overflow-x: auto }` keeps wide content scrolling inside the bubble.
- **R6 Test runner**: a separate `frontend/vitest.config.ts` (React plugin, `environment: "jsdom"`),
  explicit `import { describe, it, expect, vi } from "vitest"` (no globals, so `tsc -b` needs no extra
  types), and `"test": "vitest run"`. No `jest-dom` (assertions use plain DOM queries).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New dev dependencies `vitest`, `@testing-library/react`, `@testing-library/dom` (RTL peer), `jsdom` | AC 5 needs a component test of the card (pending/approved/cancelled/expired, double click), and the repo has no frontend test runner. Accepted by the PO and SM (D9 note; design `#tests`). They're dev only, so nothing is added to the bundle. `vitest@3.2.x` is the line that supports the repo's Vite 5 (4.x/5.x need Vite ≥ 6). | Testing the card only through the backend can't exercise the click, busy and expired states. A hand-rolled `react-dom/test-utils` harness would still need a DOM (jsdom) and would rebuild what RTL already does. Playwright is a heavier browser runner, and the repo has none. |
