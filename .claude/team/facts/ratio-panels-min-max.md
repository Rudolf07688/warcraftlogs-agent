---
id: ratio-panels-min-max
anchors: [file:observability/grafana/dashboards/, comp:grafana]
by: dev-3 Nils
source: meta/team/dev-3.md L28; meta/sprints/2026-11-04b/board.jsonl #86
verified: b9cf9a3 2026-11-05
---
Give every `percentunit` time-series panel `min: 0` and `max: 1`. An all-zero ratio series
otherwise auto-scales to 0..100, which reads as 10000%. Every dashboard follows this since
sc-508; `test_team_dashboards.py` (build) and `test_telemetry_metrics_dashboards.py` (runtime)
enforce it.
