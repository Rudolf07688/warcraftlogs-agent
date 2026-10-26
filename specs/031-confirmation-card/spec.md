# Feature Specification: In-chat confirmation card, profile refresh and bubble width

**Feature Branch**: `031-confirmation-card`

**Created**: 2026-10-26

**Status**: Signed off (scrum master, 2026-10-26)

**Stories**: sc-207 (3) Confirm agent-initiated profile changes in chat and refresh the profile UI ·
sc-208 (1) Chat bubbles scale with screen width instead of a fixed size

**Input**: User description: "When the agent's propose_profile_changes tool returns, the browser
receives the proposal and the chat shows a confirmation card (Approve all valid / Cancel) with
per-item action, name, realm, class/role and validation. Approve and cancel go through 029's proposal
service. A server-built follow-up line. The profile page and welcome panel refresh without a reload.
A double click applies once, an expired proposal says so, a reload shows the real state. sc-208: user
and agent bubbles take a percentage of the chat column with a cap; no horizontal overflow at
390/1280/1920 px; wide tables and code scroll inside the bubble."

**Design input (agreed, cited rather than re-derived):**
`documentation/designs/self-aware-agent/participants-and-confirmation.html` (`#transport`, `#card`,
`#followup`, `#refresh`, `#edges`, `#tests`, `#files`) and
`documentation/designs/self-aware-agent/capabilities-and-tools.html` (`#proposal-contract`,
`#proposal-item`, `#validation-codes`, `#proposal-service-api`). Binding sprint decisions: D4, D6,
D8, D9, D10 (`sprints/2026-10-26/decisions.md`).

## Clarifications

### Session 2026-10-26

- Q: What are the bubble width values (sc-208)? → A: Agent bubble `max-width: min(90%, 1200px)`,
  user bubble `min(75%, 900px)`; the welcome panel follows the agent value. A rem-based cap is a
  Backlog idea, not this feature.
- Q: After a repeat approve in a second tab, does that tab show the follow-up line live? → A: No.
  Its card switches to Applied; the line appears there on the next load of the chat. Exactly one
  line is saved.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See exactly what Barnaby proposes to change (Priority: P1)

The user asks Barnaby to change their profile ("add the people from last night's dungeon to my
friends, except the shaman"). Barnaby answers, and under his answer the chat shows a confirmation
card. It lists every proposed change, one row per character: the action (add, remove, change role),
whether it is a friend or one of the user's own characters, the name, the realm and region, the
class and spec, the role the character played in the run (for information) and, for items that
can't be applied, why they will be skipped. Nothing has changed yet.

**Why this priority**: The story's promise is that the agent never silently changes the user's data
(D6). Without the card there is nothing to approve, and the agent cannot write at all.

**Independent Test**: Feed the chat a proposal (from a scripted agent turn) and check that the card
appears under the right answer with one row per item, skipped rows marked, and "Approve N" counting
only the valid items.

**Acceptance Scenarios**:

1. **Given** Barnaby's turn produced a proposal with 4 valid items and 1 already-a-friend item,
   **When** the turn's answer appears, **Then** a card under it shows 5 rows, the 5th marked
   "Skipped · already a friend" and dimmed, and the primary button reads "Approve 4".
2. **Given** a proposal whose items are all invalid, **When** the card renders, **Then** Approve is
   disabled, the card says "Nothing to apply", and only Cancel is offered.
3. **Given** a character name containing markup or prompt-like text, **When** the card renders,
   **Then** it shows as plain text, never as formatted or active content.

---

### User Story 2 - Approve or cancel, and see the result (Priority: P1)

The user clicks **Approve** (all valid items) or **Cancel** (the whole proposal; D4, no per-item
toggles). After Approve, each row shows its own result (added, removed, role set, skipped, or failed
because it changed since it was proposed) and Barnaby posts one short, factual follow-up line, such as
"Done. Added 3 friends: Kazrok, Brightmane and Velyra. Skipped 1: Nightpaw (already a friend)." After
Cancel nothing is written; the card shows Cancelled and the line reads "Cancelled. Your profile is
unchanged."

**Why this priority**: Approval is the only way an agent proposal reaches the profile.

**Independent Test**: Approve a stored proposal and check the profile gained exactly the valid items,
the card shows per-item results, and one follow-up line was saved in the conversation. Cancel another
and check the profile is unchanged.

**Acceptance Scenarios**:

1. **Given** a pending card, **When** the user clicks Approve, **Then** both buttons disable and a
   spinner shows until the server answers, then the card shows Applied with a result per row and the
   follow-up line appears at the end of the chat.
2. **Given** a pending card, **When** the user double-clicks Approve, **Then** the change is applied
   once and exactly one follow-up line is saved.
3. **Given** a pending card, **When** the user clicks Cancel, **Then** nothing in the profile changes,
   the card shows Cancelled, and the follow-up line "Cancelled. Your profile is unchanged." appears.
4. **Given** the approve request fails (network or server error), **When** the answer arrives, **Then**
   the card shows an error notice ("couldn't apply, try again") and returns to its pending,
   actionable state.
5. **Given** an item valid when proposed but added by hand since, **When** the user approves, **Then**
   that row shows "Failed · already a friend" and every other valid item is applied.

---

### User Story 3 - The profile updates without a reload (Priority: P2)

After approval, the profile page's character and friend lists and the new-chat welcome panel show the
new state without the user reloading the page, including a profile page open in another browser tab.

**Why this priority**: Part of sc-207's acceptance ("refresh without a reload"); the write itself
already works without it.

**Independent Test**: Open the profile page in a second tab, approve a proposal in the chat tab, and
check the second tab's friend list shows the new friends without a reload.

**Acceptance Scenarios**:

1. **Given** the profile page is open in tab B, **When** the user approves in tab A, **Then** tab B's
   lists refresh on their own.
2. **Given** the same card is shown in two tabs, **When** the user approves in one, **Then** the other
   tab's card switches to Applied.
3. **Given** a new chat's welcome panel is showing, **When** a proposal that changes own characters is
   approved, **Then** the welcome panel reloads its recent runs.

---

### User Story 4 - The card always shows its real state (Priority: P2)

A proposal lives for 30 minutes. A late card says "This proposal expired. Ask Barnaby again." and
can't be approved. Reloading the page or reopening the chat shows every card in its real state
(pending and still actionable, applied with its results, cancelled, or expired), under the answer it
belongs to.

**Why this priority**: Required by sc-207's acceptance (AC 4); without it a reload loses the card or
shows a wrong state.

**Independent Test**: Create proposals in each state in one conversation, reopen the conversation, and
check each card is under its message and shows its state.

**Acceptance Scenarios**:

1. **Given** a pending card whose expiry time has passed, **When** it renders, **Then** it shows
   Expired with the "ask again" text and no Approve, without contacting the server.
2. **Given** the user clicks Approve just after expiry, **When** the server rejects it as expired,
   **Then** the card shows Expired and nothing is written.
3. **Given** a conversation with an applied, a cancelled and a pending proposal, **When** the user
   reopens it, **Then** each card is under its own answer in its real state, and the pending one can
   still be approved.
4. **Given** a turn that produced a proposal but never finished (socket dropped or the turn failed),
   **When** the chat is shown again, **Then** the proposal appears as a standalone card at the end of
   the chat rather than disappearing.

---

### User Story 5 - Chat bubbles use the screen width well (Priority: P3)

On wide and narrow screens, user and agent bubbles take a share of the chat column instead of a fixed
width, with a cap so lines stay readable on very wide screens. Nothing makes the page scroll sideways;
a wide table or code block scrolls inside its bubble.

**Why this priority**: Independent 1-point story (sc-208), bundled because it touches the same message
rendering. First to drop if the sprint runs late.

**Independent Test**: View a chat with a long answer, a wide table and a long code line at 390, 1280
and 1920 px wide and check the bubble widths and the absence of page-level horizontal scroll.

**Acceptance Scenarios**:

1. **Given** a 1920 px wide window, **When** a long answer renders, **Then** the agent bubble is wider
   than today's fixed 860 px but no wider than the cap, and the page has no horizontal scroll.
2. **Given** a 390 px wide window, **When** a wide table renders, **Then** the bubble fits the column
   and the table scrolls horizontally inside the bubble.
3. **Given** a 1280 px window, **When** user and agent messages render, **Then** both take the
   percentage width (up to their content) and the page has no horizontal scroll.

---

### Edge Cases

All from the design's `#edges` table; restated only as testable behaviour:

- **Expired**: shown on load once the expiry time has passed; a late approve or cancel gets the
  server's "expired" answer; no follow-up line.
- **Two tabs**: the first Approve wins; a later Approve elsewhere returns the stored result with no
  second write and no second line; a later Cancel gets "already applied" and the card shows Applied.
  The second tab doesn't show the follow-up line live; it appears there on the next load.
- **Approval after the conversation moved on**: still actionable until expiry; the card stays on its
  original message; the follow-up line is appended at the end of the chat.
- **Approve while another answer is streaming**: allowed; it doesn't wait for the running turn.
- **Another tenant's or user's proposal id**: "not found"; nothing is shown or written.
- **More than 30 items**: no proposal and no card (the tool refuses; 029's behaviour).
- **Unknown realm or region, friend limit, own character**: rows shown as skipped with their label.
- **Hostile names**: rendered as plain text.

## Requirements *(mandatory)*

### Functional Requirements

**Delivery of the proposal (design `#transport`)**

- **FR-001**: When the agent's proposal tool succeeds within a turn, the server MUST send the proposal
  to the browser as it is stored (not as the model saw it), before the turn ends. If the stored
  proposal can't be read for this user, nothing is sent and the event is logged.
- **FR-002**: When the turn's answer is saved, the server MUST link the turn's proposals to that answer
  (the same step that links charts today). A proposal whose turn never finished stays unlinked.
- **FR-003**: Reopening a conversation MUST return its proposals with their current status and their
  link to an answer.

**The card (design `#card`)**

- **FR-004**: The card MUST render inside Barnaby's bubble under the answer text, with one row per item
  in the proposal's order, showing action, target (friend or own character), name, realm, region,
  class and spec, played role (display only, D9), the requested role when set, and the validation or
  result label from the design's label map.
- **FR-005**: The card MUST offer exactly two actions: "Approve N" (N = valid items) and Cancel (D4).
  With N = 0, Approve is disabled and the card says "Nothing to apply".
- **FR-006**: After the first click on either action, both buttons MUST be disabled with a busy
  indicator until the answer arrives.
- **FR-007**: A pending card whose expiry has passed MUST render Expired ("This proposal expired. Ask
  Barnaby again.") without a request. The server's answer is the authority whenever one arrives.
- **FR-008**: Names and realms MUST render as plain text.
- **FR-009**: The card MUST be a labelled group, announce state changes politely to assistive
  technology (e.g. "Applied: 3 added, 1 skipped"), and keep focus on the card after an action.
- **FR-010**: The card MUST take the server's state whenever a response or a broadcast from another
  tab carries it (for example Applied after a Cancel that lost the race).

**Approve and cancel (design `#transport`, `#followup`)**

- **FR-011**: Approve MUST apply the proposal through the shared proposal service (029) and nothing
  else; the approval path never writes profile rows itself. Cancel MUST write no profile data.
- **FR-012**: Approve and cancel MUST use the same security path as every profile write (signed-in
  user, tenant scope, cross-site request protection) and answer "not found" for a proposal that isn't
  the user's.
- **FR-013**: A repeated approve MUST return the stored result without writing again and without a
  second follow-up line. A cancel after apply and actions on an expired or cancelled proposal MUST be
  refused with their specific reason.
- **FR-014**: When an approve or cancel changes the proposal's state, the server MUST save one
  follow-up agent message in the proposal's conversation, built from the per-item results only (no
  model call), using the same wording as the card's labels, and return it with the proposal. Expired
  gives no message.
- **FR-015**: The outcome MUST NOT be added to the agent's session memory (D10); the next turn learns
  the new profile from its usual profile context.

**Refresh (design `#refresh`)**

- **FR-016**: After a successful approve, the browser MUST notify every open tab of the same app that
  the profile changed (which proposal, and whether friends or own characters changed).
- **FR-017**: The profile page's character/friend lists MUST reload on that notification, and the
  welcome panel MUST reload when own characters changed. A card showing the same proposal MUST take
  the broadcast state.

**Reload (design `#edges`)**

- **FR-018**: On reopening a conversation, each linked proposal MUST render under its answer in its
  real state; an unlinked one MUST render as a standalone card at the end of the chat. A proposal from
  a failed turn MUST stay visible as a standalone card.

**Bubble width (sc-208)**

- **FR-019**: User and agent bubbles MUST size as a percentage of the chat column, with a maximum
  width cap for very wide screens, replacing the fixed pixel maximums: agent bubbles at most 90% of
  the column and 1200 px, user bubbles at most 75% and 900 px; the new-chat welcome panel follows
  the agent value.
- **FR-020**: At 390, 1280 and 1920 px window widths the page MUST NOT scroll horizontally; wide tables
  and code MUST scroll inside their bubble.

**Tests (AC 5, 7)**

- **FR-021**: The feature MUST ship a component test of the card (pending, approved, cancelled,
  expired, double click, error), a protocol test (proposal tool end → proposal delivered → linked to
  the answer → returned on reload; another tenant's id → nothing delivered), and backend tests of
  approve/cancel (idempotency, no second line, expired, cancel after apply, other tenant, and that
  approval goes through the shared service). Frontend build, typecheck and tests pass; the backend
  suite has no new failures.

### Key Entities

- **Profile proposal**: defined once in the 027 contract (`#proposal-contract`): id, conversation,
  answer link (message seq), status (pending | applied | cancelled | expired), created/expires/applied
  times, and 1–30 items. This feature mirrors it in the browser and never redefines it.
- **Proposal item**: index, action, target, name, realm, region, class, spec, requested role, played
  role (display only), previous role, validation {ok, code, message}, result {status, code,
  character} (null while pending).
- **Follow-up line**: an ordinary saved agent message in the proposal's conversation.
- **Profile-changed notification**: a browser-side event carrying the proposal and which lists
  changed; never sent to the server.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of agent-initiated profile changes reach the profile only after an explicit Approve
  on a card the user saw (no write path bypasses the card).
- **SC-002**: A double click or a second tab's Approve applies a proposal exactly once and produces
  exactly one follow-up line (verified by test).
- **SC-003**: After Approve, the card's results and the follow-up line appear as soon as the server
  answers, and an open profile page in another tab updates on its own, without a reload (checked
  manually at the live check).
- **SC-004**: Reopening a conversation shows every proposal card in the state the server holds (4 of
  4 states verified by test).
- **SC-005**: At 390, 1280 and 1920 px, the chat page has zero horizontal page overflow, and at
  1920 px agent bubbles use more width than the old fixed 860 px.
- **SC-006**: Frontend build, typecheck and the new frontend tests pass; the backend suite has no new
  failures.

## Assumptions

- 029 provides the stored proposal, its wire shape (`ProfileProposalOut`), the proposal tool, the
  `message_seq` column and the service functions (get, list, execute, cancel) with `ProposalError`
  codes. 031's backend wiring starts only after 029 merges into the sprint branch; until then the card
  is built against a fake proposal typed from the contract.
- The proposal time-to-live is 029's (30 minutes); the card shows the expiry time, with no live
  countdown.
- Other devices (a phone with the profile open) see the change on their next load (design `#refresh`,
  accepted for v1).
- Charts are still not restored on reload (sc-213, a separate follow-up); only proposals are.
- Per-item selection on the card is out of scope (D4; follow-up sc-214).
- The repo has no frontend test runner; this feature adds one as development-only dependencies
  (accepted by the product owner, recorded in the plan's Complexity Tracking).
