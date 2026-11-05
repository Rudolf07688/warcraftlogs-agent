---
id: raw-fetches-own-summary-flag
anchors: [sym:backend/app/repositories/raw_fetches.py::is_own_summary, sym:backend/app/repositories/raw_fetches.py::upsert_raw_fetch]
by: dev-1 Ansel
source: meta/team/dev-1.md L13; meta/sprints/2026-11-02/board.jsonl #31, #63
verified: b9cf9a3 2026-11-05
---
`own_summary` marks rows written by our own `ReportSummary` query. `is_own_summary` matches
the query text whole, so a hand-written look-alike never qualifies. `upsert_raw_fetch` sets
the flag on insert and on the unchanged-body update path too (051 QA BUG-002), so a write
path that skips it hides that summary from the stored-reports lookup.
