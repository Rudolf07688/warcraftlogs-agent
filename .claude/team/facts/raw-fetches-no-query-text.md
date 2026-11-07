---
id: raw-fetches-no-query-text
anchors: [sym:backend/app/db/models.py::RawFetch, file:backend/app/repositories/raw_fetches.py]
by: dev-1 Ansel
source: meta/team/dev-1.md L13; meta/sprints/2026-11-01/board.jsonl #35
verified: 03a3982 2026-11-07
---
`raw_fetches` rows keep the params, report codes and payload, never the GraphQL query
text. Anything that depends on the query's shape has to be decided when the row is written,
the way `own_summary` is, or inferred from the body. The KB backfill skips stored tables
whose metric it can't infer from the body.
