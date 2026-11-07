---
id: fetch-visible-clause-one-rule
anchors: [sym:backend/app/repositories/raw_fetches.py::fetch_visible_clause, sym:backend/app/repositories/raw_fetches.py::fetch_names_code, comp:postgres]
by: dev-3 Nils, sm Ilse
source: meta/team/dev-3.md L12; meta/sprints/2026-11-01/board.jsonl #15, #106, #107
verified: 03a3982 2026-11-07
---
Visibility for the global tables (`raw_fetches`, `kb_chunks`) lives in the SQL of every read
branch, and it has one definition: `raw_fetches.fetch_visible_clause`, the 039 rule (every code
public or granted to the tenant since `since`). Rows derived from a fetch must also pass
`fetch_names_code` (a chunk's `report_code` is one of its fetch's codes). Join these two;
never re-implement the rule. The raid summary's reads (`read_visible_summary`,
`read_visible_parts`) join it too.
