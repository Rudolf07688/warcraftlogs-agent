---
id: stored-reports-lookup-candidates
anchors: [sym:backend/app/repositories/raw_fetches.py::list_visible_summaries, sym:backend/app/repositories/raw_fetches.py::_candidate_codes, comp:postgres]
by: dev-1 Ansel
source: meta/team/dev-1.md L13; meta/sprints/2026-11-02/board.jsonl #34
verified: b9cf9a3 2026-11-05
---
On Postgres the stored-reports lookup reads only own-summary rows that name a code
confirmed public, or granted to the tenant, since `since` (`_candidate_codes`). The partial
GIN index `ix_raw_fetches_own_summary_codes` serves it. Visibility itself still comes from
`fetch_visible_clause`. `SUMMARY_LIST_TIMEOUT_MS` is set as a transaction-local
statement_timeout and stays in force for the rest of the caller's transaction.
