# Observability stack (feature 053)

Local telemetry for both layers: the app (runtime, `app.layer=runtime`) and the Claude Code
team that builds it (build, `app.layer=build`). Design: `specs/telemetry_spec.md`; this
sprint's scope and decisions: `specs/053-telemetry-stack/`.

## Run it

| Command | What runs |
|---|---|
| `docker compose up` | The app plus **Alloy** only. Alloy is always on (`restart: unless-stopped`) and queues telemetry on disk while the backends are absent. |
| `docker compose --profile observability up -d` | Adds **Loki** (logs), **Tempo** (traces), **Mimir** (metrics) and **Grafana**. |
| `bin/claude-otel [args]` | Claude Code with telemetry to Alloy (spec §5.2), OTLP http/protobuf on `ALLOY_OTLP_HTTP_PORT` (4318). Warns and still starts when Alloy is down. |

Grafana: <http://127.0.0.1:3000> (loopback only, no stored telemetry; datasources come from
`grafana/provisioning/`). Anonymous visitors are **Viewers** who can use Explore. The `admin`
login takes `GRAFANA_ADMIN_PASSWORD` from `.env`, set again on every start
(`grafana/entrypoint.sh`), so an older volume made with `admin/admin` is fixed too; unset or
empty means a random password, i.e. no admin login. No plugins are preinstalled.
Alloy UI: <http://127.0.0.1:12345>.

**service.version** of the backend comes from `WCL_GIT_SHA`; the image has no `.git`.
`bin/01_start_app.sh` exports it; a plain `docker compose up` needs
`export WCL_GIT_SHA=$(git rev-parse --short HEAD)` first, or every signal says `unknown`.

**Inside a `bin/claude-otel` session** every command inherits its `OTEL_*` settings. A
backend started there exports over http/protobuf to Alloy's port 4318 as it should (its own
`app.layer=runtime` wins over the inherited `OTEL_RESOURCE_ATTRIBUTES`); its metric interval
becomes the wrapper's 10 s. Any other OTel-aware tool started there exports too, tagged
`app.layer=build`, so its logs go to the content stream.

Host ports, all on 127.0.0.1 and overridable for a second stack: `ALLOY_OTLP_GRPC_PORT`
(4317), `ALLOY_OTLP_HTTP_PORT` (4318), `ALLOY_UI_PORT` (12345), `GRAFANA_PORT` (3000).
The backends publish no host ports.

## Pipeline (`alloy/config.alloy`)

OTLP in → memory limiter → stamp defaults (`stamp.ottl`) → redaction (`redact.ottl` and the
log body rules) → metrics: drop `session.id`, `ccr.session.id`, `prompt.id`, `user.id`,
`user.account_uuid`, `user.account_id`, `user.email`, `user.groups`, `organization.id`,
`client_request_id` → logs: content routing → batch → exporters.

- **Redaction** (both layers, every signal): the values of `access_token`, `refresh_token`,
  `client_secret`, `authorization`, `api_key`, `password` become their SHA-256. Masked to
  `<redacted>` (or `<jwt:redacted>`, `<pem:redacted>`) in resource, span, span event, log and
  datapoint attributes and in log bodies (string or map): PEM private-key blocks, JWTs,
  `Bearer`/`bearer` and `Basic` credentials, `sk-*`, `AIza*`, `ya29.` and GitHub
  (`gh[pousr]_`, `github_pat_`) tokens, the password in any `scheme://user:pw@` URL, and the
  value of `NAME=value`, `NAME: value` and `"name": "value"` pairs whose name contains
  secret, password, passwd, token, key, credential, dsn, auth, cookie or session (any case,
  e.g. `WCL_CLIENT_SECRET`, `ANTHROPIC_API_KEY`). The pair rule also masks harmless values
  (`primary_key: id`) in captured content; that is the intended trade. Not covered: values
  inside slices or nested maps, and secrets in no recognisable shape (a bare random string).
- **Content stream** (fails closed for the build layer): a log is content when it has
  `app.content="true"`, an event name starting `gen_ai.`, or comes from the build layer
  (`service.name=claude-code` or `app.layer=build`) and is not a known content-free Claude
  Code event (`api_request`, `api_refusal`, `subagent_completed`, `skill_activated`,
  `hook_registered`, `mcp_server_connection`, `plugin_loaded`, `plugin_installed`,
  `permission_mode_changed`, `retention_sweep`, `internal_error`, `at_mention`, `auth`).
  A new or unnamed Claude Code event is content. Content gets the Loki label
  `content="true"` and is kept 7 days.
- **Defaults stamped when missing**: `service.namespace=wcl-agent`,
  `deployment.environment.name=unknown`, `app.layer` = `build` for `claude-code`, else
  `runtime`.
- **Loki index labels**: `service_namespace`, `service_name`, `deployment_environment_name`,
  `app_layer`, `content`; every other attribute is structured metadata.

## Team board (`.claude/team/board.py`, feature 055)

Alloy tails the board's JSONL files (`$(git rev-parse --git-common-dir)/team-board/*.jsonl`,
mounted from `TEAM_BOARD_DIR`, default `./.git/team-board`; in a worktree `./.git` is a
file, so export `TEAM_BOARD_DIR` there) through the same chain as OTLP logs, so board text is
redacted like everything else. One record per entry: body = text, timestamp = the entry's
`ts`, `service_name="team-board"`, the fields (`board`, `author`, `kind`, `key`, `entry_id`,
`supersedes`) as structured metadata, and the `TRACEPARENT` Claude Code passed to the
posting Bash command as the record's trace and span id: the Loki "View trace" link opens the
author's tool span (the trace id alone is the lead's turn, shared by its sub-agents). Board
entries stay in the 30-day stream. Find a sprint's hand-offs with
`{service_name="team-board"} | kind="handoff" | board="sprint-2026-11-04b"`.

After Loki lost its data, `observability/board-backfill.sh` re-reads every board file
(entries within Loki's 7-day reject window; older sprints are in `meta/sprints/`). Re-reading
twice does not duplicate. Session transcripts are not tailed.

## Recording rules (`mimir/rules/anonymous/`, feature 055)

The Mimir ruler reads one rule file per owner from the repository (tenant `anonymous`),
re-read every minute, evaluated every minute. Dashboards query these aliases, never raw
metric names (spec §8.3); the list is in `specs/055-build-telemetry/contracts/aliases.md`.
Probe: `GET mimir:9009/prometheus/api/v1/rules`.

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
| `test/mutation.sh` | Disabling any one redaction, label or routing rule makes the redaction check fail. Mutates a temporary copy of `alloy/` mounted only into the test project (`ALLOY_CONFIG_DIR`); the checkout's files are never written. |
| `test/provisioning.sh` | Datasources load from file, are healthy and carry the trace↔logs and exemplar correlations; Grafana's anonymous Viewer, admin password (none when unset) and no plugin preinstall. |
| `test/board.sh` | Board entries (written by `board.py`) in Loki with their traceparent and only allowlisted index labels; a seeded secret masked; an entry posted while Loki is down arrives; backfill after Loki data loss, without duplicates. |
| `test/claude-otel.sh` | The wrapper's env, argument pass-through and the Alloy-down warning (stub `claude`, no Docker). |

## Browser telemetry (Faro, feature 057)

The React app reports Web Vitals, errors, route changes and browser traces with Grafana Faro
(`frontend/src/telemetry/`, spec §7.1). It starts only when `VITE_FARO_URL` is set; compose
sets it for the dev server to `http://localhost:12347/collect` (set it empty in `.env` to
switch Faro off), with `VITE_FARO_API_KEY`, `VITE_FARO_APP_VERSION` (`WCL_GIT_SHA`) and
`VITE_FARO_ENVIRONMENT`.

- **Receiver**: `faro.receiver` at the end of `alloy/config.alloy`, published on
  `127.0.0.1:${ALLOY_FARO_PORT:-12347}`. Its logs go through their own `otelcol.receiver.loki`
  bridge and its traces straight into the memory limiter, so both pass the stamp and
  redaction steps; nothing goes to Loki directly. Logs arrive as `service_name=web`,
  `app_layer=runtime`; the lines are logfmt (`kind=measurement type=web-vitals lcp=...`).
- **Protection** (the API key ships in the bundle and is not a secret): `x-api-key` must match
  the receiver's `api_key`; CORS allows only `http://localhost:5173` and `http://127.0.0.1:5173`
  (a browser's preflight from any other origin gets no grant; a non-browser client is not
  stopped by CORS, only by the key and the rate limit); 64 KiB payload cap and a global rate
  limit of 5/s (burst 10), about 0.3 MiB/s at most, because the receiver shares the memory
  limiter and the export queues with the backend and the build layer (global, not per app: an
  app name comes from the payload). Known gap (Alloy 1.21.3): the cap reads `Content-Length`,
  so a chunked body without one is not capped; `faro.sh` reports it. Source maps are never
  downloaded (`sourcemaps { download = false }`): the receiver would fetch any URL a stack
  frame names. The origin, key and limits are literals in `config.alloy`: change them together
  with `VITE_FARO_*` when the app moves.
- **Trusted resource**: the payload is not trusted. A Faro-only transform in front of the memory
  limiter, for logs and traces, overwrites `service.name=web`, `service.namespace=wcl-agent`,
  `app.layer=runtime`, `deployment.environment.name=dev` and removes `content` / `app.content`
  (and a log's `event.name`), so a payload cannot pose as the API or the build layer, nor
  reach the content stream.
- **Privacy**: the user is a salted SHA-256 prefix of the account id (never email or name);
  console output is not captured; Faro's `beforeSend` (`frontend/src/telemetry/scrub.ts`) cuts the
  query and fragment off every URL in an item (page meta, span `http.url`, route events, message
  text), so an invite or reset `#token=` never leaves the browser. The redaction rule for `session=value` pairs also masks
  Faro's `session_id=` in the log lines (`session_id=<redacted>`); the session id is kept as
  the `session.id` attribute on spans (Tempo), where it links a browser session to its
  backend traces. It is never a metric label.
- **Click to Postgres**: Faro's tracing adds `traceparent` to same-origin REST calls, and the
  REST client adds `x-faro-session-id`; a middleware copies that to the span attribute
  `session.id`. A chat send opens a "chat send" span and puts its `traceparent` and the Faro
  session id in the WebSocket message; the backend validates both (`backend/app/telemetry/browser.py`:
  W3C format, 128-character cap, sampled only; session id 1-64 of `[A-Za-z0-9._:-]`) and
  parents "chat turn" on it. Anything invalid or missing starts a fresh root trace.

| Script | Proves |
|---|---|
| `test/faro.sh` | The app origin with the key is accepted; a wrong or missing key is refused; the preflight from another origin gets no CORS grant; a burst is rate limited; an oversized body is refused; no source map is fetched; a payload posing as the API / build layer lands as web / runtime / dev; Web Vitals and a log arrive in Loki with a seeded secret masked, and a browser span arrives in Tempo with its `session.id`. Needs `ALLOY_FARO_PORT` (default 24347). |
