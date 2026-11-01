# Feature Specification: Clean-up and KB debt

**Feature Branch**: `047-cleanup-kb-debt`

**Created**: 2026-11-01

**Status**: Draft

**Input**: Sprint 2026-11-01b, stream B (brief `sprints/2026-11-01b/briefs/047-cleanup-kb-debt.md`).
Six small stories, one user story each; the product owner's acceptance criteria are the FRs.

## Clarifications

### Session 2026-11-01

Self-answered (tier M), each posted on the board as `clarify:047-<topic>`.

- Q: How does the suite switch `.env` off? → A: an explicit switch `WCL_LOAD_DOTENV` (default on),
  set to `0` by the test bootstrap before any app import; it gates both the dotenv load and the
  settings' env file (`clarify:047-dotenv`).
- Q: What opens the breaker? → A: a connection-class error at once, or N = 3 consecutive timeouts
  (a probe timeout or a pool wait); a success resets the count; a half-open trial that times out
  reopens it (`clarify:047-breaker`).
- Q: How is "our own summary row" proven, and what bounds the read? → A: the row's key must equal
  the key of the app's fixed summary query for the row's stored parameters, whose exact codes
  equal the row's codes; a partial index on summary rows by fetch time (migration 0020), a 2 s
  statement timeout, and a database-side projection of the needed fields (`clarify:047-lookup`).
- Q: Does waiting on another process's load count as external? → A: yes, always
  (`clarify:047-local-rate`).
- Q: Lock or retry for the message number? → A: lock the conversation row before numbering
  (`clarify:047-seq`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tests never read the real .env (sc-336, Priority: P1)

A developer runs the test suite in a checkout that holds the owner's `.env`. The suite must give
the same result as in a checkout without one, and must never pick up live provider settings (which
turned 21 tests red and made live model calls).

**Why this priority**: every other story is verified with the suite; a suite that reads live
settings can't be trusted and can cost money.

**Independent Test**: put a fake `.env` with sentinel values in the working tree; run the suite;
same counts as without it, and the guard test shows no sentinel in settings or the environment.

**Acceptance Scenarios**:

1. **Given** a `.env` with a sentinel value in the working directory, **When** the suite runs,
   **Then** neither the settings nor the process environment carry the sentinel.
2. **Given** the app started by docker, the dev server or the CLI, **When** it starts, **Then** it
   still loads `.env` as before.

---

### User Story 2 - A private report stays gone after a race (sc-322, Priority: P1)

A user makes a report private. A summary fetch sees it private while a table fetch for the same
report is still under way. The stored copy must not come back when the table answer arrives.

**Why this priority**: tenant visibility (security-core).

**Independent Test**: queue a table fetch requested before a summary that finds the report
private, written after it; the table row is not written and no tenant is served it.

**Acceptance Scenarios**:

1. **Given** a table fetch requested at T0 and a summary fetched at T1 > T0 that finds the report
   private, **When** the writer processes the summary and then the table fetch, **Then** the table
   row is not stored and the tenant that held a grant is not served it.
2. **Given** the 045 spec, **When** a reader checks FR-010, **Then** it describes the in-process
   tombstone exactly as built.

---

### User Story 3 - One slow read doesn't switch the stored data off (sc-323, Priority: P2)

A single slow read of stored data (or a brief wait for a database connection) must not make every
turn skip the stored data for 30 seconds.

**Independent Test**: breaker unit tests: one timeout keeps it closed; N consecutive timeouts open
it; one connection error opens it.

**Acceptance Scenarios**:

1. **Given** a closed breaker, **When** one probe times out, **Then** the next probe still runs.
2. **Given** a closed breaker, **When** N probes in a row time out, **Then** it opens.
3. **Given** a closed breaker, **When** a probe fails with a connection error, **Then** it opens.

---

### User Story 4 - "Reports stored for my character" is strict and cheap (sc-324, Priority: P2)

The agent asks which stored reports a character appears in. The lookup only uses rows written by
the app's own summary queries with exact report codes, is served by an index, is time-bounded,
and reads only the fields it needs.

**Independent Test**: seed a forged summary row (a hand-written query named like ours) and a row
with inexact codes; neither is ever listed. On Postgres, the lookup uses the index and returns
only the projected fields.

**Acceptance Scenarios**:

1. **Given** a stored row whose operation name says "summary" but whose request was not our fixed
   summary query, **When** the character lookup runs, **Then** that row is never used.
2. **Given** many stored rows, **When** the lookup runs on Postgres, **Then** it is served by an
   index, a statement timeout applies, and it reads a compact projection instead of whole payloads.

---

### User Story 5 - The local-answer rate is honest (sc-326, Priority: P3)

The owner reads the local-answer rate as the measure of the "80% without external calls" goal.
A turn that waited on someone else's Warcraft Logs load, or that called Warcraft Logs while its
preamble was built, must count as external.

**Independent Test**: two turns share one cache load that goes to WCL: both count external. A
turn whose preamble makes a WCL call counts external.

**Acceptance Scenarios**:

1. **Given** turn A loads a key from WCL and turn B joins that in-flight load, **When** both end,
   **Then** both count as external.
2. **Given** another process holds the load lock and turn B waits for its value, **When** B ends,
   **Then** B counts as external.
3. **Given** the turn preamble makes a WCL call, **When** the turn ends, **Then** it counts as
   external.

---

### User Story 6 - Chat messages never collide on their number (sc-255, Priority: P3)

Two messages added to one conversation at the same time both save, with distinct consecutive
numbers.

**Independent Test**: a real-Postgres test with two concurrent sessions adding to one
conversation; both succeed with seq n and n+1; the test fails on the old code.

**Acceptance Scenarios**:

1. **Given** a conversation with k messages, **When** two sessions add a message concurrently,
   **Then** both commit with seq k and k+1.

### Edge Cases

- A `.env` in a parent directory of the checkout (the dotenv search walks upwards) must be ignored
  by the suite too.
- A summary that finds several reports private tombstones each of them.
- A half-open breaker trial that times out reopens the breaker (it was just failing).
- A stored summary row with a padded or non-string code in its parameters is excluded.
- A cache load joined by a turn that was marked unshareable is reloaded by the joiner; its own
  load decides how it counts.
- A message added to a conversation of another tenant fails exactly as before.

## Requirements *(mandatory)*

### Functional Requirements

**sc-336**

- **FR-001**: The test suite MUST NOT load `.env`: no import-time dotenv load on any path the
  tests import, and the settings MUST ignore their env file under tests.
- **FR-002**: A guard test MUST show that with a sentinel `.env` in the working directory neither
  the settings nor the process environment contain the sentinel during the suite.
- **FR-003**: The suite MUST give the same result with and without a `.env` in the checkout
  (proven with a fake `.env`; the owner's real `.env` is never read).
- **FR-004**: The app (docker, dev server, CLI) MUST still load `.env` as before; the quickstart
  says where.

**sc-322**

- **FR-005**: Every gone/private signal, including a summary fetch that finds a report private,
  MUST tombstone the code, so a request already under way cannot write the row back.
- **FR-006**: `specs/045-local-data-reads/spec.md` FR-010 MUST describe the in-process tombstone
  as built (per process, TTL, cap, lost on restart, accepted for one uvicorn worker).
- **FR-007**: A test MUST reproduce the race and show the stale write is dropped and the old grant
  can't serve the row. No migration.

**sc-323**

- **FR-008**: A single timeout of a stored read, or a short wait for a pool connection, MUST NOT
  open the shared breaker; it opens on a connection error or on N = 3 consecutive timeouts.
- **FR-009**: Tests MUST cover: one slow read keeps it closed; N consecutive timeouts open it; a
  connection error opens it.

**sc-324**

- **FR-010**: The character lookup MUST select rows by a server-fixed set of operations and exact
  report codes only: a row is used only when its key is the key of the app's own fixed summary
  query for its stored parameters, and those parameters give exact codes equal to the row's codes.
  Nothing the model passes chooses the operation.
- **FR-011**: The lookup MUST be bounded: an index serves it, a statement timeout applies, and it
  reads only the needed fields (code, title, start time, zone name, actor names) instead of up to
  200 full payloads.
- **FR-012**: Tests MUST show a row with inexact codes or a non-allowed operation is never
  returned, and a Postgres test MUST show the bounded read.
- **FR-013**: The 039 guard test stays unchanged and green; visibility keeps its one definition
  (`fetch_visible_clause`).

**sc-326**

- **FR-014**: A turn that joined a shared in-flight load that went to WCL (same-process
  single-flight, or waited on another process's lock) MUST count as external.
- **FR-015**: WCL calls made while the turn preamble is built MUST count for that turn.
- **FR-016**: Tests for both.

**sc-255**

- **FR-017**: Two concurrent `add_message` calls on one conversation MUST both succeed with
  distinct consecutive `seq`.
- **FR-018**: A real-Postgres race test with two concurrent sessions MUST prove it and fail on the
  old code.
- **FR-019**: The SQLite path still works; tenant scoping and RLS of `add_message` are unchanged.

### Key Entities

- **Tombstone**: an in-process record "report X was seen gone or private at time T"; a fetch
  requested at or before T is not written.
- **Breaker**: process-wide state that keeps a failing stored-data read out of the hot path.
- **Stored summary row**: a stored response of the app's own report summary query.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The full suite gives identical pass/fail/skip counts with and without a `.env` in
  the checkout.
- **SC-002**: 0 stale writes of a report seen private in the race test.
- **SC-003**: A single slow read leaves stored data in use for the next turn (0 s skipped).
- **SC-004**: The character lookup returns per row a projection a fraction of the payload size,
  and never a forged or inexact row.
- **SC-005**: The local-answer rate counts 100% of turns that waited on a WCL load as external.
- **SC-006**: 0 failed message saves under concurrent adds to one conversation.

## Assumptions

- Under tests is signalled explicitly by the test bootstrap (an environment switch set before the
  app is imported), not guessed from loaded modules.
- One uvicorn worker (board #63): the in-process tombstone is accepted with its limits.
- A turn that waited on another process's load counts as external even if that process answered
  from stored data: it can't be told apart, and over-counting external is the safe side.
- N = 3 consecutive timeouts; a success resets the count.
