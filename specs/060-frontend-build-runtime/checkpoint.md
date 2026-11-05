# Checkpoint (2026-11-05, before implementation)

Decisions: board scope:060:boundary, :route, :events, :d12, :redaction; grant #17 (one line in
test_telemetry_metrics_dashboards.py). Faro Loki lines are logfmt (kind=..., view_name,
value_<vital>, event_name, event_data_<attr>); session_id is masked by Alloy, so sessions come
from session_start events. target_info{job="wcl-agent/api"} carries service_version (no
service_name label). Stack: COMPOSE_PROJECT=wcl-obs-tomas, ports 26317/26318/26345/26000/26347.
Implementation starts at tasks.md T001.
