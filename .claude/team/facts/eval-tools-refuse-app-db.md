---
id: eval-tools-refuse-app-db
anchors: [sym:backend/evals/kb/__main__.py::refuse_database, file:backend/evals/]
by: dev-3 Nils
source: meta/team/dev-3.md L29; meta/sprints/2026-11-01/board.jsonl #69, #107, #124
verified: b9cf9a3 2026-11-05
---
The KB eval (`run`/`live`) seeds fake public reports and global guide chunks, which every
workspace would see. Its CLI refuses the app's database: `refuse_database` checks the
database it actually connected to, not the URL string, and an unreachable one is refused too.
Any new eval or seed tool must refuse the same way.
