---
id: exporter-counters-first-sample
anchors: [file:observability/mimir/rules/anonymous/datastores.yaml, comp:mimir, comp:alloy]
by: dev-1 Ansel
source: meta/team/dev-1.md L19; meta/sprints/2026-11-05/board.jsonl #52
verified: 32010a6 2026-11-05
---
Scraped exporter counters (`pg_stat_statements_*`, Alloy's `otelcol_*_failed_*`) appear with
their first value already counted, so `rate()`/`increase()` miss a one-off event, such as a
single slow statement or one failed export. Read cumulative aliases (`pg:statement_seconds:total`)
or use `sum(x) - (sum(x offset w) or vector(0))`, as the pipeline-failure alert in
`datastores.yaml` does.
