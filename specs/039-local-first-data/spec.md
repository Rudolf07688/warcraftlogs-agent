# Feature Specification: Local-first data (epic 103, first slice)

**Feature Branch**: `039-local-first-data`

**Created**: 2026-11-01

**Status**: Draft

**Input**: Brief `sprints/2026-10-31c/briefs/039-local-first-data.md` (sprint worktree): sc-178
(visibility rule for the global raw WCL store), sc-177 (writer hardening), sc-129 (DB-first
reads with freshness rules). Owner steer: board #1 (visibility rule approved by the owner).

## Clarifications

### Session 2026-11-01

Self-answered (developer autonomy); each is a board decision `clarify:039-<topic>` (#17-#21).

- Q: What counts as a code the workspace already references? → A: a code the workspace itself
  fetched successfully from Warcraft Logs in a signed-in turn (a recorded reference); fetches
  without a signed-in identity record none.
- Q: How long do "public" and a reference count? → A: 7 days (`RAW_STORE_REVERIFY_DAYS`), then
  Warcraft Logs is asked again.
- Q: Is the reference record itself tenant-protected? → A: yes, row-level security per
  workspace; references are not deleted when a report is gone (harmless, the rows are gone).
- Q: Unchanged payload: skip entirely or refresh the fetch time? → A: refresh the fetch time
  only; the payload is neither sent nor rewritten.
- Q: Overlong code / operation name? → A: operation name truncated; an overlong code is kept in
  the row's report list but never recorded as public or referenced (fails closed).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - What I look up stays in my workspace (Priority: P1, sc-178)

A user asks about an unlisted report by its code, or looks up a character. The app keeps a
global store of every Warcraft Logs response. A user in another workspace must never be served
that stored response unless the report is public or their own workspace already references the
code. When Warcraft Logs later says a report is private or deleted, the stored copy is removed.

**Why this priority**: it is the security gate for every later read of the store (DB-first
reads, semantic search). Nothing may read the store before it exists.

**Independent Test**: store a response for an unlisted report fetched by workspace A; ask the
single read function for it as workspace B (miss), as A (hit); mark the report public (B hits);
report the code gone (every stored row for it is removed and its shared-cache entries evicted).

**Acceptance Scenarios**:

1. **Given** a stored row for an unlisted report only workspace A has fetched, **When**
   workspace B reads the store for that exact query, **Then** B gets nothing (a miss).
2. **Given** a stored row for a report Warcraft Logs has shown to be public, **When** any
   workspace reads it, **Then** the row is served.
3. **Given** stored rows for a report, **When** a Warcraft Logs refresh finds that report
   private or deleted, **Then** every stored row naming that code is deleted and its shared
   cache entries are evicted.
4. **Given** a finished report that stays public or referenced, **When** time passes, **Then**
   its rows are kept (no age-based purge).
5. **Given** any code in the app, **When** it wants stored WCL data, **Then** it can only get it
   through one read function that applies the rule.

---

### User Story 2 - The store stays cheap as it grows (Priority: P2, sc-177)

The owner wants the store not to bloat Postgres: identical refetches must not rewrite large
payloads, writes are batched, odd inputs never fail an insert, and the owner can watch the
store's size.

**Why this priority**: the store grows with every fetch; DB-first reads make it permanent.

**Independent Test**: write the same response twice (payload not rewritten), a changed one
(rewritten); push several responses through the writer (one transaction per batch, a bad row
loses only itself); write an overlong code/operation name and a body with `\u0000` (stored);
stop the writer with a pending throttled count (logged); fail the database (log has no params).

**Acceptance Scenarios**:

1. **Given** a stored row, **When** the same payload is fetched again, **Then** the payload is
   not rewritten; **When** a different payload is fetched, **Then** it is.
2. **Given** several queued responses, **When** the writer runs, **Then** it commits them in
   batches, and one failing row never loses the others or reaches a caller.
3. **Given** an overlong report code or operation name, or a body containing `\u0000`, **When**
   it is written, **Then** the insert succeeds.
4. **Given** throttled warnings pending, **When** the writer stops, **Then** the pending count is
   logged. **Given** a database error, **When** it is logged, **Then** no query parameters or
   payload appear in the log.
5. **Given** the owner, **When** they want the store's size, **Then** a documented query gives
   table size and row count.

---

### User Story 3 - Repeat questions are answered from the store (Priority: P3, sc-129)

A user asks a second question about a finished raid. The data the agent needs was already
fetched, so it is served from the store with no Warcraft Logs call, layered under the shared
cache. Live data is still refetched.

**Why this priority**: the epic's goal (most questions without external calls); it depends on
stories 1 and 2. If story 1 runs long this story is dropped, not rushed.

**Independent Test**: with the store holding a finished report's row visible to the workspace,
run the same query: no Warcraft Logs call. With a live report's row older than the live window:
refetched. With a hidden row: refetched. With the store failing: refetched, no error.

**Acceptance Scenarios**:

1. **Given** a visible stored row of a finished report, **When** the same query runs, **Then**
   it is answered from the store with no Warcraft Logs call.
2. **Given** a stored row of a report still being logged, older than the live window, **When**
   the query runs, **Then** Warcraft Logs is called.
3. **Given** a stored row the workspace may not see, **When** the query runs, **Then** it is a
   miss and Warcraft Logs is called (which applies its own permissions).
4. **Given** a cached family (e.g. report summary) missing from the shared cache but in the
   store, **When** it is read, **Then** the store answers and the shared cache is filled, so the
   next read is a shared-cache hit.
5. **Given** the store fails, **When** a query runs, **Then** it falls back to Warcraft Logs and
   the turn does not fail.
6. **Given** the command-line / evaluation path (no store configured), **When** a query runs,
   **Then** behaviour is unchanged.

### Edge Cases

- A query names several reports (batch): served only when every named report is visible and
  final; deleted when any of them is reported gone.
- A query references a report in a way the code parser does not recognise: it counts as
  non-report data, which this slice never serves from the store (fails closed).
- Two workspaces run the identical query at the same moment: each one's store read is checked
  against its own workspace; only the network fetch is shared.
- A fetch outside a signed-in chat turn (background jobs, page loads): no workspace is
  recorded, so its rows are visible only when the report is public.
- A report shown public long ago, or a code fetched long ago: visibility is re-confirmed with
  Warcraft Logs after a bounded window, so a later private/deleted state is detected.
- A Warcraft Logs refresh that fails for other reasons (rate limit, timeout, malformed query):
  not treated as private/deleted.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A stored row MUST be served to a workspace only when every report it names is
  public (as last seen from Warcraft Logs) or referenced by that workspace.
- **FR-002**: A workspace references a code when that workspace has itself successfully fetched
  data for that code from Warcraft Logs.
- **FR-003**: Public status and references MUST be re-confirmed with Warcraft Logs at least every
  `RAW_STORE_REVERIFY_DAYS` days (default 7); older ones do not count.
- **FR-004**: Rows naming no report (rankings, characters, world data) are public Warcraft Logs
  data reachable only by their exact query; this slice never serves them from the store (the
  shared cache's family TTLs keep governing them).
- **FR-005**: All reads of the store MUST go through one read function; no other module reads
  the store table directly (guarded by a test).
- **FR-006**: When a Warcraft Logs response for a single report shows it missing, private or
  deleted, every stored row naming that code MUST be deleted, its public status removed, and its
  shared-cache report entries evicted.
- **FR-007**: No age-based purge of stored rows.
- **FR-008**: An unchanged payload MUST NOT be rewritten; only its fetch time is refreshed. A
  changed payload replaces the row.
- **FR-009**: The writer MUST commit in batches; on a batch failure it retries the batch's items
  one by one, so one bad item loses only itself. Failures never reach a caller.
- **FR-010**: Overlong report codes / operation names and `\u0000` in a body MUST NOT fail an
  insert (operation name truncated to 120; a code over 32 characters stays in the row's report
  list but is never recorded as public or referenced, so the row is never served); the throttled warnings' pending counts are logged on stop; database error logs contain
  only the error class and SQL state.
- **FR-011**: A documented monitoring query reports the store's size and row count.
- **FR-012**: A Warcraft Logs read MUST check the shared cache, then the store, then Warcraft
  Logs.
- **FR-013**: A report row is fresh when the report was seen finished and the row was fetched
  after it finished (kept indefinitely), or when it is younger than the live window
  (`WCL_CACHE_UNFINISHED_TTL`, the shared cache's existing rule for unfinished reports).
- **FR-014**: A store hit MUST NOT be offered for storage again and MUST NOT count as a reference.
- **FR-015**: Any store failure MUST fall back to Warcraft Logs without surfacing an error.
- **FR-016**: Without a configured store (CLI, evals, tests) the client behaves exactly as today.

### Key Entities

- **Stored fetch**: one Warcraft Logs response per exact query, with the reports it names, its
  fetch time and a content hash.
- **Report status**: per report code, the visibility and end time last seen from Warcraft Logs,
  and when.
- **Workspace reference**: (workspace, report code, last confirmed) — this workspace fetched the
  code from Warcraft Logs itself. Protected per workspace by row-level security.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In tests, 0 stored rows are served to a workspace that neither references the code
  nor sees it as public.
- **SC-002**: A second identical question about a finished report makes 0 Warcraft Logs calls
  for the data already stored.
- **SC-003**: Refetching an unchanged payload rewrites 0 payload bytes.
- **SC-004**: A store outage causes 0 failed chat turns.
- **SC-005**: After a refresh finds a report private or deleted, 0 rows naming it remain.

## Assumptions

- The app authenticates to Warcraft Logs with client credentials, so every response it gets is
  for a public or unlisted report; private reports are never returned.
- Report summary queries also select the report's `code` and `visibility`, the source of
  "public" and of the end time used for freshness.
- The shared Redis cache keeps its design; this feature only adds eviction of a gone report's
  keys. DB-first reads never widen exposure beyond today: the shared cache already serves report
  data by code to every workspace.
