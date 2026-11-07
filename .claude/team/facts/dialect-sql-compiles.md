---
id: dialect-sql-compiles
anchors: [sym:backend/app/repositories/raw_fetches.py::fetch_visible_clause, file:backend/app/repositories/raw_fetches.py]
by: dev-2 Tomas
source: meta/team/dev-2.md L16
verified: 03a3982 2026-11-07
---
Dialect-specific SQL inside a clause with a fixed signature is written as a `ColumnElement`
subclass with one `@compiles` per dialect. In `raw_fetches.py`, `_NonEmpty` uses
`jsonb_array_length` on Postgres and `json_array_length` on SQLite, and `_CodesVisible`
works the same way. Callers keep one function that runs on both test engines.
