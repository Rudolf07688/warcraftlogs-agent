# Checkpoint 051 (before implement)

Decisions: board `clarify:051-*` (#26–#30), risk `risk:051` (#31). Spec Clarifications mirror them.

- Tombstones: cap kept, in-window overflow raises `_tombstones.floor`; codes > 32 not buried.
- Signals: ReportGone uncapped; dropped own summaries salvaged to codes-only ReportGone.
- Null batch entry `r{i}` → gone code `c{i}` (stored bodies never carry errors).
- `own_summary` column, write-time rule = exact own query text + exact codes; 0021 backfills with
  the old `_our_summary` rule.
- Lookup: no `fetched_at` bound; Postgres driver `?|` over grant ∪ public codes since `since`,
  partial GIN; SQLite no driver.
- 0020 index replaced by 0021 (dropped concurrently).

Files: see plan.md Project Structure. Implementation starts at T002 (0020 CONCURRENTLY).
