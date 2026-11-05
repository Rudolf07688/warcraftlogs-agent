---
id: absent-label-matches-not-equal
anchors: [file:observability/mimir/rules/anonymous/cross.yaml, file:observability/alloy/config.alloy, comp:mimir, comp:alloy]
by: dev-3 Nils
source: meta/team/dev-3.md L22, L39; meta/sprints/2026-11-05/board.jsonl #95
verified: b9cf9a3 2026-11-05
---
In PromQL an absent label matches `!="x"`. Alloy's spanmetrics `target_info` has no
`service_version`: the `spanmetrics_version` transform deletes it, because the connector
keeps its first span's whole resource and would export a stale version. So
`service_version!="unknown"` also selects it. Use `service_version!~"|unknown"` to exclude
both. Check other streams' selectors against any label your change removes.
