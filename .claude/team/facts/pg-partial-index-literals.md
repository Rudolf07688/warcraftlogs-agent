---
id: pg-partial-index-literals
anchors: [sym:backend/app/repositories/raw_fetches.py::_candidate_codes, file:backend/tests/test_047_stored_reports_pg.py, comp:postgres]
by: dev-1 Ansel
source: meta/team/dev-1.md L17
verified: 03a3982 2026-11-07
---
Under asyncpg, Postgres uses a partial index only when the query's predicate value is a SQL
literal, not a bound parameter. That is why `_candidate_codes` uses
`literal_column("'public'")`, so `ix_raw_reports_public_checked` matches. To prove a plan,
run EXPLAIN after `SET LOCAL enable_seqscan = off` and assert the index appears, as
`test_047_stored_reports_pg.py` does.
