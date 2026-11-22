# Feature Specification: Status frames and turn costs

**Feature Branch**: `085-status-frames`

**Created**: 2026-11-22

**Status**: Draft

**Input**: Sprint 2026-11-22 brief 085 (sc-582 socket/UI part, sc-583 settings read and status store). Contract `contract:chat-status-records`: the `thinking`, `interim`, `model_retry` and `model_fallback` shapes stay as on base 4fc12a3.

## Clarifications

### Session 2026-11-22

Answered by the developer (autonomy rule); each is a board decision `scope:085:<topic>`.

- Q: After a drop that retracted all text so far, what does the turn store? → A: a partial "(no response)" (not nothing, not the retracted text): it gives the reconnect reload the server's word (`scope:085:drop-placeholder`).
- Q: Does the placeholder apply when the turn ends by a second tab's cancel or an error? → A: No, drops only: on cancel and error the browser drops its local copy itself (error frame), and a placeholder would add a row the new tab never saw.
- Q: How long does a retry/fallback notice show under the cards? → A: Until the turn's next status event (tool start/end, thinking, interim, grounding); the latest event wins over an older thought line (`scope:085:retry-under-cards`).
- Q: Does the browser strip bidi and zero-width controls itself? → A: Yes, at render, besides the runner's own clean-up; the line also gets `dir="auto"` (`scope:085:status-text`).
- Q: Where does the BUG-004 fix act? → A: The socket clears the turn's tokens before it sends the `interim` frame (was after), so a cancel during that send cannot keep them (`scope:085:retraction-order`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The saved answer never holds retracted progress text (Priority: P1)

A player asks a question. The assistant first writes a short progress note ("Warcraft Logs errors on report aB3xY9, I'll retry"), then decides that note was progress, not answer, and retracts it before looking something up. If the turn ends early at exactly that moment (the player continues the chat in a second tab, or the connection drops), the answer kept for that turn must not contain the retracted note, and what the player sees after reopening the chat, what the PDF export contains and what is stored must be the same.

**Why this priority**: data integrity of the saved conversation (the 080 security review's "live = reload" rule); retracted text can carry report codes and retry notes that should never read as an answer.

**Independent Test**: script a turn that streams a progress note and retracts it, cut the turn at the retraction (a second tab's cancel during the retraction send; a socket drop during or after it), then compare the stored messages with what a reload shows.

**Acceptance Scenarios**:

1. **Given** a turn retracting its progress note, **When** a second tab's turn on the same chat cancels it while the retraction is being sent, **Then** the stored partial holds no retracted text and a reload shows exactly what is stored.
2. **Given** a turn that retracted its progress note and has no answer text yet, **When** the connection drops (the retraction may never have reached the browser), **Then** the stored turn ends with a partial "(no response)" message, and after the reconnect the browser shows the stored messages only, never its local copy of the retracted note.
3. **Given** a second tab's turn arriving while the first turn is saving its partial, **When** the save completes, **Then** the stored partial equals what a reload shows and the first turn was not cut mid-save.

---

### User Story 2 - Model retry and fallback notices show under spell cards (Priority: P2)

While a turn waits out a model rate limit, or switches to the sibling model, the player sees "Model busy — retrying (1 of 5)…" or "X is rate-limited — switching to Y…". Today this only shows before the first spell card; once cards exist the notice is invisible. It must show in the status line under the cards too, and always as plain, bounded text.

**Why this priority**: the player otherwise sees a silent stall of up to a minute.

**Independent Test**: send a tool card, then a `model_retry` frame; the status line under the cards shows the retry label.

**Acceptance Scenarios**:

1. **Given** a turn with a spell card, **When** a `model_retry` or `model_fallback` frame arrives, **Then** the status line under the cards shows its label until the turn's next status event.
2. **Given** a retry/fallback frame with a very long model id, markup in the id, or odd numbers (negative, NaN wait), **When** it is shown, **Then** the label renders as plain text, at most the status cap long, and the frame still reaches the browser as valid data.

---

### User Story 3 - Cheaper chat turns (Priority: P3)

Each chat turn reads only the two settings fields it uses (main class and main spec) of the player's own workspace, and the live status line updates without re-rendering the whole app or the message list.

**Why this priority**: small per-turn costs found by the 11-20 QA sweep.

**Independent Test**: count the queries and columns the preamble reads; count app renders during a burst of 50 thinking frames.

**Acceptance Scenarios**:

1. **Given** a workspace with saved settings, **When** a turn builds its preamble, **Then** it reads main class and main spec only, from the caller's workspace only, with no onboarding query.
2. **Given** a streaming turn, **When** 50 thinking frames arrive, **Then** the app and the message list do not re-render, and the status line shows the latest thought.

### Edge Cases

- Status or interim text with HTML, markdown links or images, a `<script>` tag, zero-width or bidi-override characters: rendered as plain text, controls removed, clamped to the status cap without splitting a character.
- A client sending a frame typed `thinking` or `interim`: rejected as an invalid message, nothing stored, no turn started.
- Another workspace's settings row: never read by the preamble.
- A server restart mid-turn (nothing stored): the browser still keeps its local partial (unchanged sc-376 behaviour).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The chat socket MUST drop retracted text from the turn's answer before it sends the retraction to the browser, so no way the turn ends (cancel, drop, error) can store it.
- **FR-002**: When a turn ends by a connection drop after a retraction with no answer text kept, the system MUST store a partial "(no response)" message for it, so the reconnecting browser shows the stored state instead of its local copy.
- **FR-003**: The browser MUST show the `model_retry` / `model_fallback` label in the status line whether or not spell cards exist, until the next status event of the turn.
- **FR-004**: The socket MUST send retry frames with finite, non-negative wait and attempt numbers, so every frame is valid data for the browser.
- **FR-005**: The browser MUST render all status text (thought, interim, retry and fallback labels) as plain text, with bidi and zero-width controls removed, cut to 120 characters on a character boundary.
- **FR-006**: The turn preamble MUST read only main class and main spec from the caller's workspace settings, with no other settings field and no onboarding query.
- **FR-007**: The live status (label, thought line, last-event time) MUST live outside the app's state so that a status update re-renders only the live message.
- **FR-008**: The status frame shapes MUST stay as in `contract:chat-status-records`.

### Key Entities

- **Partial answer**: the agent message stored with status `partial` when a turn ends early; holds only answer text kept after the last retraction, or "(no response)" after a drop that kept none.
- **Live turn status**: transient, browser-only: the status label, the thought line, a model notice (retry/fallback label) and the time of the last turn event. Never stored.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In every scripted early end of a retracting turn (cancel during the retraction, cancel during the save, drop during or after the retraction), stored text = reloaded text, and it contains no retracted text.
- **SC-002**: A retry or fallback notice is visible in 100% of turns where one is sent, with or without spell cards.
- **SC-003**: 50 thinking frames cause 0 re-renders of the app and of the message list.
- **SC-004**: The preamble's settings read selects 2 fields from 1 table, 1 query per turn (was a whole row plus an onboarding query).
- **SC-005**: No per-frame database write: a turn with 50 thinking frames opens as many database scopes as one with none.

## Assumptions

- The PDF export is rendered server-side from stored messages, so "stored = PDF" holds once stored is right.
- The runner (Vera's 084) decides when retraction and status records are sent; this feature changes only how the socket and the browser treat them.
- A server restart mid-turn stays out of scope: nothing is stored, and the browser keeps its local partial (sc-376).
- "(no response)" is the existing wording for a turn without an answer; a constant 13-character placeholder is not counted against "a stored partial is never larger than the answer tokens it keeps".
