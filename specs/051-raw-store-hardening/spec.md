# Feature Specification: Raw-store hardening

**Feature Branch**: `051-raw-store-hardening`

**Created**: 2026-11-02

**Status**: Draft

**Input**: Sprint 2026-11-02 brief 051 (stories sc-359, sc-353, sc-354): migrations build their
indexes without locking writes; a private report's tombstone can't be flushed and its signal is
never dropped; the stored-reports lookup stays correct and fast as the store grows.

## Clarifications

### Session 2026-11-02

Answered by the developer (autonomous sprint); board keys `clarify:051-*`.

- Q: What happens when the tombstone cap overflows inside the in-flight window? → A: The oldest
  entry is evicted, and if it was still inside the window its time raises a per-process floor:
  every report fetch requested at or before the floor is treated as stale. Codes over 32 characters
  are not tombstoned.
- Q: How are signals kept on a full queue without unbounding memory? → A: Gone signals bypass the
  queue caps; a dropped summary of our own query is salvaged into a gone signal carrying only its
  private and null-entry codes (its body is still dropped).
- Q: What sets the own-summary flag? → A: The write path, when the query text is exactly the app's
  own summary query (single or batch) and its exact codes equal the stored codes; migration 0021
  backfills with the old lookup's per-row key check.
- Q: How does the lookup stay bounded without the fetch-time window? → A: On Postgres it reads only
  own-summary rows naming a code granted to the workspace or confirmed public inside the window;
  every visible row names such a code, so this never hides a visible row. The unused 0020 index is
  replaced.
- Q: Where is the concurrent-index rule written? → A: In the migration template
  (`backend/migrations/script.py.mako`); no migrations README exists.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Index migrations don't lock writes (Priority: P1, sc-359)

An operator upgrades a running deployment. The migration that adds an index to the raw store must
not block the app's writes to that table while the index builds, and the rule must be visible to
whoever writes the next index migration.

**Why this priority**: smallest story, and the new migration of story 3 must follow the rule.

**Independent Test**: upgrade and downgrade a throwaway Postgres from revision 0019 and from 0020;
inspect that the index statements run outside the migration transaction.

**Acceptance Scenarios**:

1. **Given** a database at 0019, **When** it is upgraded to head and downgraded back to 0019,
   **Then** every step succeeds and the indexes of 0020 and 0021 are created and dropped
   concurrently, outside the migration transaction.
2. **Given** a database at 0020, **When** it is upgraded to head and back to 0020, **Then** every
   step succeeds and the 0020 index exists again.
3. **Given** a developer generating a new migration, **When** they open the generated file,
   **Then** it states the concurrent-index rule.
4. **Given** the SQLite test database, **When** the suite runs, **Then** it still works.

---

### User Story 2 - A private report's tombstone can't be flushed (Priority: P1, sc-353)

When Warcraft Logs says a report is gone or private, the app deletes its stored rows and remembers
the report for a while (a tombstone), so a fetch of that report that was already under way is not
written back. An attacker must not be able to make the app forget that tombstone, or lose the
signal, by flooding it.

**Why this priority**: a lost tombstone or signal lets a private report's data be written back and
served to a workspace with a grant.

**Independent Test**: unit tests on the persistence writer with fakes, no network.

**Acceptance Scenarios**:

1. **Given** a real tombstone, **When** more gone signals for made-up codes than the tombstone cap
   arrive inside the in-flight window, **Then** a fetch of the real report requested before its
   tombstone is still not written.
2. **Given** a full write queue, **When** a gone signal or a summary carrying a private report
   arrives, **Then** the gone/private signal is still queued and processed (its rows are deleted,
   its tombstone set); other fetches are dropped as before.
3. **Given** a stored batch summary whose entry for one report is null, **When** it is written,
   **Then** that report is treated as gone (rows deleted, tombstone set, cache evicted).
4. **Given** any flood, **Then** the tombstone memory stays under the stated bound.

---

### User Story 3 - Stored-reports lookup is correct and fast (Priority: P1, sc-354)

The agent's "stored reports for a character" lookup lists the newest report summaries the workspace
may see. It must list the app's own summaries even when many hand-written look-alike rows exist,
include summaries a workspace may see through a recent grant even if they were fetched long ago,
never show a workspace anything it could not see before, and not slow down per row.

**Why this priority**: correctness and tenant visibility of stored data.

**Independent Test**: repository tests on SQLite and Postgres (two tenants, RLS), a migration
backfill test on Postgres, and a before/after timing.

**Acceptance Scenarios**:

1. **Given** rows written by the app's own summary query, **When** they are stored, **Then** they
   carry the own-summary flag; hand-written look-alikes don't.
2. **Given** a database with rows stored before the flag existed, **When** it is migrated,
   **Then** exactly the rows the old lookup accepted carry the flag.
3. **Given** more than 200 visible hand-written `ReportSummary` rows newer than the real ones,
   **When** the lookup runs, **Then** it still returns the real rows.
4. **Given** a summary fetched before the window whose report the workspace was granted recently,
   **When** the lookup runs, **Then** that summary is listed.
5. **Given** two workspaces, private and public reports, and grants held by the other workspace,
   **When** each looks up, **Then** each sees exactly what the visibility rule allowed before.

---

### Edge Cases

- A gone signal names a code longer than the store's code limit: rows naming it are never served,
  so it is not tombstoned (keeps the memory bound).
- A tombstone entry is evicted by overflow while still inside the in-flight window: its protection
  is kept by a floor (every report fetch requested at or before it is treated as stale).
- A dropped summary that carries no gone/private finding: dropped as before, nothing queued.
- A batch summary body with GraphQL errors is never stored (the client raises), so a null entry in
  a stored body is WCL's own answer.
- The lookup runs for no workspace (tenant None): only public reports.
- Old summary rows whose reports were not confirmed public or granted inside the window are not
  read at all.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Migrations 0020 and 0021 MUST create and drop their indexes concurrently, outside the
  migration transaction, on Postgres; SQLite tests keep working.
- **FR-002**: The migration template MUST state that rule for future index migrations.
- **FR-003**: A tombstone younger than the in-flight window MUST keep protecting its report however
  many other tombstones arrive (overflow inside the window raises the stale floor instead of
  forgetting the protection).
- **FR-004**: Gone and private signals MUST never be dropped because the write queue is full.
- **FR-005**: A null report entry in a stored batch summary of the app's own query MUST produce a
  gone signal.
- **FR-006**: Tombstone memory MUST stay bounded: at most `TOMBSTONE_MAX` (1024) entries of codes
  of at most 32 characters, plus one floor timestamp (well under 1 MB). Queued signals bypass the
  queue's caps but are small (codes only, under 1 KB each) and at most one per Warcraft Logs
  answer received while the queue is full, which the WCL hourly point budget bounds.
- **FR-007**: Raw rows MUST carry an own-summary flag, set at write time when the row is the
  response to the app's own fixed summary query (single or batch) with exact codes; migration
  0021 MUST backfill it with the same rule the lookup used before.
- **FR-008**: The lookup MUST filter on the flag in the database before its row limit.
- **FR-009**: The lookup MUST list every visible own summary regardless of when it was fetched,
  reading only own-summary rows that name a report confirmed public or granted to the workspace
  inside the window (not every row ever stored).
- **FR-010**: Visibility MUST stay the one existing rule; the lookup MUST NOT show a workspace a row
  it could not see before.
- **FR-011**: The lookup MUST NOT re-derive any row's query key per row.

### Key Entities

- **Raw fetch row**: one stored WCL response; gains the own-summary flag.
- **Tombstone**: a code seen gone/private and when, kept per process for the in-flight window.
- **Grant / report status**: what makes a row visible to a workspace (unchanged).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Upgrade/downgrade from 0019 and 0020 pass on a throwaway Postgres.
- **SC-002**: With 1025+ made-up gone codes, the real report's in-flight fetch is still not stored.
- **SC-003**: With a full queue, 100% of gone/private signals are processed.
- **SC-004**: With 250 hand-written look-alike rows, the lookup returns the real rows.
- **SC-005**: The lookup time no longer includes a per-row key computation; before/after timing is
  recorded in the hand-off.

## Assumptions

- The in-flight window is the existing `TOMBSTONE_TTL` (10 minutes, well past the 75 s WCL timeout
  plus queueing).
- The lookup window is the existing `raw_store_reverify_days` (1 day).
- Rows written under a past version of the summary query text keep their flag: they were the app's
  own summaries when written; visibility still applies.
- The 0020 summary index becomes unused once the lookup filters on the flag; 0021 replaces it.
