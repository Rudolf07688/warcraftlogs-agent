---
id: pg-tests-shared-db
anchors: [file:backend/tests/, comp:postgres]
by: dev-3 Nils
source: meta/team/dev-3.md L13
verified: 9107884 2026-11-22
---
The Postgres tests (`*_pg.py`, `test_rls.py`, via `TEST_DATABASE_URL`) share one long-lived
database with no reset between tests. Use unique test data (fresh UUIDs and report codes),
and never assert exact result lists over global tables (`raw_fetches`, `kb_chunks`,
`spec_guides`): other tests' rows are there too.
