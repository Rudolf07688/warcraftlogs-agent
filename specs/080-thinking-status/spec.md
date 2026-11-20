# Feature Specification: Thinking status line and interim text as status

**Feature Branch**: `080-thinking-status`

**Created**: 2026-11-20

**Status**: Draft

**Input**: Stories sc-569 (live status line from thinking summaries) and sc-572, structural part
(tool troubleshooting leaks into the coach's answers). Brief:
`sprints/2026-11-20/briefs/080-thinking-status.md`.

## Clarifications

### Session 2026-11-20

- Q: When is streamed text known to be interim, and what does the retraction drop? → A: At the round's first new tool call (or, for text after a call, at the round's tool result); the `interim` event means "all answer text streamed so far was progress", since any earlier text was already retracted at its own tool call. Browser and server both clear their whole accumulated answer (scope:080:interim-segment).
- Q: What does a turn interrupted during a text segment save? → A: Exactly what the live view held: the unretracted segment, as a `partial` message (never indexed); retracted text is never saved (scope:080:partial-save).
- Q: Which turns get the new events? → A: Chat turns only (`user_id != USER_ID`); greeting, guide jobs and evals yield today's records unchanged, including the sc-302 paragraph join (scope:080:chat-only).
- Q: Which thought text becomes the status, and when is the generic line shown? → A: The first sentence of the latest thought paragraph of the current model call (a markdown heading line counts as a sentence; a still-open paragraph counts once it has a sentence end or 80 characters); the generic "Thinking… Ns" shows when no status text arrived since the last tool result, no tool is casting and no turn event came for 3 s, counting from that last event (scope:080:status-line).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See what the coach is doing between tool rounds (Priority: P1)

A player asks a question that needs several lookups. Between lookup rounds the model thinks for
17–68 s. Today the chat looks frozen in those gaps. With this feature, a one-line status under the
spell cards shows what the coach is thinking about (the first sentence of its latest thinking
summary), or, when the model sends no summary, "Thinking…" with the seconds waited so far.

**Why this priority**: The owner's direct complaint; the gaps make the app look broken.

**Independent Test**: Feed a turn whose model streams thought summaries between tool rounds; the
live view shows the status line, updated at most about once a second, and it disappears as soon
as the answer starts; the saved answer contains none of it.

**Acceptance Scenarios**:

1. **Given** a turn in a tool round's aftermath, **When** the model streams a thought summary,
   **Then** the chat shows its first sentence (about 80 characters at most), as plain transient
   text under the spell cards.
2. **Given** the model streams many summary chunks within a second, **When** they arrive,
   **Then** the status changes at most about once per second.
3. **Given** the answer text has started, **When** a further thought arrives, **Then** no status
   line is shown and none is sent.
4. **Given** a model that sends no summaries, **When** nothing arrives for about 3 s and no tool
   is running, **Then** the chat shows "Thinking… Ns" with the seconds counting up.
5. **Given** a finished turn, **When** the chat is reloaded, **Then** no thought text appears
   anywhere in it.

---

### User Story 2 - The kept answer starts at the verdict (Priority: P1)

Text the model writes before it calls a tool ("Warcraft Logs is throwing errors… I'll retry…") is
progress, not answer. While the turn runs it is shown as the transient status line; the answer the
player keeps (live and after reload) is only the final text written after the last tool round.

**Why this priority**: sc-572: troubleshooting paragraphs with report codes and retry notes end
up in saved answers, the PDF report and the knowledge index.

**Independent Test**: Feed a turn "interim text → tool call → tool result → final text"; the
stored message equals the final text, equals what the live view shows at `done`, and the interim
text was shown only as status.

**Acceptance Scenarios**:

1. **Given** a turn whose model writes text and then calls a tool, **When** the call starts,
   **Then** the text leaves the answer area and its first sentence shows as the status line.
2. **Given** that turn completes, **When** it is saved, **Then** the stored answer is only the
   final round's text, and the knowledge index receives only that text.
3. **Given** that turn, **When** the chat is reloaded, **Then** it shows the same answer as the
   live view did at the end of the turn.
4. **Given** a turn interrupted (superseded or socket dropped) while text is streaming, **When**
   its partial is saved, **Then** it saves exactly what the live view showed at that moment
   (text already retracted as interim is never saved).

---

### Edge Cases

- Thought text containing HTML, markdown links, bold, code fences: shown as inert plain text
  without markup characters turning into formatting or elements.
- A 10,000-character thought with no sentence end: the status is capped (about 80 characters).
- Newlines, control characters, ANSI escapes and bidi overrides in a thought: removed before
  the text is sent.
- A thought arriving after the final answer started: never shown.
- Thought parts from the web-search sub-agent: never shown.
- Interim text with report codes, source ids and "retry" lines: never in the stored message or
  the knowledge index.
- A client sending a frame of the new types to the server: ignored as a chat turn (rejected as an
  invalid message), nothing echoed.
- Greeting, guide jobs and evals that share the runner: output unchanged.
- A turn whose interim text is followed by tools and then no answer: the no-answer message is
  the whole answer (no leftover interim text before it).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: During a chat turn, the system MUST turn the model's thought summaries into a
  status line: the first sentence of the latest summary block, plain text, at most about 80
  characters.
- **FR-002**: Status updates MUST be throttled to at most about one per second per turn.
- **FR-003**: No status update MAY be sent or shown once the answer text of the current segment
  has started streaming; status MUST never be saved as part of the answer.
- **FR-004**: Status text MUST be stripped of control characters, ANSI escapes, bidi/format
  characters and markdown markers, length-capped on the server, and rendered as plain text and
  length-capped again in the browser.
- **FR-005**: When no status text is available, the live view MUST show "Thinking…" with the
  elapsed seconds after about 3 s without any turn event while no tool is running.
- **FR-006**: Text streamed in a round that then calls a tool MUST be retracted from the answer
  (live and server side alike) and shown only as the status line.
- **FR-007**: The stored answer of a completed turn MUST equal the answer the live view shows at
  `done`; the knowledge index MUST receive only that answer.
- **FR-008**: A turn interrupted while text streams MUST save as its partial exactly the text the
  live view held; retracted text is never saved.
- **FR-009**: Only chat turns get the new behaviour; turns run for the greeting, guide jobs and
  evals MUST yield exactly the records they yield today.
- **FR-010**: Thought parts from any author other than the chat agent MUST NOT produce status.
- **FR-011**: The new stream events MUST be documented in the runner's stream protocol and in the
  frontend frame types; frames of these types sent by a client MUST NOT start or alter a turn.
- **FR-012**: The status line MUST work for both Gemini and Claude thought summaries (Claude per
  `contract:claude-thinking-summaries`).

### Key Entities

- **Thinking event**: transient, server → client; one plain-text status line.
- **Interim event**: transient, server → client; "the answer text streamed so far was progress":
  drop it from the answer, show its first sentence as status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a turn with tool rounds, no gap longer than about 3 s passes without a visible
  status (thought line, tool card or "Thinking… Ns").
- **SC-002**: 100% of completed turns store exactly the final round's text; zero stored answers
  contain interim text.
- **SC-003**: Reloading a chat shows the same answer text the live view showed, for every
  completed turn.
- **SC-004**: Status updates never exceed about one per second, and none appears after the
  answer starts.

## Assumptions

- Thought summaries arrive as streamed `thought` parts on both providers (Vera's "as built" on
  `contract:claude-thinking-summaries`: Claude streams thinking deltas as partial thought parts,
  then a final aggregated thought).
- Within one model call, text precedes the function calls; text written after a call in the same
  round is also treated as interim (retracted when the round's tool result arrives).
- The architecture page on streaming is updated in the close-out docs pass, not here.
- The prompt line telling the model to state tool failures once (sc-572 prompt AC) is Nils's
  (082), not part of this feature.
