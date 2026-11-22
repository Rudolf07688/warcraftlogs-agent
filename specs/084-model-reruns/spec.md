# Feature Specification: Model re-runs and the runner (chat reliability)

**Feature Branch**: `084-model-reruns`

**Created**: 2026-11-22

**Status**: Draft

**Input**: Sprint 2026-11-22 brief 084: sc-586 (Gemini empty answers), sc-580 (Claude output budget and time), the runner items of sc-582 (thinking status edge cases).

## Clarifications

### Session 2026-11-22

- Q: How is the 180 s Claude call bound enforced (effort cap, wall-clock deadline or both)? → A: A wall-clock deadline per streamed Claude model request (each rate-limit attempt gets its own), checked between chunks and while waiting for the next one; the chat effort stays as it is and only the re-run drops to low (scope:084:claude-call-time).
- Q: What happens when the bound cuts a call after answer text has streamed? → A: The text streamed so far becomes the call's final response (finish reason max tokens) and no re-run follows (scope:084:time-cut-after-text).
- Q: Does the empty-stop re-run apply to Claude too? → A: No, Gemini only, as the ticket found it; Claude's no-answer case stays with its budget re-run (scope:084:empty-stop-gemini).
- Q: When is a short retracted answer kept (retraction-guard residual)? → A: Not in 084. It has the same shape as progress text followed by a call and a short answer; a length rule would bring troubleshooting text back as answer (two pinned 080 tests). Backlog: backlog:retraction-short-answer (scope:084:short-answer-restore, revised).
- Q: Which counter does a time cut-off use? → A: `budget_retries` (it is handled like the budget cut-off); the warning line names the cause (scope:084:time-cut-counter).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A Gemini turn that comes back empty is asked once more (Priority: P1)

A player asks "is frost mage difficult?" in a fresh chat on Gemini. Sometimes the model ends its
call with a normal stop but no text, no tool call and no output tokens, and the player sees "I
couldn't put an answer together". The app now asks the model once more before giving up.

**Why this priority**: the owner's first priority; 2 of 7 live Gemini turns failed this way.

**Independent Test**: a fake Gemini model that returns one empty stop, then an answer: the player
gets the answer, and the turn's stats show one empty re-run.

**Acceptance Scenarios**:

1. **Given** a Gemini call that ends with a stop, no answer text, no tool call and 0 output tokens,
   **When** the turn runs, **Then** the call is made once more and its result is used.
2. **Given** the re-run is empty too, **When** the turn ends, **Then** the player sees the
   existing no-answer message (no third call).
3. **Given** a re-run happened, **When** the turn ends, **Then** the turn stats line shows
   `empty_retries=1`.

---

### User Story 2 - A Claude call never holds the chat for minutes (Priority: P2)

A Claude call that spends its whole output budget thinking can run 5-11 minutes. No single
streamed Claude chat call may run longer than 180 s, thinking included. A call cut at the bound
is handled like the thinking-only cut-off: one re-run at low effort, under the same bound.

**Why this priority**: cost and waiting time (sc-580 PERF Medium); the re-run counting closes a
round-cap gap (SEC-001).

**Independent Test**: a fake Claude stream that never ends (or keeps thinking past the bound):
it is cut at the bound, its stream is closed, and exactly one low-effort re-run follows.

**Acceptance Scenarios**:

1. **Given** a streamed Claude call still running at 180 s with only thinking so far, **When**
   the bound passes, **Then** its stream is closed and the call runs once more at low effort,
   under the same bound.
2. **Given** a call cut at 180 s after answer text had started, **When** the bound passes,
   **Then** the text streamed so far stands as the call's answer and no re-run follows (it would
   repeat the text).
3. **Given** any re-run (budget, time or empty stop), **When** the turn counts its lookup rounds,
   **Then** the re-run counts as a round toward the round cap.
4. **Given** a turn ends, **When** its stats line is logged, **Then** it shows `budget_retries`
   and `empty_retries`.

---

### User Story 3 - The status line and retraction behave at the edges (Priority: P3)

The live status line and the retraction of progress text (feature 080) have four edge cases:
a re-run splices two calls' thoughts (BUG-005); retracted text is lost when a turn ends with a
tool call still pending (BUG-006); a heading line in the model's thoughts runs into the next
sentence unless a blank line follows it (SPEC L1). The fourth, a short answer followed by a
gathering call and a short closing line (retraction-guard residual), is out of scope (see
Clarifications).

**Independent Test**: runner tests with fake event streams, one per edge case.

**Acceptance Scenarios**:

1. **Given** a call re-run after its thoughts streamed, **When** the re-run's thoughts arrive,
   **Then** the status line is built from the re-run's thoughts only.
2. **Given** a chat turn that retracted text and ends with a tool call never answered, **When**
   the turn ends, **Then** the retracted text comes back as answer text.
3. **Given** thought text "**Analyzing the deaths**\nI am comparing ...", **When** the status
   line is made, **Then** it is "Analyzing the deaths".

### Edge Cases

- A call that is both empty-stop and cut by time: at most one re-run per call, of either kind.
- A turn of several calls that each re-run: each re-run counts as a round; the round cap trips.
- A hung stream that sends nothing: cut at the bound all the same (no chunk needed to notice).
- A call cut while a tool call was streaming (no answer text): treated like thinking only.
- Background jobs (greeting, guide jobs, evals): get the same re-runs; no status records.
- Non-streamed Claude calls (CLI) keep their 16k output limit and no time bound.
- The rate-limit retry loop's 90 s wait budget is unchanged; the time bound applies to each
  model request, not to the waits between them.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A Gemini call whose final response is a stop with no answer text, no tool call and
  0 output tokens MUST be re-run once; its empty result is not passed on.
- **FR-002**: A streamed Claude chat call MUST be cut off at 180 s (thinking included), its stream
  closed, and handled like the thinking-only cut-off: one re-run at low effort under the same
  bound, unless answer text had already streamed (then that text stands, no re-run).
- **FR-003**: A model call MUST get at most one re-run, of any kind (thinking budget, time, empty stop).
- **FR-004**: Every re-run MUST count as a model request and so as a round toward the round cap.
- **FR-005**: The turn stats line MUST show `budget_retries` and `empty_retries`.
- **FR-006**: After a re-run, the status line MUST use only the re-run's thoughts.
- **FR-007**: A chat turn that ends without an answer MUST give back its retracted text, also when
  a tool call is still pending; the no-answer message stays limited to turns with no call pending.
- **FR-008**: A markdown heading line (`# ...` or a line that is wholly bold) MUST count as a
  sentence of its own, with or without a blank line after it.
- **FR-009**: (withdrawn: the retraction residual stays as it is; see Clarifications.)
- **FR-010**: The `thinking`, `interim`, `model_retry` and `model_fallback` record shapes MUST stay
  unchanged (contract:chat-status-records); only when they are sent may change.

### Key Entities

- **Turn stats**: per-turn tally; gains `empty_retries` next to `budget_retries`; both on the
  turn stats log line.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Live: the frost question in a fresh Gemini chat answers (re-run when the first call is empty).
- **SC-002**: No streamed Claude chat call runs longer than 180 s; a turn's worst case is two
  such calls per model request plus the unchanged rate-limit waits.
- **SC-003**: Re-runs are visible per turn in the logs (`budget_retries`, `empty_retries`).
- **SC-004**: Each runner edge case above has a test that fails on the base code and passes after.

## Assumptions

- The empty-stop re-run applies to Gemini only (the ticket's finding); Claude's no-answer case is
  covered by its budget re-run (079).
- The 180 s bound applies to streamed Claude calls only; Gemini calls are not bounded here.
- A time cut-off counts in `budget_retries` (it is handled like the budget cut-off).
- The claude history cache layout code is out of scope (feature 087).
