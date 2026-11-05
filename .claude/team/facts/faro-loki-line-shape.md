---
id: faro-loki-line-shape
anchors: [file:observability/grafana/dashboards/runtime/frontend.json, comp:loki]
by: dev-2 Tomas
source: meta/team/dev-2.md L24
verified: b9cf9a3 2026-11-05
---
Faro lines in Loki are logfmt (`| logfmt`): `kind=` (measurement, event, exception, log),
`view_name` (the route template), `value_<vital>` (`value_lcp`, `value_inp`, `value_cls`, ...),
`event_name` and `event_data_<attr>` (`event_data_ttft_ms`). `session_id` is masked by the
redaction rules. Find the session id as `session.id` on spans in Tempo. Probe real line
shapes on your own stack before designing queries.
