# Contract: alert rules (058)

File `observability/grafana/provisioning/alerting/rules.yaml`, folder "WCL alerts", group
`telemetry`, interval 30 s.

| uid | Title | Condition | Pending | Synthetic trigger |
|---|---|---|---|---|
| `wcl-alert-pipeline` | Telemetry pipeline failures or drops | `sum(meta:exporter_failures:increase2m) > 0` | 0 s | a log record Loki refuses for good |
| `wcl-alert-build-spend` | Build spend per day above threshold | `sum(sum_over_time(cc:cost_usd:rate5m[24h])) * 60 > alert:build_spend_usd_per_day:threshold` | 0 s | synthetic Claude Code cost + a lowered threshold |

No data → Normal (an idle laptop is not an incident). The threshold is changed in `datastores.yaml`.
