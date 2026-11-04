# Data model: 054 backend telemetry

No stored data. One in-process value:

## TelemetryConfig (frozen dataclass)
| Field | Source | Rule |
|---|---|---|
| `enabled` | `OTEL_EXPORTER_OTLP_ENDPOINT` | non-empty after strip |
| `environment` | `WCL_ENVIRONMENT` | `dev`/`ci`/`prod` (trimmed, lower-case); anything else → `unknown` |
| `content_allowed` | environment | `environment == "dev"` only |
| `version` | `WCL_GIT_SHA` → `git rev-parse --short HEAD` → `unknown` | |

## Resource
`service.name=api`, `service.namespace=wcl-agent`, `service.version`, `vcs.ref.head.revision`,
`deployment.environment.name`, `app.layer=runtime`.
