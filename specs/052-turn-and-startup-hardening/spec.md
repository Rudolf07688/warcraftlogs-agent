# Feature Specification: Turn and startup hardening

**Feature Branch**: `052-turn-and-startup-hardening`
**Created**: 2026-11-02
**Status**: Draft
**Input**: Sprint 2026-11-02 stream C: seven small, independent stories (sc-355, sc-332, sc-352,
sc-357, sc-356, sc-270, sc-297), each with its own acceptance criteria from the product owner's
brief.

## Clarifications

### Session 2026-11-02

- Q: What identifies a "turn" for the breaker, and what about reads outside a chat turn? → A: The chat turn's own accounting object; reads outside any turn (pre-fetch, background jobs) share one "no turn" bucket that counts as one turn.
- Q: When does the shared breaker open on timeouts? → A: At least 3 timeouts inside a 60 s window, from at least 2 distinct turns, and timeouts at least half of the window's answered probes (successes no longer reset a count).
- Q: How are a single turn's probes capped? → A: A turn with 3 timeouts in the window skips the store for the rest of the window (its in-flight probes finish).
- Q: Investigate limit default and order? → A: 5 per user per minute (`WCL_INVESTIGATE_PER_MINUTE`), checked before the 404 rule so it reveals nothing.
- Q: Unshareable-load joiner: change the code or the 047 spec? → A: The code: the joiner's own reload decides how it counts, as the 047 edge case says.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One busy turn doesn't switch stored data off for everyone (sc-355, P1)

A player's turn fires many stored-data reads at once. Today three of them timing out together
switch the stored data off for every workspace for 30 s, while a store that is slow for most
reads but answers one in between never switches off, so every slow read costs the full timeout.

**Independent Test**: drive the store source with a fake clock, a hanging store and two turns.

**Acceptance Scenarios**:

1. **Given** a closed breaker, **When** one turn's parallel reads all time out, **Then** the
   breaker stays closed (that turn alone stops probing for a while).
2. **Given** a store that times out on most reads within the window, **When** an occasional read
   succeeds in between, **Then** the breaker still opens.
3. **Given** a closed breaker, **When** a connection error happens, **Then** it opens at once;
   **When** timeouts come from two or more turns inside the window, **Then** it opens.
4. **Given** an open breaker past its wait, **Then** the half-open trial behaves as before.

### User Story 2 - Probe counters per operation (sc-332, P2)

The operator decides whether to keep probing the store from live numbers. Totals hide which
report family hits; a per-operation split answers it.

**Acceptance Scenarios**:

1. **Given** probes of two operations, **When** the cache stats are read, **Then** the hit,
   miss, not-visible and timeout counts appear per operation name as well as in total.

### User Story 3 - Investigate is rate limited and its pre-fetch is careful (sc-352, P1)

**Acceptance Scenarios**:

1. **Given** a user over the per-user investigate limit, **When** they click investigate again,
   **Then** the answer is 429 and nothing is created or fetched.
2. **Given** the store breaker is open, **When** a raid is investigated, **Then** no pre-fetch
   starts (and asking whether it is open changes no breaker state).
3. **Given** the endpoint's transaction fails to commit, **Then** no pre-fetch was scheduled.

### User Story 4 - Turn accounting survives failures (sc-357, P1)

**Acceptance Scenarios**:

1. **Given** a turn whose setup fails after the turn opened (preamble or setup commit), **Then**
   the refresh actor is cleared and the turn is closed without being counted.
2. **Given** a turn that joins a load marked unshareable, **When** its own reload is answered
   locally, **Then** the turn counts as local (the 047 edge case: its own load decides).
3. **Given** the final save fails, **Then** the client gets the turn's error frame, the turn
   ends and no exception escapes the turn.

### User Story 5 - No silent start on the dev secret (sc-356, P1)

**Acceptance Scenarios**:

1. **Given** the secret key is the dev default and the public site is not localhost or
   127.0.0.1, **When** the app starts, **Then** startup fails with a clear message.
2. **Given** local dev or the test suite, **Then** the app starts without extra setup.
3. **Given** insecure defaults in use (secret key, database URL), **Then** one warning names each,
   without printing a secret value.

### User Story 6 - Cheaper tenant scope and proxy parsing (sc-270, P3)

**Acceptance Scenarios**:

1. **Given** a tenant-scoped transaction on Postgres, **Then** both scope settings are set by one
   statement, and the RLS tests still pass.
2. **Given** a settings object, **Then** its trusted proxy list is parsed once, not per request.

### User Story 7 - "Both models busy" within the promised time (sc-297, P3)

**Acceptance Scenarios**:

1. **Given** both models remembered as rate limited, **When** requests themselves take time,
   **Then** the turn ends with "both models are busy" within 10 s plus at most one in-flight
   request (the budget counts requests and waits).

### Edge Cases

- Store reads outside a chat turn (the kickoff pre-fetch, background jobs) count as one shared
  "no turn" source: they alone can't open the breaker either, and they stop probing together.
- Concurrent probes during the half-open trial still skip; a cancelled trial frees the trial.
- A turn cancelled during setup (socket closed) is closed as not counted.
- The rate-limit 429 comes before the 404 rule, so it does not reveal which raids exist.
- A secret key explicitly set to the dev value counts as the dev default.
- Trusted proxies changed at runtime (tests) are re-parsed for the new value.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001** (sc-355): Timeouts from one turn MUST NOT open the shared breaker; timeouts from two
  or more turns inside the window, with timeouts the majority of the window's probes, MUST open
  it; a connection error MUST open it at once; a turn that has had the opening number of
  timeouts in the window MUST stop probing for the rest of that window.
- **FR-002** (sc-355): The half-open trial MUST behave as before.
- **FR-003** (sc-332): Probe outcomes MUST be counted per WCL operation name and in total and
  exposed by the cache-stats endpoint.
- **FR-004** (sc-352): Investigate MUST have a configurable per-user per-minute limit answering 429.
- **FR-005** (sc-352): The pre-fetch MUST NOT be scheduled while the breaker is open, checked
  without changing breaker state, and MUST be scheduled only after the endpoint's commit.
- **FR-006** (sc-357): The refresh actor MUST be reset in a `finally`; a turn whose setup fails
  MUST be closed as not counted; a joiner of an unshareable load MUST be counted by its own reload;
  a failing final save MUST be handled inside the turn's error handling; no new lock or wait.
- **FR-007** (sc-356): Startup MUST fail with the dev secret key unless the site is localhost or
  127.0.0.1, and MUST warn naming each insecure default in use, without values.
- **FR-008** (sc-270): Both scope settings MUST be set in one statement; trusted proxies MUST be
  parsed once per value.
- **FR-009** (sc-297): The both-limited budget MUST be a monotonic deadline covering requests and
  waits.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: One turn's burst of timeouts never switches stored data off for other workspaces.
- **SC-002**: A real outage still switches it off after at most three timeouts across two turns,
  or one connection error.
- **SC-003**: One user can start at most the configured number of investigations per minute.
- **SC-004**: "Both models busy" arrives within 10 s plus one request.
- **SC-005**: Every acceptance scenario above has a test that fails without the change.

## Assumptions

- The per-user investigate limit defaults to 5 per minute (a player clicks a few raids, not dozens).
- The breaker window is 60 s; "mostly" means at least half of the window's probes timed out.
- "Localhost" for the startup check means the hosts `localhost`, `127.0.0.1` and `::1`.
- The limiters are in-process, like the existing ones (one app instance).
