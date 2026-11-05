---
id: grafana-servicemap-browser
anchors: [file:observability/grafana/dashboards/runtime/api-red.json, file:observability/test/provisioning.sh, comp:grafana, comp:tempo]
by: dev-3 Nils
source: meta/team/dev-3.md L25; meta/sprints/2026-11-05/board.jsonl #46, #48
verified: 32010a6 2026-11-05
---
Grafana runs the Tempo `serviceMap` query in the browser, and `/api/ds/query` refuses it,
so a stack test can't run the panel the way Grafana does. Instead, run its Prometheus queries
(`traces_service_graph_*`, by the fixed names Grafana uses) through the Mimir datasource, as
`provisioning.sh` does.
