---
id: ratio-panels-min-max
anchors: [file:observability/grafana/dashboards/, comp:grafana]
by: dev-3 Nils
source: meta/team/dev-3.md L28; meta/sprints/2026-11-04b/board.jsonl #86
verified: b9cf9a3 2026-11-05
---
Give every `percentunit` time-series panel `min: 0` and `max: 1`. An all-zero ratio series
otherwise auto-scales to 0..100, which reads as 10000%. At b9cf9a3, D1's "Cache hit ratio
over time" (`claude-code-overview.json`) still has no bounds.
