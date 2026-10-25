# Feature Specification: Rate-Limit Fallback to the Sibling Model

**Feature Branch**: `021-ratelimit-fallback`

**Created**: 2026-10-25

**Status**: Draft

**Input**: User description: "Feature 021 (sc-164): when a chat turn's model is still rate limited (429/RESOURCE_EXHAUSTED/overloaded) after the existing feature 011 retry policy, the turn continues on the other discovered model of the same class (feature 016 classes: Gemini pro/flash/flash-lite serve two versions; if the turn is on the second model, it switches to the first). At most one switch per turn attempt, so the fallback cannot loop. If both models of the class are rate limited, or the class has only one model (Claude classes today, decision 7), the user gets a clear in-chat "try again shortly" message; the agent loop and the socket survive and the next message works. When a switch happened the user can see which model answered (a notice in the chat). A half-streamed reply must never be duplicated in stored history. Tests cover the Gemini and the Anthropic call paths with fake 429s; no live Vertex call in CI. The title hook (019) and other generate_with_retry callers must behave as before."

## Overview

Feature 011 made a chat turn survive a short rate limit: the app waits, retries and tells
the player it is doing so, and gives up with a plain "try again in about a minute" message
once its wait budget is spent. Feature 016 serves the two newest working versions of each
model class (for example two Gemini flash versions). Rate-limit quota is tracked per model
version, so when one version's allowance is used up, its sibling in the same class usually
still has room.

This feature uses that: when the model a turn is using stays rate limited after the
existing retries, the turn carries on with the other version of the same class instead of
failing. The player sees a short notice saying which model answered. Only when the sibling
is also rate limited, or the class has no sibling, does the player get the "try again
shortly" message, and even then the chat stays usable for the next message.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A rate-limited turn finishes on the sibling model (Priority: P1)

A player chats with a Gemini flash model. Midway through a turn the provider keeps
refusing that model as rate limited, and the app's retries run out. Instead of the
"rate-limited, try again" error, the turn carries on with the other flash version the app
serves, and the answer arrives. Lookups already done in the turn are not repeated, and the
part of the answer already shown is not shown or stored twice.

**Why this priority**: This is the story's core value. A single model's quota no longer
stalls the chat.

**Independent Test**: With two models in a class, make the first one refuse every request
as rate limited. A turn on it completes with an answer from the second, no error is shown,
and the stored reply appears exactly once.

**Acceptance Scenarios**:

1. **Given** a turn on the newer model of a two-model class, **When** that model is still
   rate limited after the retry policy, **Then** the turn continues on the older model of
   the same class and completes normally.
2. **Given** a turn on the older (second) model of a two-model class, **When** it is still
   rate limited after the retry policy, **Then** the turn switches to the newer (first)
   model of the class.
3. **Given** a turn that already streamed part of its answer and ran lookups before the
   rate limit, **When** the turn switches model, **Then** the lookups are not run again,
   and the stored reply contains each streamed part exactly once.
4. **Given** a provider failure that is not a rate limit, **When** it occurs, **Then** no
   model switch happens and the error is reported as today.

---

### User Story 2 - The player is told when both models are busy (Priority: P1)

The sibling model is rate limited too, or the class has only one model (the Claude classes
today). The player gets a clear in-chat message to try again shortly. The chat, its
connection and its history stay intact, and the next message is processed normally.

**Why this priority**: Without a bounded end, a fallback could loop or hang. The player
must always get an answer or a clear message.

**Independent Test**: Make both models of a class refuse every request. The turn ends with
the "Both <class> models …" message after at most one switch, and a following message (with
the provider accepting again) gets a normal answer on the same connection.

**Acceptance Scenarios**:

1. **Given** a turn whose model and its sibling are both rate limited, **When** the retry
   policy is exhausted on the sibling, **Then** the player sees "Both <class> models are
   rate-limited right now. Please try again in about a minute." and the turn makes no
   further switch.
2. **Given** a turn on a model whose class has only one served model (e.g. a Claude class),
   **When** it is still rate limited after the retry policy, **Then** the player sees the
   feature 011 message unchanged, straight away, with no switch.
3. **Given** a turn that ended with a rate-limit message, **When** the player
   sends another message, **Then** it is processed normally on the same connection, and
   no half-written reply from the failed turn is in the conversation history.

---

### User Story 3 - The player sees which model answered (Priority: P2)

When a switch happens, the chat shows a short notice naming the model that answered and
the one that was rate limited, so the player knows why the answer may read differently.

**Why this priority**: Transparency. The turn works without it, but a silent model change
would be confusing when the dropdown still shows the original model.

**Independent Test**: Force a switch. The chat shows a notice naming both models while the
answer streams, and the notice stays next to that answer after the turn completes.

**Acceptance Scenarios**:

1. **Given** a turn that switched model, **When** the answer is shown, **Then** a notice in
   the chat names the model that answered and the model that was rate limited.
2. **Given** a turn that did not switch, **When** the answer is shown, **Then** no notice
   appears.

---

### Edge Cases

- The rate limit hits after part of a model response has already streamed (mid-stream):
  no switch is made for that response, since a retry would duplicate text; the turn fails
  exactly as it does today (the partial reply is kept once and reported as an agent
  error). Changing that is out of scope.
- The sibling answers but later in the same turn is rate limited as well: the turn has
  already used its one switch, so the player gets the "Both <class> models …" message.
- After a switch, every later model request of the same turn goes to the sibling; the turn
  does not bounce back and forth.
- A class served by three or more versions (a larger configured keep count): the newest
  model falls back to the second newest; any other model falls back to the newest.
- Model discovery is degraded or in static mode and the served list has no second model of
  the class: there is no sibling, so the player gets the feature 011 message.
- Helper calls (greeting, follow-up suggestions, conversation titles, guide pipeline,
  guild summaries) keep today's behaviour: they never switch models.
- The player closes the connection during a switch: the turn is abandoned as today, and
  any streamed text is kept as a partial reply exactly once.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When a chat turn's model request is still rate limited after the existing
  retry policy (feature 011), and nothing of that request's response has streamed yet,
  the system MUST continue the turn on the sibling model of the same class.
- **FR-002**: The sibling MUST be another currently served model of the same publisher and
  class. For the class's newest served model it is the next newest; for any other model of
  the class it is the newest.
- **FR-003**: A turn MUST switch model at most once. After the switch, all remaining
  model requests of that turn MUST go to the sibling.
- **FR-004**: When there is no sibling, the system MUST end the turn with the feature 011
  message unchanged ("The model is rate-limited right now. Please try again in about a
  minute."). When a switch was made and the sibling is also still rate limited after the
  retry policy, it MUST end the turn with "Both <class> models are rate-limited right
  now. Please try again in about a minute." (<class> as in "Gemini flash"). Both use the
  error code `rate_limited` and contain no provider wording.
- **FR-005**: After a turn ends with that message, the connection and the conversation
  MUST stay usable, and the next message MUST be processed normally.
- **FR-006**: A switch MUST NOT re-run lookups already done in the turn, and MUST NOT
  store or show any part of the reply twice.
- **FR-007**: When a switch happens, the player MUST see a notice in the chat naming the
  model that answered and the model that was rate limited: a status line while the switch
  happens, then a notice line under the reply that answered. The notice lives in the live
  session only; it is not stored, so a reload does not show it.
- **FR-008**: The model selector MUST keep showing the player's chosen model after a
  switch, and the next turn MUST start on the chosen model again (with its own single
  switch available).
- **FR-009**: Helper model calls outside the chat turn (greeting, follow-up suggestions,
  conversation titles, guide pipeline, guild summaries) MUST behave exactly as before and
  never switch models.
- **FR-010**: Non-rate-limit failures MUST NOT trigger a switch.
- **FR-011**: The per-turn stats log line MUST record whether a switch happened and to
  which model.
- **FR-012**: The fallback MUST follow one rule for Gemini and Anthropic (Claude) models:
  the sibling is another served model of the same publisher and class. A Claude class
  served by one model (today's configuration) has no sibling and goes straight to the
  feature 011 message (decision 7).

### Key Entities

- **Model class**: a publisher plus a class name (Gemini pro / flash / flash-lite, Claude
  haiku / sonnet / opus), served as an ordered list of versions, newest first.
- **Sibling model**: the other served version of the same class that a turn may switch
  to once.
- **Fallback notice**: what the player sees after a switch: the model that was rate
  limited and the model that answered.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With one model of a two-model class refusing every request as rate limited,
  100% of turns on that model complete with an answer from the sibling.
- **SC-002**: No turn ever switches model more than once (checked by tests that keep both
  models refusing).
- **SC-003**: In every switch scenario, the stored reply contains each streamed part
  exactly once and no lookup of the turn runs twice.
- **SC-004**: After a "try again shortly" ending, the next message on the same connection
  is answered normally in 100% of test runs.
- **SC-005**: Every switch shows the player a notice naming both models.
- **SC-006**: Helper calls (titles, suggestions, greeting, guide pipeline) show no change
  in behaviour: their existing tests pass unchanged.
- **SC-007** *(product owner acceptance check 1)*: After a switch, the conversation's
  stored model history holds the turn exactly once: one user message, each tool call and
  result once, and the answer once. A test shows this with a real session store.
- **SC-008** *(acceptance check 2)*: The conversation-title job (feature 019) and the guide
  pipeline behave exactly as before. Their existing tests pass with no edits, and they
  never switch models.
- **SC-009** *(acceptance check 3)*: Both the Gemini and the Anthropic call paths are
  tested with fake rate-limit errors (a switch case and a no-switch case each), with no
  live provider call.
- **SC-010**: Both end-of-turn messages are tested: the feature 011 message when there is
  no sibling, and the "Both <class> models …" message when the sibling was tried.

## Assumptions

- Rate-limit quota is enforced per model version, so a sibling version often still has
  room when the current one is exhausted (feature 016's discovery treats quota per base
  model in the same way).
- The served model list keeps each class's versions newest first (feature 016), in both
  catalog and static discovery modes; a static-mode id is placed in its class by the same
  naming rules discovery uses.
- The sibling needs no extra startup probe: it is already a served model, so it passed
  discovery.
- The feature 011 wording is reused unchanged when there is no sibling; a busy sibling
  gets the distinct "Both <class> models …" message.
- Tests use fake rate-limit errors for both providers; no live provider call is needed.
- No database change: the fallback is a per-turn runtime decision.
