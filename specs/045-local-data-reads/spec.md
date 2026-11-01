# Feature Specification: Local data reads (raw-store probe, races, hit rate, exact lookups)

**Feature Branch**: `045-local-data-reads`

**Created**: 2026-11-01

**Status**: Draft

**Input**: Sprint 2026-11-01, stories sc-295, sc-296, sc-132, sc-131 (epic 103 "Every fetch stored
in the DB"). Design: `documentation/designs/20261101_semantic_knowledge_base.md`; QA source:
`qa-reports/2026-10-31c/performance.md` (PERF-001..007) and Ansel's 039 bypass review.

## Clarifications

### Session 2026-11-01 (self-answered, board #39-#43)

- Q: Probe timeout default and breaker trigger? → A: 400 ms setting; 30 s breaker; opens on timeouts and connection-class errors only; half-open lets one trial through (`clarify:045-breaker`).
- Q: How can the probe run inside single-flight when its answer depends on the workspace? → A: the flight key includes the store's workspace scope whenever a store is installed (`clarify:045-flight-scope`).
- Q: Where is the per-turn boundary without touching `ws.py`? → A: the cache module's per-turn hook `set_refresh_actor` (`clarify:045-turn-seam`).
- Q: How are gone-vs-write races ordered without a migration? → A: DB tombstone status `gone` in `raw_reports` + request start time on fetches; Redis tombstone key checked after each report-family write (`clarify:045-races`).
- Q: What does `list_stored_reports_for_character` read? → A: visible stored report summaries whose roster names the character (`clarify:045-tools`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The local store makes answers faster, never slower (Priority: P1, sc-295)

A player asks about a report. Before every Warcraft Logs (WCL) call the app checks its own store
of earlier fetches. Today a slow or hung database adds up to 3 s to every such call, a probe costs
6-9 database round trips, a fan-out holds one database connection per call, and the background
writer rewrites the tenant scope and grant on every fetch. After this story the check is cheap,
bounded and remembered when it fails.

**Why this priority**: it is paid on almost every report question; a database stall today can add
24-30 s to one answer. Its counters also feed User Story 3, and its visibility clause is a contract
another feature (044 search) builds on.

**Independent Test**: drive the WCL client with a fake store source and a fake network; drive the
store read with a session whose statements are counted; drive a hung session and check the second
call skips the store.

**Acceptance Scenarios**:

1. **Given** the store hangs, **When** a report query runs, **Then** it waits at most the probe
   timeout (default 400 ms, configurable, never over 500 ms by default) and goes to WCL, and for the
   next ~30 s no probe runs at all (breaker open).
2. **Given** the breaker has been open for 30 s, **When** the next calls arrive, **Then** exactly
   one trial probe runs; others skip the store until it ends; success closes the breaker, a timeout
   or connection error opens it again for 30 s.
3. **Given** no stored row for the query, **When** the store is probed, **Then** it costs one SQL
   statement (at most 2) and no tenant scope is set.
4. **Given** a stored, fresh, visible row, **When** the store is probed, **Then** at most one
   `set_config` statement runs and the visibility check and payload come back in one statement.
5. **Given** ten identical concurrent report queries from one workspace, **When** they run,
   **Then** one probe runs (inside single-flight), holding a lane slot, so a fan-out holds at most
   the lane limit of database connections.
6. **Given** a batch of writes for one workspace with grants younger than an hour, **When** the
   writer stores them, **Then** the tenant scope is set once per tenant per batch and unchanged
   grants are not rewritten.
7. **Given** a store hit of a large body, **When** it is returned, **Then** the body arrives as
   bytes (no text decode and re-encode on the event loop).
8. All 039 visibility tests stay green, unchanged.

---

### User Story 2 - "Private" means private within hours, and gone stays gone (Priority: P2, sc-296)

A report owner makes a report private or deletes it. Its stored copy must stop being served:
a store hit for a workspace that sees it only through its own grant must not copy it into the
shared, workspace-less Redis cache, and late-arriving data must not bring a gone report back.

**Why this priority**: privacy, but today's exposure is bounded and accepted (re-verify window +
Redis TTL), so it ranks after US1. Second in the drop order (Maren, board #9).

**Independent Test**: fake store source + fakeredis: a granted-only hit leaves no Redis key; writer
tests over SQLite order a ReportGone against a fetch requested before it; a loader whose write
lands after an eviction leaves no key.

**Acceptance Scenarios**:

1. **Given** a stored row visible to the workspace only through its grant (some code not public),
   **When** a cached report tool loads it through the store, **Then** the value is returned to the
   caller but no shared Redis entry is written (and no process memo).
2. **Given** a row whose every code is public, **When** it is served from the store, **Then** Redis
   is back-filled as today.
3. **Given** a ReportGone for code X was written, **When** a fetch naming X whose request started
   before the gone was seen is written later, **Then** neither its row nor its grant is stored.
4. **Given** a fetch naming X requested after the gone was seen, **When** it is written, **Then**
   it is stored and granted normally (the report came back).
5. **Given** a loader read report X's data before X's Redis keys were evicted, **When** it writes
   to Redis after the eviction, **Then** the entry does not survive.

---

### User Story 3 - The owner can see how often questions are answered locally (Priority: P2, sc-132)

The app owner wants to measure progress toward "80% of questions answered without external calls".

**Why this priority**: it's the baseline metric for the epic, and the PERF-007 decision in US1
rests on the probe counters.

**Independent Test**: record probe outcomes and turns, flush to fakeredis, read the admin cache
stats.

**Acceptance Scenarios**:

1. **Given** probes ended as hit, miss, not visible and timeout, **When** an admin reads the cache
   stats, **Then** each count appears, summed over the stats window, with a store hit rate.
2. **Given** a chat turn that made no external WCL call (Redis, store or no data needed), **When**
   it ends, **Then** it counts as answered locally; a turn with any network WCL call (successful
   or failed) does not.
3. **Given** turns in the window, **When** an admin reads the cache stats, **Then** the local-answer
   rate (local turns / turns) is shown, or "no data" when there were no turns.
4. **Given** Redis is down or disabled, **When** stats are read, **Then** the degraded shape keeps
   the new fields with zero counts and no rate.

---

### User Story 4 - The agent can look up exact stored data (Priority: P3, sc-131)

A player asks "what fights are in report X?", "show the damage table for fight 32", "which of my
reports do you have?". The agent first asks the store through exact lookups, and falls back to WCL
when the store says "not stored locally".

**Why this priority**: it builds on US1's read path and needs the name resolver (044, sc-304)
merged; last in order.

**Independent Test**: tools called with a turn identity over SQLite with seeded rows: visible,
not visible (another workspace's grant), not stored, stale.

**Acceptance Scenarios**:

1. **Given** a stored, visible report summary, **When** `list_stored_fights(report_code)` runs,
   **Then** it returns the report's fights in a compact form.
2. **Given** a stored, visible table for a report fight and metric, **When**
   `get_stored_fight_table(report_code, fight_id, data_type, ...)` runs, **Then** it returns the
   table, capped like the WCL table tool.
3. **Given** stored, visible summaries listing a character, **When**
   `list_stored_reports_for_character(name, realm, region)` runs, **Then** it returns those reports,
   newest first, bounded.
4. **Given** a row that exists but isn't visible to the workspace, **When** any tool asks for it,
   **Then** the result is identical to "nothing stored": `not_stored`, telling the agent to use WCL.
5. **Given** a misspelled encounter or character argument, **When** a tool runs, **Then** the
   resolver normalises it or returns its correctable error with close matches.

### Edge Cases

- The probe is cancelled by its caller (turn cancelled): the breaker trial slot is released and the
  breaker state is unchanged.
- A non-connection error in the probe (a bug, a bad row): a miss, not a breaker trip.
- The row changes between the lookup and the payload statement: the payload statement is pinned to
  the looked-up `fetched_at`, so a changed row reads as a miss.
- Rate-limited WCL (429 budget spent): the store is still probed first, so stored answers keep
  working while WCL is blocked.
- Two workspaces send the identical query at once: they never share one single-flight (the probe's
  answer depends on the workspace), so neither sees the other's grant.
- A turn's tools run in threads or sub-tasks: the per-turn "external call" marker is shared through
  the copied context.
- Probe counters and turn counts are best effort like the family counters: lost on a crash before
  a flush, never failing a request.

## Requirements *(mandatory)*

### Functional Requirements

**sc-295**
- **FR-001**: The probe timeout is a setting (`RAW_STORE_PROBE_TIMEOUT_MS`, default 400). A breaker
  opens for 30 s after a probe timeout or connection error; while open no probe runs; after it, one
  trial probe (half-open) decides.
- **FR-002**: The probe looks up the row first. No row, invalid codes or not fresh end the probe
  without setting a tenant scope. A miss costs at most 2 SQL statements.
- **FR-003**: On a hit the tenant scope is one `set_config` statement (skipped when every code is
  public or there is no tenant), and visibility plus payload come back in one statement.
- **FR-004**: `fetch_visible_clause(raw_fetch_id, *, tenant_id, since)` in `raw_fetches.py` is the
  one SQL definition of the 039 visibility rule (common.md contract 3); `read_visible_fetch` uses it.
- **FR-005**: The probe runs inside the WCL client's single-flight (keyed by query and workspace
  scope) and inside a lane-limiter slot, before the rate-limit block check.
- **FR-006**: The writer sets the tenant scope once per tenant per transaction (one statement) and
  skips a grant refresh younger than one hour.
- **FR-007**: A store hit returns the payload as bytes from the database, with no text decode or
  re-encode on the event loop.
- **FR-008**: PERF-007: a board `decision` on skipping the probe for Redis-cached families, citing
  what the counters can show and how to read them (live numbers come from the owner's live check).

**sc-296**
- **FR-009**: A store answer carries whether every code is public. When not, the value is not
  written to the shared Redis cache or the process memo by the loading `get_or_load` /
  `get_many_or_load`.
- **FR-010**: Every gone or private signal leaves a tombstone for each code (the time WCL said so):
  a ReportGone (`report: null`, its seen time) and a summary that finds a report private (its fetch
  time, 047 sc-322). The writer stores no row, status or grant for a fetch naming a tombstoned code
  whose request started at or before the tombstone; a fetch requested later is written as usual
  (the report came back). As built (047, owner's choice, no migration): the tombstone lives in the
  writer's process memory (`fetch_persistence._tombstones`), per process, kept 10 minutes
  (`TOMBSTONE_TTL`, well past the 75 s WCL query timeout plus queueing) and capped at 1024 codes
  (`TOMBSTONE_MAX`, oldest dropped first), and lost on restart. That is accepted for the single
  uvicorn worker the app runs (board #63): the one writer sees every signal. This supersedes the
  `raw_reports` `gone` status in the clarification above and the "tombstones reuse `raw_reports`"
  assumption.
- **FR-011**: Evicting a report's Redis keys first sets a short Redis tombstone for the code; a
  report-family cache write checks it after writing and removes its own write when present.

**sc-132**
- **FR-012**: Probe outcomes `hit`, `miss` (no row or not fresh), `not_visible`, `timeout` (timeout
  or connection error) are counted like the family counters and summed by `read_stats`.
- **FR-013**: Each chat turn is counted; a turn with no network WCL call is counted as local. The
  turn boundary is the existing per-turn hook in the cache module (`set_refresh_actor`), so
  `ws.py` is unchanged.
- **FR-014**: `CacheStats` gains `store` (counts + hit rate) and `local_answers` (turns, local
  turns, rate) for the stats window; degraded shape keeps them with zeros.

**sc-131**
- **FR-015**: Agent tools `list_stored_fights`, `get_stored_fight_table`,
  `list_stored_reports_for_character` read only through the visibility rule (exact key via
  `read_visible_fetch`, or a list query filtered by `fetch_visible_clause`); no embeddings.
- **FR-016**: Not visible and not stored return the same result, `{"status": "not_stored", ...}`,
  with a hint to use the WCL tools.
- **FR-017**: Encounter and character arguments are normalised by the resolver (044 sc-304); its
  correctable error is returned as is.
- **FR-018**: Output is compact and bounded (fights ≤ 100 rows, reports ≤ 25, tables through the
  existing table cap).
- **FR-019**: The tools run only inside an authenticated chat turn (`current_identity`); outside it
  they fail closed like the profile tool.

### Key Entities

- **Probe outcome**: hit / miss / not_visible / timeout, per probe.
- **Breaker**: closed / open(until) / half-open(trial in flight or not), process-wide.
- **Stored answer**: body bytes + `shared` (every code public).
- **Tombstone**: a `raw_reports` status `gone` with its seen time (DB), and a short Redis key per
  evicted code.
- **Turn usage**: per turn, whether any network WCL call happened.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: During a database stall, a turn with 10 report-naming calls loses at most one probe
  timeout (≤ 0.5 s) instead of up to 30 s.
- **SC-002**: A probe for an unknown query costs ≤ 2 SQL statements; a hit ≤ 4, down from 6-9.
- **SC-003**: Concurrent probes are bounded by the WCL lane limit (6) instead of one per call.
- **SC-004**: A granted-only stored report never appears in the shared cache (0 keys in tests).
- **SC-005**: The admin can read the local-answer rate and store hit rate for any 1-35 day window.
- **SC-006**: Every stored-data tool answer for invisible data is byte-identical to "not stored".

## Assumptions

- "Round trips" in the ACs are SQL statements; pool ping, BEGIN and ROLLBACK are session overhead
  common to every DB call and not counted.
- Not fresh is counted as `miss` (the AC's four counters); a breaker-skipped call counts nothing.
- A turn is a chat turn over the websocket; greetings, follow-up suggestions and guide jobs are not
  turns. A turn needing no data counts as local, as the AC states.
- `list_stored_reports_for_character` finds reports through stored, visible report summaries whose
  roster names the character (WCL rosters carry no realm, so realm/region narrow nothing beyond the
  resolver's normalisation).
- No migration: tombstones reuse `raw_reports` (visibility `gone`, 16-char column).
- sc-131 starts only after the resolver (044) merge and Ansel's release of `raw_fetches.py`.
