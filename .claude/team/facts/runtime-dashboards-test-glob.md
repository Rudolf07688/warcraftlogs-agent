---
id: runtime-dashboards-test-glob
anchors: [file:observability/grafana/dashboards/runtime/, file:backend/tests/test_telemetry_metrics_dashboards.py]
by: dev-2 Tomas
source: meta/team/dev-2.md L14
verified: b9cf9a3 2026-11-05
---
`test_telemetry_metrics_dashboards.py` globs every `*.json` in `dashboards/runtime/`
(except `frontend.json`) and requires each Mimir query to use only the aliases in
`runtime.yaml` or the contracted aliases. A new dashboard file there falls under that test
(in 060 one broke two tests). Either place it elsewhere or ask for the one-line grant on the
test at specify time.
