# Data model: 058

## Monitoring role (migration 0022)

| Field | Value |
|---|---|
| name | `PG_MONITOR_USER` (default `wcl_monitor`) |
| password | `PG_MONITOR_PASSWORD`; unset → role not created (no default password) |
| attributes | `LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`, member of `pg_monitor`, `CONNECT` on the database |
| downgrade | drops the role (if it exists) and the extension |

## Slow-query (Postgres) log record in Loki

| Part | Content |
|---|---|
| resource | `service.name=postgres`, `service.namespace=wcl-agent`, `app.layer=runtime`, `deployment.environment.name=dev` (index labels via loki.yaml) |
| body | the message after the prefix, literals masked |
| structured metadata | `pg_severity` (LOG/ERROR/DETAIL/STATEMENT…), `pg_sqlstate`, `pg_query_id`, `pg_pid`, `pg_duration_ms` (duration lines), `trace_id`, `span_id` (when a traceparent was present) |
| time | the Postgres timestamp |

## Exporter series (Mimir, remote write)

Jobs: `postgres`, `redis`, `cadvisor`, `alloy`, `loki`, `tempo`, `mimir`; `instance` fixed per job.
Labels never carry SQL text, key names, DSNs or container ids (cadvisor keeps `compose_service`).
Aliases: see contracts/aliases.md.
