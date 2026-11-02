# Brief 051-raw-store-hardening (stream B)

From Maren (product owner, `maren` on the board). Sprint 2026-11-02, steer = board #1
(fully autonomous: no owner questions at any point; decide and record on the board).

- **You:** seat `dev-1` (Ansel). Parallel developers: Nils (`dev-3`, feature 050, worktree dev-a)
  and Tomas (`dev-2`, feature 052, worktree dev-c).
- **Feature / branch:** `051-raw-store-hardening`
- **Tier:** M: one Spec Kit pass (specify, plan, tasks, implement), no gates in the middle.
  Answer your own clarify questions; post them as `answer` keyed `clarify:051-<topic>`.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b` (detached at `3b5e3ca`).
  `git -C /home/rudolf/dev/wcl-worktrees/dev-b switch -c 051-raw-store-hardening sprint-2026-11-02`
- **Base ref:** `sprint-2026-11-02`.
- **Security-core:** yes (tenant visibility of stored reports, private-report tombstones). A scoped
  `qa-security` review runs at your hand-off; Highs/Mediums come back as your one rework round.
- **Migration:** you own all migrations this sprint. New revision
  `0021_raw_fetch_own_summary` with `down_revision = "0020_raw_fetch_summary_index"`.
- **Spec dir:** `specs/051-raw-store-hardening/`.

## Goal
The stored-reports lookup stays correct and fast as the store grows, a private report's tombstone
can't be flushed, and index migrations don't lock writes.

## File footprint (stay inside; ask on the board before touching anything else)
- `backend/app/repositories/raw_fetches.py`, `backend/app/services/fetch_persistence.py`
- `backend/app/db/models.py` (raw-store models only), `backend/migrations/versions/0020_*.py`,
  `backend/migrations/versions/0021_*.py`
- `backend/app/agent_tools/stored_data_tools.py` (only if the lookup's signature changes)
- `specs/051-*/**`, tests: new files or files only you touch.
- Not yours: `backend/app/services/raw_fetch_reads.py` (breaker, probe counters) and
  `backend/app/services/kickoff_prefetch.py` are Tomas's. If the write path you change lives in
  `raw_fetch_reads.py`, agree the hunk with Tomas on the board first.

## Stories (order: 359, 353, 354)
Move each story to In Progress (`500000008`) when you start it and to Under Review
(`500000023`) in your hand-off. Never Done. ACs below are mine, derived from each ticket.

### Migration 0020 builds its index without CONCURRENTLY (sc-359, 1, chore)
Ticket: `ix_raw_fetches_summaries` is created inside the migration transaction, which locks writes
to `raw_fetches` for the build. Suggested fix: create it CONCURRENTLY in an autocommit block
(`op.get_context().autocommit_block()`) and adopt that as the rule for future index migrations.
Acceptance criteria:
1. 0020 and your new 0021 create (and drop) their indexes CONCURRENTLY in an autocommit block on Postgres; SQLite tests still run.
2. Upgrade and downgrade pass on the throwaway Postgres (`pg.py`), from 0019 and from 0020.
3. The rule is written down where future migration authors will see it (a comment in the migration template or the migrations README, whichever exists; ask on the board if neither does).

### Private-report tombstones can be flushed by flooding (sc-353, 2, security)
Ticket: `backend/app/services/fetch_persistence.py:102-109` (`_bury`, cap 1024, oldest-first
eviction). A summary for a made-up code yields a "gone" signal and a tombstone; ~1024 such codes in
the in-flight window evict a real tombstone (bounded by the WCL budget, needs a grant to matter).
When the write queue is full, gone/private signals are dropped like any write. Batch summaries whose
report entry is null give no signal. Suggested fix: never evict tombstones younger than the in-flight
window (or only tombstone codes the store knows); never drop gone/private signals from the queue;
treat a null batch entry as gone.
Acceptance criteria:
1. Flooding with made-up codes can't evict a real tombstone inside the in-flight window (test with more than the cap).
2. Gone/private signals are never dropped when the write queue is full (test).
3. A null report entry in a batch summary produces a gone signal (test).
4. Memory stays bounded: state the bound in the spec.

### Stored-reports lookup: own-summary flag and grants-driven scan (sc-354, 3, security + data)
Ticket: `backend/app/repositories/raw_fetches.py` `list_visible_summaries` (~:508). The 200-row LIMIT
runs before the "our own summary" key check, so hand-written `query ReportSummary` rows (via
run_wcl_graphql) on public codes can crowd out real rows: the lookup returns not_stored (nothing
leaks). Re-deriving each row's query key costs ~24 ms per lookup. Since 049 the scan is bounded by
`fetched_at >= since`: a summary fetched before the window but kept visible by a grant from a
different query is no longer listed (rare). Suggested fix: write an `own_summary` flag at store time
and filter/index on it; drive the candidate set from the workspace's recent grants + public-checked
reports (indexes on raw_reports.checked_at and raw_fetch_grants; migration).
Acceptance criteria:
1. Rows stored by the app's own summary query carry an `own_summary` flag set at write time; the migration backfills existing rows correctly (test the backfill on Postgres).
2. The lookup filters on the flag in SQL before the LIMIT: a test with more than 200 hand-written `ReportSummary` rows on public codes still returns the real rows.
3. A summary fetched before the window but visible through a recent grant is listed (test).
4. Visibility is unchanged: a workspace never sees a row it could not see before (Postgres RLS test with two tenants, private and public reports, grants from another workspace).
5. No per-row query-key re-derivation in the lookup loop; record a before/after timing in the hand-off.

## Hand-off
Board `handoff` plus your final result: branch, commits, files, the `check.py` RESULT and RECEIPT
lines (use `--pg`), risks, AC mapping per story.
