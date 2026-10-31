# Feature Specification: Crucial epic-203 QA fixes (profile proposals)

**Feature Branch**: `034-epic203-qa-fixes`

**Created**: 2026-10-31

**Status**: Signed off (scrum master, 2026-10-31)

**Stories**: sc-241 (2) one invalid proposal item crashes the profile tool and the chat turn ·
sc-242 (2) overlapping approvals post the follow-up twice or return 500 after applying ·
sc-243 (2) proposal card shows in the wrong chat after a mid-turn switch; misleading tool status.
All three are `qa-deferred` findings from the 2026-10-26 sweep (fix-now items FN-1, FN-2, FN-3).

**Input**: User description: "Feature 034: crucial epic-203 QA fixes for Barnaby's profile-change
proposals. sc-241: one invalid proposal item (realm/region null or blank, role written
"Healer"/"DPS", unknown action/target) must become a skipped row on the card instead of crashing
the propose_profile_changes tool and the chat turn; blank/missing realm or region are coded
invalid_realm/invalid_region; roles compare case-insensitively; any unexpected exception in the
tool returns {"status":"error"} with a plain message and the turn continues. sc-242: overlapping
approvals (or cancels) of the same proposal apply the change once, save exactly one follow-up line
and never return 500; only the call that made the transition (decided under the row lock) saves
the follow-up, in the same transaction. sc-243: a proposal card (or loose card) attaches only to
the chat whose turn produced it (the turn's conversation id from the meta frame); switching chats
or starting a new chat mid-turn never shows it in the wrong chat, reopening the original chat shows
it; while propose_profile_changes runs the status reads "Preparing profile changes" with a
matching spell entry instead of "Searching Warcraft Logs"."

**Prior context (cited, not re-derived):** `specs/029-agent-profile-proposals/` (proposal service,
validation codes, tool contract), `specs/031-confirmation-card/` (card, follow-up line FR-013 /
SC-002, loose cards), QA reports `qa-reports/2026-10-26/` (BUG-001..003, SPEC-001..003, SPEC-011,
SEC-006), sprint plan `sprints/2026-10-31/plan.md` section 034.

## Clarifications

### Session 2026-10-31

- Q: The plan's AC 1 expects "2 skipped, 1 valid" for realm null + played_role "Healer" + 1 valid,
  but roles compare case-insensitively, so "Healer" is valid. What mix does the acceptance test
  assert? → A: Raw dicts through the real ADK argument path: realm null (`invalid_realm`), region
  "" (`invalid_region`), action "promote" (`invalid_item`), played_role "Healer" (valid, stored
  and shown as `healer`) and one fully valid item: 3 skipped + 2 valid, no agent error. This is
  plan AC 1 at hand-off.
- Q: An unknown `played_role` (display-only, e.g. "Support"): skip the item or drop the role? →
  A: Drop it (shown empty); the item stays valid. An unknown `raid_role` (stored) skips the item
  as `invalid_item`.
- Q: How is the sc-242 overlap verified? → A: A Postgres concurrency test (two approvals, and two
  cancels) that self-skips without `TEST_DATABASE_URL`, run on the developer's own Postgres with
  the output pasted into the hand-off, plus a default-suite unit test that only the call making
  the transition saves the line. The hand-off does not pass without the pasted Postgres run.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One bad row never sinks the whole proposal (Priority: P1) · sc-241

The user asks Barnaby to add the people from last night's raid as friends. One player in the log
has no realm (Warcraft Logs left the server out), another is listed with the role written "Healer",
and the rest are fine. Barnaby shows one card: the fine players as normal rows, the player without
a realm as a skipped row ("realm unknown, add by hand"), and the "Healer" player as a normal row
with the role understood. Nothing crashes, and the user never sees raw program text.

**Why this priority**: Today one such row ends the whole turn with an error made of Python text, no
proposal is stored and every valid player is lost. The owner's own example request can hit this
live. It is the data-path fix the rest of the flow depends on.

**Independent Test**: Send a scripted tool call with raw items (one with no realm, one with role
"Healer", one fully valid, plus the other bad shapes below) through the same argument path the real
agent uses, and check the stored proposal: the right rows skipped with the right reason codes, the
rest valid, and the turn ends normally.

**Acceptance Scenarios**:

1. **Given** a tool call whose raw items are one with realm null, one with region "", one with
   action "promote", one with `played_role` "Healer" and one fully valid item, **When** the tool
   runs through the real agent argument path, **Then** a proposal is stored with 5 rows in order:
   3 skipped (`invalid_realm`, `invalid_region`, `invalid_item`) and 2 valid (the "Healer" row
   stored and shown as `healer`), and the turn ends without an agent error.
2. **Given** an item whose realm is blank or only spaces, **When** the proposal is created,
   **Then** that row is skipped with `invalid_realm` (not `invalid_item`). The same holds for a
   blank or missing region (`invalid_region`).
3. **Given** an item whose `raid_role` or `played_role` is written in any letter case ("Healer",
   "DPS", "TANK"), **When** the proposal is created, **Then** the role is understood as the
   matching role (`healer`, `dps`, `tank`) and the row is not skipped for it.
4. **Given** an item with an unknown action or target, or a field of the wrong kind (e.g. a name
   that is not text), **When** the proposal is created, **Then** that row alone is skipped with
   `invalid_item` and every other row is validated as usual.
5. **Given** an unexpected failure inside the tool (anything other than the known refusals),
   **When** the tool runs, **Then** it returns an error result with a plain, user-safe message
   (no exception text), the failure is logged for the developers, and Barnaby's turn continues so
   he can tell the user.

---

### User Story 2 - Approving twice still tells the truth once (Priority: P1) · sc-242

The user has the chat open in two tabs (or the browser retries a click). Both tabs send Approve for
the same card at nearly the same moment. The change is applied once, the chat gets exactly one
"Done. Added 2 friends…" line, and neither tab shows "Couldn't apply. Try again." for a change that
went through. The same holds for two overlapping Cancels.

**Why this priority**: Today both approvals save a follow-up line (two "Done" lines), or one of
them collides with the other and returns a server error although the friends were added. That
breaks 031's promise of exactly one line (FR-013 / SC-002) and makes the chat lie.

**Independent Test**: Fire two approvals of the same pending proposal at the same time against a
real database (with real row locking) and check: the profile changed once, the chat has exactly
one follow-up line, both responses are successful, and only one of them carries the follow-up.
Repeat with two cancels.

**Acceptance Scenarios**:

1. **Given** a pending proposal, **When** two approvals for it overlap, **Then** the valid items
   are applied once, exactly one follow-up line is saved in the proposal's chat, both calls return
   success with the applied proposal, and exactly one of them returns the follow-up line.
2. **Given** a pending proposal, **When** two cancels for it overlap, **Then** it is cancelled
   once, exactly one "Cancelled. Your profile is unchanged." line is saved, and both calls succeed.
3. **Given** a pending proposal, **When** an approval succeeds, **Then** the change, the status
   and the follow-up line are saved together: either all of them are saved or none is.
4. **Given** an already-applied proposal, **When** it is approved again, **Then** the stored
   result comes back with no new line (unchanged 031 behaviour).

---

### User Story 3 - The card stays in its own chat, and the status says what Barnaby does (Priority: P2) · sc-243

The user asks Barnaby in chat A to add some friends, then switches to chat B (or starts a new
chat) while Barnaby is still answering. The proposal card never appears in chat B or in the new
chat. When the user goes back to chat A, the card is there under Barnaby's answer. While Barnaby is
preparing the changes, the status line reads "Preparing profile changes" with its own spell card,
not "Searching Warcraft Logs".

**Why this priority**: Approving from chat B applies the right proposal, but the follow-up line
lands in chat A out of view, and the user approves a change outside the conversation that
explains it. It is a frontend guard on the same flow; the data-safety fixes (stories 1, 2) come
first.

**Independent Test**: Drive the chat with a scripted frame sequence for a turn in chat A, switch
to chat B (or a new chat) before the turn ends, and check that no card is added to the open chat;
reopen chat A and check the card shows once. Separately, check the status text and spell card for
the profile tool.

**Acceptance Scenarios**:

1. **Given** a turn in chat A that produces a proposal, **When** the user switches to chat B
   before the turn ends, **Then** chat B shows no proposal card, neither under a message nor as a
   standalone card, whether the turn ends normally or with an error.
2. **Given** the same turn, **When** the user starts a new chat before the turn ends, **Then** the
   new chat shows no proposal card.
3. **Given** the user left chat A mid-turn, **When** they reopen chat A after the turn, **Then**
   the card shows under Barnaby's answer (or as a standalone card if the turn failed), once.
4. **Given** the user switched away from chat A and back again before the turn ends, **When** the
   turn ends, **Then** the card shows once in chat A (no duplicate standalone card).
5. **Given** a turn in the open chat (no switch), **When** it produces a proposal, **Then** the
   card attaches to Barnaby's answer exactly as before.
6. **Given** Barnaby is running the profile tool, **When** the status line and spell card show,
   **Then** they read "Preparing profile changes" (or similar wording) with a dedicated spell
   entry, not "Searching Warcraft Logs" or the generic spell.

---

### Edge Cases

- Every item of a proposal is invalid: the proposal is still stored, all rows skipped, and the
  card offers no Approve (existing card behaviour for zero valid items).
- An item that is not an object at all (e.g. a bare string): skipped as `invalid_item`, others go on.
- Realm or region present but not text (e.g. a number): treated like any other wrong-kind field
  (`invalid_item`) unless it is missing or blank, which maps to `invalid_realm` / `invalid_region`.
- A role that is not a known role in any case ("Support", "Heals"): an unknown `played_role`
  (display-only) is dropped and the item stays valid; an unknown `raid_role` (stored) skips the
  item as `invalid_item`.
- An approval and a cancel of the same proposal overlap: whichever takes the lock first wins; the
  other is refused with the existing 409 code (`proposal_applied` / `proposal_cancelled`) and no
  second line is saved.
- An approval of an expired proposal: unchanged, refused as `proposal_expired`, no line.
- Two different proposals in the same chat approved at the same moment: out of scope (see
  Assumptions); each proposal's own line is saved once.
- The turn errors before any proposal frame: nothing to attach; unchanged.
- The user switches back and forth several times mid-turn: the card attaches only if chat A is the
  open chat when the turn ends; otherwise it shows on the next load of chat A.

## Requirements *(mandatory)*

### Functional Requirements

**sc-241 — invalid items become skipped rows**

- **FR-001**: The profile tool MUST accept a list in which any item may fail validation, and MUST
  validate each item on its own, so one invalid item becomes one skipped row and never fails the
  call, the stored proposal or the other items.
- **FR-002**: The tool's declared argument schema for the model MUST stay as descriptive as today
  (the item fields and their allowed values stay listed), so the model's guidance does not regress.
- **FR-003**: A missing, null or blank realm MUST be coded `invalid_realm`; a missing, null or
  blank region MUST be coded `invalid_region`. These checks come before the generic `invalid_item`.
- **FR-004**: `raid_role` and `played_role` MUST be compared case-insensitively and stored /
  shown in the canonical lower-case form. An unknown `played_role` MUST be dropped (the item stays
  valid); an unknown `raid_role` MUST skip the item as `invalid_item`.
- **FR-005**: An item with an unknown action or target, a missing name, or a field of the wrong
  kind MUST be skipped as `invalid_item`. Its row keeps its position (index) on the card.
- **FR-006**: A skipped row's displayed values MUST be bounded (same clipping as today) and the
  follow-up line MUST NOT repeat the name of an item refused for its identity (unchanged 031 rule).
- **FR-007**: Any unexpected exception inside the tool MUST be caught, logged with details for the
  developers, and returned as `{"status": "error", "error_message": <plain message>}` with no
  exception text; the turn continues.

**sc-242 — one decision, one line**

- **FR-008**: Approve and cancel MUST decide whether this call moved the proposal out of `pending`
  while holding the proposal's row lock, not from a read taken before the lock.
- **FR-009**: Only the call that made the transition MUST save the follow-up line, and it MUST save
  it in the same transaction as the decision (status, per-item results and profile changes).
- **FR-010**: A call that finds the proposal already decided (applied by another call, or
  cancelled twice) MUST return the stored state with no follow-up line and no server error.
- **FR-011**: The approve/cancel responses, error codes and follow-up text MUST stay as defined by
  031 (no contract change for the frontend).

**sc-243 — card in the right chat, honest status**

- **FR-012**: The chat MUST record which conversation the current turn belongs to, from the turn's
  `meta` frame.
- **FR-013**: When the turn ends (`done`), its proposals MUST attach to the answer only if the
  turn's conversation is the open chat; when it fails (`error`), its proposals MUST become
  standalone cards only if the turn's conversation is the open chat. Otherwise they are not shown
  in the open chat; reopening the turn's chat shows them from the server.
- **FR-014**: When a turn's proposals attach in the open chat, any standalone card for the same
  proposal (loaded when the user reopened the chat mid-turn) MUST be replaced, so each proposal
  shows once.
- **FR-015**: While `propose_profile_changes` runs, the status line MUST read "Preparing profile
  changes" and its spell card MUST use a dedicated entry (icon, hue, verb, flavor lines).

### Key Entities

- **Proposal item (input)**: one change the agent proposes: action, target, name, realm, region,
  optional class, spec, raid role and played role. May arrive malformed; each is validated alone.
- **Proposal item (row)**: the stored, displayed row: the item's values (clipped), its index, and
  its validation result (ok, code, message). Unchanged shape.
- **Proposal decision**: the move of a proposal from `pending` to `applied` or `cancelled`, made
  once, together with its follow-up line.
- **Turn conversation**: the conversation a streaming turn belongs to, known from its first frame.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a proposal request with any mix of valid and malformed items (missing realm or
  region, odd role spelling, unknown action or target), 100% of requests end with a stored
  proposal and a card; 0 turns end in an error showing program text.
- **SC-002**: Each malformed item maps to exactly one skipped row with the documented reason;
  every valid item in the same request stays valid.
- **SC-003**: For two overlapping approvals (or cancels) of one proposal, the profile changes
  once, the chat has exactly 1 follow-up line, and 0 of the 2 requests fails.
- **SC-004**: In 100% of mid-turn chat switches or new chats, the proposal card appears only in
  the chat that produced it, exactly once after reopening it.
- **SC-005**: While Barnaby prepares profile changes, the status text names that action in 100%
  of turns (never "Searching Warcraft Logs").
- **SC-006**: The existing proposal, card and WebSocket tests still pass; the backend suite has
  no new failures; the frontend build, typecheck and tests pass.

## Assumptions

- No change to the proposal contract the frontend reads (`ProfileProposalOut`, item rows,
  validation codes, decision response). No database migration.
- The overlap test for sc-242 runs against a real Postgres (row locks); it is skipped like the
  existing RLS tests when no Postgres test database is configured, and the developer runs it on
  the feature's own throwaway Postgres and pastes the output into the hand-off (clarification Q3).
- The older behaviour where a `done` answer lands in whichever chat is open is out of scope
  (separate issue); this feature guards proposals only, as the ticket scopes it.
- Two different proposals in the same chat decided at the same instant could still race on the
  message order; that is not part of sc-242 (which is about one proposal). Not fixed or filed
  here; the scrum master passes it to the product owner as a Backlog candidate.
- sc-214, sc-219, sc-221 and sc-225 are separate backlog tickets and not part of this feature.
  The approve/cancel route stops reading the proposal before the lock as part of FR-008, which
  overlaps sc-225's suggestion only where FR-008 needs it.
- Fakes only: no live model or Warcraft Logs calls.
