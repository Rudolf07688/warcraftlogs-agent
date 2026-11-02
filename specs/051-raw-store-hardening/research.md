# Research: Raw-store hardening

## R1 Concurrent index builds in Alembic (sc-359)

- **Decision**: `with op.get_context().autocommit_block(): op.create_index(..., postgresql_concurrently=True)`
  (and `op.drop_index(..., postgresql_concurrently=True)`), only on Postgres; SQLite runs the plain
  statements (it never takes this path in tests: tests build the schema from the models).
- **Rationale**: `CREATE INDEX CONCURRENTLY` can't run inside a transaction; Alembic's autocommit
  block commits the migration transaction first and reopens it after. A failed concurrent build
  leaves an INVALID index: `if_not_exists`/`if_exists` make a re-run converge.
- **Alternatives**: plain `CREATE INDEX` (locks writes for the build: the bug).

## R2 Tombstone overflow (sc-353)

- **Decision**: keep `TOMBSTONE_MAX`; an overflow eviction of an entry younger than
  `TOMBSTONE_TTL` raises `floor` to its time; `_stale` treats any fetch naming a report and
  requested at or before `floor` as stale. `_tombstones` becomes an `OrderedDict` subclass holding
  `floor`, so test isolation (`type(_tombstones)()`) resets both.
- **Alternatives**: never evict young entries (memory then rests on the WCL rate only); tombstone
  only codes the store knows (a report's first fetch in flight when it turns private has no rows
  yet, so it would be missed).

## R3 Signals on a full queue (sc-353)

- **Decision**: the queue becomes unbounded in asyncio terms; the writer counts capped items
  itself. `ReportGone` is never capped. A capped-out summary of our own query is salvaged in a
  tracked task: `_report_statuses` (off-loop above 256 KB) gives its gone codes, queued as
  `ReportGone(codes, fetched_at)` (the same effect `_store_one` gives private findings).
- **Alternatives**: exempt whole summaries (memory then grows with body size); regex the body
  (text parsing of JSON).

## R4 Null batch entries (sc-353)

- **Decision**: in `_report_statuses`, for our batch query, an entry `r{i}` that is JSON `null` maps
  to variable `c{i}` and is a gone code. Stored bodies never carry `errors` (the client raises on
  them), so the null is WCL's own answer, not error propagation; the alias→code map comes from our
  fixed query text.

## R5 Own-summary flag and lookup driver (sc-354)

- **Decision**: `own_summary BOOLEAN NOT NULL DEFAULT false`, set in `upsert_raw_fetch` from
  `query == REPORT_SUMMARY or query == report_summaries_query(len(variables))` with exact codes
  equal to the stored codes. Lookup (Postgres): `own_summary AND report_codes ?| ARRAY(grant codes
  since ∪ public codes checked since) AND fetch_visible_clause`, newest first, LIMIT.
- **Why complete**: a visible row names ≥ 1 code and every code is public-checked or granted inside
  the window, so it names a code in the driver set: the driver removes only invisible rows.
- **Indexes**: `ix_raw_fetches_own_summary_codes` GIN(report_codes) WHERE own_summary;
  `ix_raw_reports_public_checked` (checked_at) WHERE visibility = 'public';
  `ix_raw_fetch_grants_tenant_granted` (tenant_id, granted_at). 0020's index dropped.
- **Alternatives**: keep `fetched_at >= since` and add a grants branch (two scans, still misses the
  public-only edge); keep per-row `_flight_key` (the ~24 ms per lookup the story removes).
