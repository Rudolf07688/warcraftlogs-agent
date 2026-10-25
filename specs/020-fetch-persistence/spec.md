# Feature Specification: Fetch persistence foundation

**Feature Branch**: `020-fetch-persistence`

**Created**: 2026-10-25

**Status**: Draft

**Input**: User description: "Every successful GraphQL response that actually reaches the Warcraft Logs API through the single WCL client (AsyncWCLClient) is stored in a new global (not tenant-scoped) raw-fetch table: query key, operation name, params JSONB, report code (nullable, indexed), fetched_at, payload JSONB, created by migration 0013 (down_revision 0012_conversation_pin_title) whose upgrade and downgrade both work. Persistence covers cache-miss fetches from tools, guides, the welcome/recent-raids service and background jobs. Persisting never blocks or slows the tool call: it runs off the request path in a bounded background writer (overflow dropped and logged); persistence errors are logged, never raised to the agent or user. Repeated identical fetches of a finished report upsert one row instead of duplicating; live data may be stored again with a new fetched_at. Tests cover write-through, error isolation (DB down, fetch still succeeds) and upsert. Nothing reads from the table yet (DB-first reads are sc-129)."

Shortcut: sc-127 (2 points, Raw WCL fetch schema), sc-128 (2 points, Write-through
persistence of every WCL fetch). Epic 103 "Every fetch stored in the DB". Sprint plan
section F3 / 020. Decision 6 (the table is global).

## Clarifications

### Session 2026-10-25

Q1 and Q5 answered by the product owner (decisions.md entries 16 and 17), the rest by the
scrum master. Spec signed off once these were encoded.

- Q: Upsert policy: one row per query key, or append live data? → A: One row per query
  key; every store replaces the payload and fetch time (FR-008). DB-first reads (sc-129)
  can tell whether a row was final when fetched from the report's end time and
  `fetched_at`.
- Q: Which processes persist? → A: Only the backend app process. Everywhere else the
  client's sink stays unset (no-op) (FR-010).
- Q: Queue bound and overflow? → A: At most 500 queued responses and 64 MB of queued body
  bytes (counted from the response bytes already in hand, never re-serialised on the
  caller's path). When full, drop the new response, count it, and log one warning per
  60 s with the count. Settings `WCL_FETCH_PERSIST_ENABLED` (true),
  `WCL_FETCH_PERSIST_QUEUE_MAX` (500) and `WCL_FETCH_PERSIST_QUEUE_MB` (64), documented in
  `.env.example` (FR-006, FR-012).
- Q: Shutdown? → A: A 5 s drain before the WCL clients and the database engine close,
  then cancel and log the dropped count. Tests cover both a timely drain and the timeout
  (FR-011).
- Q: Batched multi-report calls? → A: One row per network call; `report_code` is empty
  when the call covers more than one report. Condition from the product owner: the
  report codes must be queryable without parsing the GraphQL text, uniformly for every
  call that names one or more reports (FR-015).
- Condition from the product owner: acceptance needs a test showing that a full queue
  drops without blocking the fetch, alongside the DB-down test (FR-006, SC-007).
- The rateLimitData-only query is stored like any other fetch, with no special case.

## User Scenarios & Testing *(mandatory)*

The owner wants "every single fetch stored in the db", so that over time the app holds
the Warcraft Logs data it has seen and most questions can be answered without an
external call. This feature is the foundation: it stores. Reading from the store comes
next sprint (sc-129). The chat user must notice nothing, except that nothing gets slower.

### User Story 1 - Every Warcraft Logs response is kept (Priority: P1)

Whenever the app asks Warcraft Logs for data and gets a successful answer, whether the
question came from a chat tool, a class guide build, the welcome page's recent raids or
any other background job, that answer is saved in the app's database together with what
was asked (the query, its parameters, the report it was about, and when it was fetched).

**Why this priority**: This is the point of the epic. Stored data only starts building up
once this ships, and every later story (DB-first reads, semantic search, the Raids page)
needs it.

**Independent Test**: Run a tool that fetches a report from Warcraft Logs (with a fake
Warcraft Logs server), then look in the database: one stored fetch exists with the
query's operation name, its parameters, the report code and the response body.

**Acceptance Scenarios**:

1. **Given** the app is running with a database, **When** a chat tool fetches a report's
   fights from Warcraft Logs and the shared cache does not have them, **Then** the
   response is stored once, with the operation name, parameters, report code, fetch time
   and response body.
2. **Given** the shared cache already holds the answer, **When** a tool asks for it,
   **Then** no request reaches Warcraft Logs and nothing new is stored.
3. **Given** a background job (recent raids, guide data sheet) fetches from Warcraft
   Logs, **When** the response arrives, **Then** it is stored the same way as a chat
   fetch.
4. **Given** several identical requests are in flight at once and share one Warcraft Logs
   call, **When** the call succeeds, **Then** the response is stored once, not once per
   waiter.
5. **Given** Warcraft Logs answers with an error (HTTP error, GraphQL errors, timeout),
   **When** the call fails, **Then** nothing is stored.

---

### User Story 2 - Saving never slows or breaks a chat (Priority: P1)

Saving a response happens in the background. The tool that asked for the data gets it
back as fast as before. If the database is slow, down or rejects the write, the chat
carries on normally; the problem shows up in the logs, never in the chat.

**Why this priority**: The owner's goal is a faster app. A store that adds latency or
turns a database hiccup into a failed tool call would defeat it. This is as important as
storing.

**Independent Test**: Make the database unreachable, run a tool that fetches from a fake
Warcraft Logs server: the tool returns its normal result, and the log shows a
persistence warning.

**Acceptance Scenarios**:

1. **Given** the database is down, **When** a tool fetches from Warcraft Logs, **Then**
   the tool returns its normal result and a warning is logged.
2. **Given** the background writer is backed up to its limit, **When** another response
   arrives, **Then** that response is dropped from persistence (the tool still gets it),
   and the drop is logged without flooding the log.
3. **Given** a tool fetches a large report, **When** the response is handed to the
   writer, **Then** the hand-off costs the tool no measurable time (no database work, no
   parsing on its path).
4. **Given** the app shuts down with responses still waiting to be written, **When**
   shutdown runs, **Then** the writer gets a short, bounded grace period to finish, and
   whatever is left after it is dropped and counted in the log; shutdown is never held
   up longer than that.

---

### User Story 3 - A finished report is stored once (Priority: P2)

A finished report never changes, so fetching the same thing from it again must not add
a second copy. Data that can still change (a report still being logged, a character's
rankings) may be stored again, with its new fetch time.

**Why this priority**: Without it the store grows with duplicates of data that never
changes. It matters for size and for the DB-first reads that come next, but storing at
all (US1) comes first.

**Independent Test**: Fetch the same finished report query twice (cache bypassed): the
store holds one row for it, with the latest fetch time.

**Acceptance Scenarios**:

1. **Given** a finished report's query was stored, **When** the identical query (same
   query text and parameters) is fetched again, **Then** the store still holds exactly
   one row for it, and its fetch time is the newer one.
2. **Given** live data was stored, **When** it is fetched again and Warcraft Logs returns
   a different answer, **Then** the stored answer and fetch time are the new ones.
3. **Given** the same query is fetched with different parameters (another fight, another
   report), **When** both are stored, **Then** they are separate rows.

---

### Edge Cases

- **No database configured** (the `wcl` CLI, the guide eval scripts, unit tests that do
  not opt in): fetching works exactly as today and nothing is persisted; no warning per
  fetch.
- **Batched requests** (one call covering several characters or up to 10 reports): the
  response is stored as one row; the single report code is set only when the request is
  about exactly one report; every code the request names is in the row's searchable
  report-code list.
- **Response with no report** (rankings, zones, the class roster, character lookups):
  stored with an empty report code.
- **The budget field the client adds to every query** (points spent this hour) is not
  part of the stored response: it is client bookkeeping, not Warcraft Logs data.
- **OAuth token requests** are not GraphQL data fetches and are not stored.
- **A persistence write fails halfway through** (constraint, connection lost): that row
  is skipped and logged; the writer keeps going with the next one.
- **Very large responses** (report events): stored whole; turning them into the stored
  form happens in the background, never on the tool's path.
- **The same query fetched by two app processes at once**: both upserts land on the same
  row; the later one wins; neither fails.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A new global table of raw fetches MUST hold, per stored fetch: a query key
  (identity of the query text plus all parameters), the operation name, the parameters,
  the report code (optional, indexed), the fetch time and the response body. It is not
  tenant-scoped and carries no row-level security, like the shared Warcraft Logs cache
  (decision 6).
- **FR-002**: Migration `0013` MUST create the table (with `down_revision`
  `0012_conversation_pin_title`); downgrade MUST drop it; upgrade, downgrade, upgrade
  MUST all succeed on PostgreSQL. The app's runtime database role MUST get read/write
  access to it, as for the other global tables.
- **FR-003**: Every successful GraphQL response that reaches the Warcraft Logs API through
  the single WCL client MUST be offered for persistence exactly once per network call,
  whichever caller (chat tool, guide pipeline, recent raids, other background job) asked.
  Responses served from the shared cache MUST NOT be stored again (they never reach the
  API).
- **FR-004**: Failed calls (HTTP error, GraphQL errors in the response, timeout,
  cancellation) MUST NOT be stored.
- **FR-005**: Offering a response for persistence MUST NOT block, await or parse on the
  caller's path; it is a constant-time hand-off to a background writer.
- **FR-006**: The background writer MUST be bounded: at most 500 waiting responses and
  64 MB of waiting response bytes by default (byte count taken from the response already
  in hand). When either bound is reached, the new response MUST be dropped from
  persistence (never from the caller, and without waiting), and the drops logged at most
  once per 60 s with a count. A test MUST show a full queue dropping without blocking the
  fetch.
- **FR-007**: Any persistence error (database down, write rejected, bad data) MUST be
  logged and MUST NOT reach the caller, the agent or the user. One failed row MUST NOT
  stop the writer.
- **FR-008**: There MUST be exactly one stored row per query key: storing a fetch whose
  query key already exists MUST replace that row's response body and fetch time (an
  upsert). A finished report (a report whose last event is at least two hours before
  the fetch, the rule the cache already uses) therefore never piles up duplicates, and
  live data is stored again with its new fetch time.
- **FR-009**: The stored response body MUST be the Warcraft Logs response as the caller
  receives it (the client's injected budget field removed).
- **FR-010**: Persistence MUST be active in the backend app process (started and stopped
  with the app). Processes without the app's lifecycle (the `wcl` CLI, eval scripts,
  tests that do not opt in) MUST keep working with persistence off.
- **FR-011**: On app shutdown, new responses MUST stop being accepted and the writer MUST
  get 5 s to write what is waiting, before the WCL clients and the database engine close;
  anything left is dropped and logged with a count. Shutdown MUST NOT wait longer than
  that period.
- **FR-012**: Persistence MUST be switchable off (`WCL_FETCH_PERSIST_ENABLED`, default
  on) and its bounds configurable (`WCL_FETCH_PERSIST_QUEUE_MAX`, default 500;
  `WCL_FETCH_PERSIST_QUEUE_MB`, default 64), documented in `.env.example`.
- **FR-013**: The `wcl_agent` package MUST keep running without the backend: it MUST NOT
  import backend or database code. The backend plugs the writer into the client.
- **FR-014**: Nothing reads from the table in this feature.
- **FR-015**: Every stored fetch MUST carry the list of report codes the query names
  (empty when none), in a form the database can search and index directly, uniformly for
  single-report and batched calls. The codes MUST come from the query itself (each
  `report(code: …)` argument, as a variable or a literal), so agent-written queries are
  covered too. The single `report_code` column is set only when that list has exactly one
  code.

### Key Entities

- **Raw fetch**: one Warcraft Logs GraphQL response the app received. Identified by its
  query key (the query text plus all parameters). Holds the operation name (for example
  `ReportSummary`), the parameters as sent, the list of report codes the query names,
  the single report code when that list has exactly one, when it was fetched, and the
  response body. Global: shared by every tenant,
  because Warcraft Logs data is public.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of successful Warcraft Logs calls made by the running app in a test
  session end up as stored fetches (one per distinct query), with no stored row for a
  failed call or a cache hit.
- **SC-002**: With the database unreachable, every tool call that fetches from Warcraft
  Logs still returns its normal result (0 failures caused by persistence).
- **SC-003**: Handing a response to the writer adds no measurable time to a tool call: in
  a test with a deliberately slow database write, the tool call returns in the same time
  as with persistence off.
- **SC-004**: Fetching the same finished-report query N times leaves exactly 1 stored row
  for it.
- **SC-005**: App shutdown with a backed-up writer completes within the configured grace
  period plus 1 second.
- **SC-006**: The schema migration upgrades, downgrades and upgrades again cleanly on
  PostgreSQL.
- **SC-007**: With the writer's queue full, a fetch still returns its result without
  waiting, and the dropped response is counted and logged.
- **SC-008**: Every stored fetch of a batched multi-report call can be found by any one
  of its report codes with a single indexed lookup.

## Assumptions

- The query key is the same identity the client already uses to join identical in-flight
  requests (query text plus sorted parameters, hashed), so "identical fetch" means the
  same thing everywhere.
- One row per query key (latest response wins) is enough for this sprint: nothing reads
  the store yet, and DB-first reads (sc-129) can tell whether a stored report row was
  final when fetched from its fetch time and the report's end time. Keeping a history of
  live data is out of scope (product owner, Q1).
- No retention or size limit on the table this sprint; the owner wants the data kept.
- The writer runs inside the app's event loop as a background task; database work is
  asynchronous and large-body preparation runs in a worker thread, so neither touches the
  caller's path.
- Persisting fetches from the `wcl` CLI and eval scripts is out of scope (no database
  lifecycle there).
