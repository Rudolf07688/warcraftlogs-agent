# Observability stack (feature 053)

Local telemetry for both layers: the app (runtime, `app.layer=runtime`) and the Claude Code
team that builds it (build, `app.layer=build`). Design: `specs/telemetry_spec.md`; this
sprint's scope and decisions: `specs/053-telemetry-stack/`.

## Run it

| Command | What runs |
|---|---|
| `docker compose up` | The app plus **Alloy** only. Alloy is always on (`restart: unless-stopped`) and queues telemetry on disk while the backends are absent. |
| `docker compose --profile observability up -d` | Adds **Loki** (logs), **Tempo** (traces), **Mimir** (metrics) and **Grafana**. |
| `bin/claude-otel [args]` | Claude Code with telemetry to Alloy (spec §5.2). Warns and still starts when Alloy is down. |

Grafana: <http://127.0.0.1:3000> (anonymous admin, loopback only, no stored telemetry;
datasources come from `grafana/provisioning/`). Alloy UI: <http://127.0.0.1:12345>.

Host ports, all on 127.0.0.1 and overridable for a second stack: `ALLOY_OTLP_GRPC_PORT`
(4317), `ALLOY_OTLP_HTTP_PORT` (4318), `ALLOY_UI_PORT` (12345), `GRAFANA_PORT` (3000).
The backends publish no host ports.

## Pipeline (`alloy/config.alloy`)

OTLP in → memory limiter → stamp defaults (`stamp.ottl`) → redaction (`redact.ottl` and the
log body rules) → metrics: drop `session.id`, `prompt.id`, `user.account_uuid`,
`user.email`, `client_request_id` → logs: content routing → batch → exporters.

- **Redaction** (both layers, every signal): the values of `access_token`, `refresh_token`,
  `client_secret`, `authorization`, `api_key`, `password` become their SHA-256; bearer
  tokens, JWTs, `sk-*` and `AIza*` keys and Postgres DSN passwords become `<redacted>` in
  resource, span, span event, log and datapoint attributes and in log bodies (string or map).
  Not covered: values inside slices or nested maps.
- **Content stream**: a log is content when it has `app.content="true"`, an event name
  starting `gen_ai.`, or is a Claude Code `user_prompt`, `assistant_response`, `tool_result`,
  `tool_decision`, `api_request_body` or `api_response_body` event. Content gets the Loki
  label `content="true"` and is kept 7 days.
- **Defaults stamped when missing**: `service.namespace=wcl-agent`,
  `deployment.environment.name=unknown`, `app.layer` = `build` for `claude-code`, else
  `runtime`.
- **Loki index labels**: `service_namespace`, `service_name`, `deployment_environment_name`,
  `app_layer`, `content`; every other attribute is structured metadata.

## Persistence and the export queue

Every backend and Grafana has a named volume. Each Alloy exporter has a persistent queue
(`otelcol.storage.file`, public preview, hence `--stability.level=public-preview`) on the
`alloy-data` volume, retried until the backend is back. Caps: traces 256 MiB, logs
256 MiB, metrics 64 MiB. **When a queue is full** Alloy refuses new data for that signal
with a retryable error (the sender's SDK retries briefly, then drops it); senders never
block, and the queued data still drains first when the backends start.

Retention: logs 30 days, content stream 7 days, traces 7 days (Tempo can't keep content
traces shorter than the rest), metrics 13 months.

## Tests

Each script starts its own compose project (`COMPOSE_PROJECT`, default `wcl-obs-test`) on
non-default ports, prints `PASS`/`FAIL` lines and a `RESULT`, and removes the project and
its volumes at the end (`KEEP=1` keeps it).

| Script | Proves |
|---|---|
| `test/persistence.sh` | A span, a log and a metric sent with the backends stopped (and Alloy restarted) arrive after they start; retention as the backends run it. |
| `test/redaction.sh` | Seeded secrets from both layers are hashed or masked in Loki, Tempo and Mimir; banned metric labels absent; content routing. |
| `test/mutation.sh` | Disabling any one redaction, label or routing rule makes the redaction check fail. Edits `alloy/` in place and restores it: run on a clean tree. |
| `test/provisioning.sh` | Datasources load from file, are healthy and carry the trace↔logs and exemplar correlations. |
| `test/claude-otel.sh` | The wrapper's env, argument pass-through and the Alloy-down warning (stub `claude`, no Docker). |
