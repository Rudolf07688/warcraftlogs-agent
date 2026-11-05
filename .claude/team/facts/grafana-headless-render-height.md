---
id: grafana-headless-render-height
anchors: [file:observability/grafana/dashboards/, comp:grafana]
by: po Maren, dev-3 Nils
source: meta/team/po.md L20; meta/sprints/2026-11-04b/board.jsonl #86, #93
verified: 32010a6 2026-11-05
---
Grafana leaves the uPlot canvases blank for panels outside the browser window. A headless
screenshot with a window shorter than the page therefore shows empty time series: legends,
no lines, no axes. Use a window taller than the page (D7 needs about 2800 px at 1600 px wide), or
screenshot each panel.
