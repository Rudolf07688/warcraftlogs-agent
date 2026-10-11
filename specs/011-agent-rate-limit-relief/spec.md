# Feature Specification: Agent Rate-Limit Relief

**Feature Branch**: `011-agent-rate-limit-relief`

**Created**: 2026-10-11

**Status**: Draft

**Input**: User description: "One other "side-win" thing that I want to add as a last small update: The agent calls a lot of tools, especially on the first question, this causes me to hit the models' rate limit quickly. Can do something small to alleviate this pain? It might just be we update the prompt and add retry with backoff on the native sdk settings - or whatever you would recommend"

## Overview

A player's first question in a chat, and especially the one-click "investigate this raid"
flow, makes the coaching agent gather evidence from many lookups. Every round of lookups
costs another request to the AI model, so a single broad question can burn through the
model provider's per-minute allowance. When that happens today the whole turn aborts with
a raw technical error, the evidence already gathered is thrown away, and the player has to
guess that waiting a moment and resending might work.

This update is deliberately small and has two halves. First, a turn must survive a
temporary rate limit: the app waits and retries on the player's behalf, tells them it is
doing so, and only gives up after a bounded wait with a plain-language message. Second, the
agent must need fewer model requests to answer a broad first question: it gathers the
evidence for an investigation in a small number of well-batched rounds instead of a long
chain of one-at-a-time lookups, and it stops gathering once it has enough. Secondary
model calls that are not the answer itself (the greeting and the follow-up question
suggestions) must never fail a turn or compete with it when the allowance is tight.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A rate-limited turn recovers instead of failing (Priority: P1)

A player asks a broad question or clicks "investigate" on a raid. Midway through, the
model provider refuses a request because the per-minute allowance is used up. Instead of
an error, the player sees the agent's status change to a "busy, retrying" message, the
app waits and tries again, and the answer arrives a little later. If the allowance stays
exhausted for longer than the app is willing to wait, the player gets a short, specific
message saying the model is rate-limited and to try again in about a minute, not a raw
technical error.

**Why this priority**: This is the pain the user described. It turns a hard failure into
a short delay and is independently valuable even if nothing else ships.

**Independent Test**: Simulate the provider refusing requests for 20 seconds in the
middle of a turn. The turn completes with a correct answer, the status showed a retrying
message during the wait, and no error was shown. Simulate refusals lasting longer than
the wait budget: the turn ends with the rate-limit message and the conversation remains
usable for the next message.

**Acceptance Scenarios**:

1. **Given** a turn in progress, **When** the provider refuses a request as rate-limited
   and accepts the retry a few seconds later, **Then** the turn completes normally, the
   player saw a "retrying" status while waiting, and no error message appears.
2. **Given** a turn in progress, **When** the provider keeps refusing for longer than the
   wait budget, **Then** the turn ends with a plain-language message naming the cause
   (model rate limit) and suggesting to try again shortly; no stack trace or provider
   wording is shown.
3. **Given** a provider failure that is not a rate limit (invalid request, outage),
   **When** it occurs, **Then** the app does not retry on the player's behalf and reports
   it as today, so genuine errors are not hidden behind delays.
4. **Given** the retry wait is in progress, **When** the player looks at the chat,
   **Then** the composer stays disabled and the spell cards for already-finished lookups
   remain visible; nothing already gathered disappears.
5. **Given** a rate-limited turn that ultimately fails, **When** the player sends the
   same question again a minute later, **Then** it works, and the failed attempt did not
   leave a half-written reply in the conversation history.

---

### User Story 2 - A broad first question needs fewer model requests (Priority: P2)

A player clicks "investigate this raid" or asks an open first question such as "how did
we do on this report?". The agent plans its evidence gathering up front, issues the
independent lookups of each stage together in one round, stops gathering once the
question is answerable, and answers. The number of model requests for the same question
drops noticeably compared with today, so the per-minute allowance is hit far less often in
the first place.

**Why this priority**: Retrying treats the symptom; fewer requests treat the cause. It is
second only because it depends on steering the agent, which is less deterministic than
the retry behaviour.

**Independent Test**: Run the raid-investigation kickoff on a fixed report with each
supported model before and after the change, counting model requests per turn. The median
count drops by at least a third and the answer still covers the same bosses and headline
findings.

**Acceptance Scenarios**:

1. **Given** the raid-investigation kickoff on a report with several bosses, **When** the
   agent gathers evidence, **Then** lookups that do not depend on each other (for
   example, one per boss) are issued together in the same round rather than one per
   round.
2. **Given** an open first question, **When** the agent has enough evidence to answer
   the headline question, **Then** it answers rather than continuing to gather
   supporting detail that was not asked for.
3. **Given** a turn that has already used a configured number of lookup rounds,
   **When** the agent would start another, **Then** it is steered to answer with the
   evidence it has and to say what it did not get to, instead of continuing.
4. **Given** the same question asked twice in one conversation, **When** the second
   turn runs, **Then** the agent reuses evidence already in the conversation rather than
   re-fetching it.

---

### User Story 3 - Secondary model calls never cost the player a turn (Priority: P3)

Beyond the answer itself, the app makes small extra model calls: the welcome greeting
and the three follow-up question suggestions after each reply. When the allowance is
tight these must quietly step aside: a reply still arrives without suggestions, a new chat
opens without a greeting, and neither ever surfaces an error or delays the answer.

**Why this priority**: These calls are invisible helpers; they should never compete with
the thing the player actually asked for. Small, low-risk change.

**Independent Test**: With the provider refusing requests, open a new chat and send a
message whose answer was already produced. The chat opens (no greeting), the reply shows
with no follow-up chips, and no error is shown for either.

**Acceptance Scenarios**:

1. **Given** the follow-up suggestion call is rate-limited, **When** a reply completes,
   **Then** the reply is shown immediately with no suggestions and no error.
2. **Given** the greeting call is rate-limited, **When** a new chat opens, **Then** the
   chat opens empty with no error and the player can type at once.
3. **Given** a turn's answer is being retried after a rate limit, **When** the retry
   wait is in progress, **Then** no secondary call is started that would compete with it.

---

### Edge Cases

- The provider's refusal says how long to wait: the app honours that hint rather than
  its own schedule, within the overall wait budget.
- The player disconnects or closes the chat during a retry wait: the turn is abandoned,
  no further retries are made, and nothing partial is saved as a reply.
- The rate limit hits on the very first request of a turn (before any lookups): same
  retrying status and same bounded wait.
- Two players in the same deployment hit the limit at once: each sees their own retrying
  status; one player's retries do not cancel the other's turn.
- A lookup (not the model) is what fails, for example the Warcraft Logs API budget: that
  keeps today's behaviour, where the agent reads the failure and answers with what it
  has.
- The configured lookup-round cap is reached on a legitimately deep question: the answer
  states plainly which parts were not investigated rather than silently omitting them.
- The same evidence-gathering steering must not make short, specific questions slower or
  more verbose: a question that needs one lookup still makes one lookup.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When the model provider refuses a request because of rate limiting during
  a turn, the system MUST automatically wait and retry that request with increasing
  delays, up to a configured total wait budget, before treating it as a failure.
- **FR-002**: The retry behaviour MUST apply only to rate-limit (and equivalent
  "temporarily overloaded") refusals; other provider errors MUST fail immediately as
  today.
- **FR-003**: While a retry wait is in progress the player MUST see a distinct status
  message indicating the model is busy and the app is retrying; already-shown lookup
  results MUST remain visible.
- **FR-004**: If the wait budget is exhausted, the turn MUST end with a plain-language
  error naming the cause as a model rate limit and advising to try again shortly; raw
  provider wording and stack traces MUST NOT be shown.
- **FR-005**: A turn that fails after exhausting the budget MUST NOT persist a partial
  reply; the player's message stays in the conversation and can be resent.
- **FR-006**: The wait budget, the maximum number of attempts and the lookup-round cap
  MUST be configurable by the operator without a code change, with sensible defaults
  (see Assumptions).
- **FR-007**: When the provider's refusal carries a wait hint, the system MUST respect
  it, bounded by the overall wait budget.
- **FR-008**: The agent's guidance MUST direct it to plan evidence gathering for broad
  questions and the raid-investigation kickoff in a small number of stages, issuing all
  independent lookups of a stage together in one round.
- **FR-009**: The agent's guidance MUST direct it to stop gathering and answer once the
  question asked is answerable, and to reuse evidence already present in the
  conversation instead of re-fetching it.
- **FR-010**: The raid-investigation kickoff wording MUST ask for a bounded overview
  (headline findings per boss) rather than an open-ended investigation, so that the
  first turn's evidence gathering is naturally limited.
- **FR-011**: When a turn reaches the configured lookup-round cap, the agent MUST be
  steered to answer with the evidence it has and state what was not investigated.
- **FR-012**: The greeting and follow-up suggestion calls MUST be skipped silently when
  rate-limited (no retry wait, no error shown), and MUST never delay or fail the turn's
  answer.
- **FR-013**: The system MUST record, per turn, the number of model requests, the number
  of lookup rounds and the number of rate-limit retries, so the operator can verify the
  improvement from logs.
- **FR-014**: Behaviour for short, specific questions MUST be unchanged: a question that
  needs a single lookup still makes a single lookup and answers at the same length as
  today.

### Key Entities

- **Turn attempt record**: the per-turn tally of model requests, lookup rounds and
  rate-limit retries, plus the final outcome (answered, failed after budget, abandoned).
  Operational data only, not shown to players.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the provider refusing requests for up to 30 seconds mid-turn, 100% of
  turns complete with a correct answer and zero error messages shown.
- **SC-002**: For the raid-investigation kickoff on a fixed set of three reports, the
  median number of model requests per turn drops by at least one third compared with the
  current build, on every supported model, with the same bosses and headline findings
  covered.
- **SC-003**: Zero rate-limit failures expose provider wording or stack traces to the
  player; every such failure uses the plain-language message.
- **SC-004**: A player whose turn is retried sees the "busy, retrying" status within 2
  seconds of the first refusal.
- **SC-005**: Across a manual session of ten broad first questions on the default model,
  at most one ends in a rate-limit failure (previously several did).
- **SC-006**: Short, specific questions show no increase in answer time or lookups
  compared with the current build.
- **SC-007**: All existing automated checks pass, and the greeting and follow-up
  suggestions degrade silently in 100% of simulated rate-limit cases.

## Assumptions

- Rate limiting comes from the AI model provider's per-minute request allowance, not
  from the Warcraft Logs API, whose budget the agent already checks and reports.
- Defaults unless the operator overrides them: up to 5 attempts, delays growing from
  roughly 2 seconds to a ceiling of roughly 30 seconds, a total wait budget of about 90
  seconds per request, and a lookup-round cap of 6 rounds per turn. These are the
  operator-tunable values in FR-006.
- The retry is applied at the model request level, so partially gathered lookup results
  within the turn are kept; the turn does not restart from scratch.
- Reducing requests is achieved by steering the agent (its guidance and the kickoff
  wording) and a round cap, not by removing any lookup capability or changing what the
  agent is allowed to do.
- The "busy, retrying" status is shown through the existing in-turn status line, like the
  existing "searching the web" status, so no new UI surface is needed.
- Model requests made at startup to validate the selectable models are few and
  one-off; they are out of scope.
- No change to conversation storage, authentication, or the frontend's message format
  beyond the new status text is expected.
