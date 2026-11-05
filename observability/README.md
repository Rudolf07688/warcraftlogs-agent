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

**Inside a `bin/claude-otel` session** the `OTEL_*` settings configure Claude Code itself and
do **not** reach the commands its Bash tool runs: Claude Code passes only
`CLAUDE_CODE_ENABLE_TELEMETRY`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA` and `TRACEPARENT` (its
tool span) to Bash. A backend started there exports only when its endpoint is set explicitly
(`OTEL_EXPORTER_OTLP_ENDPOINT`; the compose backend has it). `board.py` stores the
`TRACEPARENT` on each board entry (see Team board below).

Host ports, all on 127.0.0.1 and overridable for a second stack: `ALLOY_OTLP_GRPC_PORT`
(4317), `ALLOY_OTLP_HTTP_PORT` (4318), `ALLOY_UI_PORT` (12345), `ALLOY_FARO_PORT` (12347, the
browser receiver), `GRAFANA_PORT` (3000). The backends publish no host ports. Two mounts also
have overrides: `TEAM_BOARD_DIR` (the board files Alloy tails, default `./.git/team-board`)
and `MIMIR_RULES_DIR` (the recording rules, default `./observability/mimir/rules`).

## Pipeline (`alloy/config.alloy`)

Inputs → memory limiter → stamp defaults (`stamp.ottl`) → redaction (`redact.ottl` and the
log body rules) → metrics: drop `session.id`, `ccr.session.id`, `prompt.id`, `user.id`,
`user.account_uuid`, `user.account_id`, `user.email`, `user.groups`, `organization.id`,
`client_request_id` → logs: drop records outside Loki's accept window (below), then content
routing → batch → exporters. The inputs are OTLP (4317, 4318), the Faro receiver (12347, behind
its own overwrite-the-resource transform) and the team board's files (tailed and mapped to log
records). Faro joins at the memory limiter and the board at the redaction step (it skips the
stamp, which would strip its path marker), so both pass every later step. After redaction, traces from `api` and `claude-code` also feed
the span-metrics and service-graph connectors, whose metrics rejoin at the identifier-dropping
step. The recording rules in Mimir's ruler work on the stored metrics.

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
  `content="true"` and is kept 7 days. The team board is the one build-layer source that is
  not content, and the exception follows the path, not the payload: only records from the
  board's own branch carry the marker attribute `alloy.board` (the stamp step deletes it
  from every other source), so an OTLP sender that names itself `team-board` still lands in
  the content stream.
- **Loki's accept window** (`otelcol.processor.filter.log_window`, every log source): a
  record dated more than 6 days back or more than 10 minutes ahead (its time, else its
  observed time) is dropped before the export queue and counted in
  `otelcol_processor_filter_logs_filtered_total`. Loki refuses older or later records anyway,
  and before its schema start it answers with a retryable 503, which would hold the queue
  and every record batched with it.
- **Defaults stamped when missing**: `service.namespace=wcl-agent`,
  `deployment.environment.name=unknown`, `app.layer` = `build` for `claude-code`, else
  `runtime`.
- **Loki index labels**: `service_namespace`, `service_name`, `deployment_environment_name`,
  `app_layer`, `content`; every other attribute is structured metadata.

## Team board (`.claude/team/board.py`, feature 055)

Alloy tails the board's own JSONL files, `sprint-*.jsonl` and `selftest-*.jsonl` in
`$(git rev-parse --git-common-dir)/team-board/` (mounted from `TEAM_BOARD_DIR`, default
`./.git/team-board`; in a worktree `./.git` is a file, so export `TEAM_BOARD_DIR` there).
A line without both `text` and `kind` is dropped, never forwarded raw. The records go through
the same chain as OTLP logs from redaction on, so board text is redacted like everything
else. One record per entry: body = text, timestamp = the entry's
`ts`, `service_name="team-board"`, the fields (`board`, `author`, `kind`, `key`, `entry_id`,
`supersedes`) as structured metadata, and the `TRACEPARENT` Claude Code passed to the
posting Bash command as the record's trace and span id: the Loki "View trace" link opens the
author's tool span (the trace id alone is the lead's turn, shared by its sub-agents). Board
entries stay in the 30-day stream. Find a sprint's hand-offs with
`{service_name="team-board"} | kind="handoff" | board="sprint-2026-11-04b"`.

After Loki lost its data, `observability/board-backfill.sh` re-reads every board file. Only
recent history comes back: Loki refuses an entry more than about an hour behind the newest
entry already in its stream (a 400 the exporter drops, so nothing gets stuck), and all
boards share one stream, so older sprints' entries are lost (they are in `meta/sprints/`;
backlog `055-board-history`; a per-board index label would fix it). Entries older than 6 days
are dropped by the accept window anyway. Re-reading twice does not duplicate. Session
transcripts are not tailed.

## Recording rules (`mimir/rules/anonymous/`, feature 055)

The Mimir ruler reads one rule file per owner from the repository (tenant `anonymous`),
re-read every minute, evaluated every minute. Dashboards query these aliases, never raw
metric names (spec §8.3); the list is in `specs/055-build-telemetry/contracts/aliases.md`.
Probe: `GET mimir:9009/prometheus/api/v1/rules`.

- `build.yaml`: `cc:*` from Claude Code's metrics (D1, D2). `cc:cache_hit_ratio` is
  cacheRead / (input + cacheRead + cacheCreation); output tokens are not input. Counts of
  discrete events in D1 (sessions started, lines of code, commits, pull requests, active time)
  and of turns, calls, searches and lookups on D6-D8 are the one exception to "aliases only":
  `increase()` of the raw counter over the range (rounded for counts), because a rule's copy
  loses the counter's created-time zero sample and a rate alias summed over a range gives
  fractions. Ratio panels divide two totals with no `* 60`.
- `red.yaml`: `app:http_requests:rate5m`, `app:http_latency:p95` from the spanmetrics
  connector (`traces_spanmetrics_calls`, `traces_spanmetrics_duration_bucket` in seconds, with
  exemplars; `traces_service_graph_*`). An aggregate idle for 5 minutes expires, and one
  aggregate is kept per promoted resource, so a new `service.version` continues the same
  series. Only spans of `api` and `claude-code` feed the connectors: browser spans carry
  browser-controlled names.
- `cost.yaml`: generated from `pricing/pricing.yaml` (below).
- `runtime.yaml` (feature 056): `genai:*`, `rag:*`, `cache:*` and `db:*` from the backend's
  ADK and app metrics (`app.rag.*`, `app.cache.requests`, `app.llm.stream.ttft`), which are native
  histograms, so sums and counts use `histogram_sum` and `histogram_count`; for D6-D8.

## LLM pricing (`pricing/pricing.yaml`, feature 055)

List prices in USD per million tokens per model and token type. A price change is a commit to
`pricing.yaml` plus `uv run python observability/pricing/generate.py`, which rewrites
`mimir/rules/anonymous/cost.yaml` (a test fails when the two differ). The rules record
`llm_price_usd_per_token{gen_ai_request_model, gen_ai_token_type}` every minute, so the price
history is a time series and cost already recorded keeps the price of its time; from the
backend's token usage they compute `genai:cost_usd:rate5m` (USD/s by model and agent). Cost per
hour is `3600 * sum(genai:cost_usd:rate5m)`. Cached input is priced as input (the backend
reports input and output only). Seat cost on D2 comes per sprint from
`.claude/team/teamstats.py`, priced at `claude-opus-5-5`. Gemini 3.6, 3.7 and 3.8 Flash are
Google's Vertex AI list price (checked 2026-11-04): $0.75 input / $3.75 output per million
tokens, introductory through 2026-12-31; from 2027-01-01 the standard price is $1.50 / $7.50, so
change those rows in a commit on that day. Flash-Lite and 3.1 Pro are not verified.

## Persistence and the export queue

Every backend and Grafana has a named volume. Each Alloy exporter has a persistent queue
(`otelcol.storage.file`, public preview, hence `--stability.level=public-preview`) on the
`alloy-data` volume, retried until the backend is back (Tempo and Mimir without limit; Loki for
24 hours: in a longer outage the batches being retried at that moment, at most one per
consumer, are dropped and the rest of the queue lands when Loki is back; a refusal that can
never succeed frees its consumer instead of holding it for good). Caps: traces 256 MiB, logs
256 MiB, metrics 64 MiB. **When a queue is full** Alloy refuses new data for that signal
with a retryable error (the sender's SDK retries briefly, then drops it); senders never
block, and the queued data still drains first when the backends start.

Loki's schema starts 2026-01-01, well before any data: a record before the start would get a
retryable 503.

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
| `test/board.sh` | Board entries (written by `board.py`) in Loki with their traceparent and only allowlisted index labels; a seeded secret masked; an entry posted while Loki is down arrives; backfill after Loki data loss, without duplicates; entries before the schema start or in the far future are dropped by Alloy and do not hold back current ones; only `sprint-*` and `selftest-*` files are tailed and only board entries forwarded; an OTLP sender naming itself `team-board` stays in the content stream. |
| `test/queue-drain.sh` | A Loki export queue stuck on a refusal (an old entry before the schema start, batched with a current one) drains on the same volumes once the repository's Alloy and Loki config is deployed, and data stored before the switch is kept. `lib.sh` layers an extra compose file through `COMPOSE_OVERRIDE`. |
| `test/red.sh` | Spanmetrics and service-graph series from synthetic spans with exemplars and no id/URL/SQL/session label; browser spans stay out; the RED aliases, latency without `/ws/chat` and `.*/generate`. |
| `test/rules.sh` | Every rule file loads and evaluates (mimirtool lint for build/red); `cc:*` from synthetic Claude Code metrics; `genai:cost_usd:rate5m` = tokens x list price for one Claude and one Gemini model; a price change (in a mounted copy) loads without a restart and cost recorded before keeps the old price. |
| `test/dashboards.sh` | D1, D2 and D13 provision; every panel query of D1 and D2 is valid against Mimir, Loki and Tempo. |
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
  parents "chat turn" on it; anything invalid or missing there starts a fresh root trace. REST calls are different: FastAPI's own instrumentation takes the browser's `traceparent` (and `baggage`) as it comes, without these checks (a known gap, backlog sc-459).

| Script | Proves |
|---|---|
| `test/faro.sh` | The app origin with the key is accepted; a wrong or missing key is refused; the preflight from another origin gets no CORS grant; a burst is rate limited; an oversized body is refused; no source map is fetched; a payload posing as the API / build layer lands as web / runtime / dev; Web Vitals and a log arrive in Loki with a seeded secret masked, and a browser span arrives in Tempo with its `session.id`. Needs `ALLOY_FARO_PORT` (default 24347). |

## Profiles and runtime dashboards (059)

**Span profiles** (spec §6.7, sc-421). The `pyroscope` service (observability profile,
`grafana/pyroscope:2.4.3`, volume `pyroscope-data`, 7-day retention, `127.0.0.1:${PYROSCOPE_PORT:-4040}`)
receives CPU profiles straight from the API: no Alloy hop. The backend profiles only when
telemetry is on and `PYROSCOPE_SERVER_ADDRESS` is set (compose sets `http://pyroscope:4040`);
the test suite sets neither, so no profiler starts there. `pyroscope-otel`'s
`PyroscopeSpanProcessor` gives every *root* span (a request, a chat turn) the attribute
`pyroscope.profile.id` and tags the CPU samples taken meanwhile with the same `span_id`;
Tempo's `tracesToProfiles` turns that into **Profiles for this span** on the span in Grafana.
Limits: samples are tagged per OS thread, and every asyncio request shares the event-loop
thread, so two requests running at once share their samples; spans shorter than a few
sampling intervals (100 Hz) may show an empty flame graph.

**Service graph** (sc-462). Tempo's `serviceMap` reads Alloy's `traces_service_graph_*` from
Mimir; D6 (App: API RED) shows it as a node graph. That panel is the one that queries raw
names: Grafana's service map asks for those series by their fixed names. It wants the edge
latency as `traces_service_graph_request_server_seconds_bucket`, so `runtime.yaml` records a
copy of `traces_service_graph_request_server_bucket` under that name (Mimir adds no unit
suffix). Pyroscope runs the v2 storage only (`-architecture.storage=v2`: a new install has
no v1 data, and in the default dual mode its reads looked for v1 data and found none).

**New app metrics** (all labels on `setup.METRIC_ATTRIBUTES`):

| Metric | Labels | Recorded |
|---|---|---|
| `app.llm.finish_reasons` | `gen_ai.request.model`, `app.llm.finish_reason` (google-genai's reason names, anything else `other`) | each non-partial model response |
| `app.agent.turns_per_conversation` | `gen_ai.agent.name` | the end of each chat turn: the turns so far, from `app_turns` in the ADK session state (older conversations count from their first turn after 059) |
| `app.embedding.duration`, `app.embedding.batch_size` | `gen_ai.request.model`, `app.embedding.task` (`document`, `query`) | each provider embedding request |

Aliases (`runtime.yaml`): `app:http_latency:p50` and `:p99` (beside red.yaml's p95, same
exclusions), `genai:finish_reasons:rate5m`, `genai:turns_per_conversation:p50`/`:p95`,
`rag:embedding_latency:p95`, `rag:embedding_batch_size:avg5m`. D7 shows finish reasons and
depth, D8 embedding latency and batch size. Feedback ratio (§7.5) is not built: the app has
no feedback feature. Any panel with per-interval bars or legend totals must read windows of
`$__interval` with its `interval` set (sc-471); `test_telemetry_metrics_dashboards.py` checks it.

**Board backfill window** (sc-463): accepted at what it is. Alloy drops records older than 6
days and Loki refuses anything past 7 (`reject_old_samples`). That limit is per tenant, and
there is one tenant, so it can't be widened for the board stream alone; widening it for
everything would admit week-old content records that the 7-day content retention deletes
again. Older sprints' boards are in `meta/sprints/*/board.jsonl`, and D13 is fed by
`teamstats.py`, not Loki.

`test/provisioning.sh` also proves: the Pyroscope datasource and Tempo's `serviceMap` and
`tracesToProfiles`; the D6 service-graph query returns an edge; a CPU-bound span run through
the real bootstrap carries its profile id and Pyroscope returns its flame graph; an 8-day-old
board entry is dropped while a fresh one in the same file lands. Set `PYROSCOPE_PORT`
(default 24040) with the other port overrides.

## Frontend, build vs runtime and redaction e2e (060)

**D5, App: Frontend** (`grafana/dashboards/runtime/frontend.json`, uid `wcl-d5-frontend`) reads
Faro's lines in Loki directly (no Loki ruler): Web Vitals p75 by route, JS errors per minute
and the top errors with route and boundary, client-side TTFT, stream aborts, sessions
(`session_start` events; the session id itself is masked) and turns. The route is the React
Router template (`/app/*`, never a raw path), which the app sets as Faro's view, so every line
carries `view_name`. The app (`frontend/src/telemetry/`):

- **Error boundaries** around the app shell and each chat panel (sidebar, message list,
  composer): a panel that throws shows a plain "Something went wrong" with Retry, never the
  error text (it can carry model or WCL text); the other panels keep working; the error goes
  to Faro as `React ErrorBoundary <type>` with the component stack, `context_route` and
  `context_boundary`. The boundary reports through the registered Faro instance, so Faro stays
  out of the main bundle; with Faro off it only shows the fallback.
- **Chat events**, once per turn: `agent_message_sent`, `agent_first_token_rendered`
  (`ttft_ms`, after the first token is on screen), `agent_response_completed` (`duration_ms`),
  `stream_aborted` (`reason` `connection_lost`, or `closed` when the app closed the socket,
  e.g. leaving the chat; an error frame is not an abort). Attributes: the model and whole
  milliseconds, never text or ids. `agent_feedback` is not sent (no feedback feature, §7.5).

**D12, Build vs Runtime** (`grafana/dashboards/cross/build-runtime.json`, uid
`wcl-d12-build-runtime`): annotations for each api version while it ran, p95 latency, error
ratio and LLM cost per request by commit, and a table commit → seat → estimated build cost →
runtime deltas. Its aliases are in `mimir/rules/anonymous/cross.yaml`: the running version
comes from `target_info{job="wcl-agent/api"}` (`service.version` is not a promoted label), the
seat from `build_commit_info`, which `build-runtime/commits.py` pushes from the team boards,
the roster and `usage.txt` (run it at wrap-up next to `teamstats.py`; `--dry-run` prints the
table). The attribution rule, the cost estimate and the delta definition are stated on the
dashboard and in `commits.py`'s docstring. A version no board entry names is *unattributed*.

**Redaction end to end** (`test/redaction_e2e.py`): fresh secrets of each shape in `SHAPES`
(bearer, JWT, `sk-`, `AIza`, DSN password) go through each path in `PATHS`: the build layer
(OTLP shaped like Claude Code's: logs with its event names, a span with a `tool.output` event,
a metric), the backend's real telemetry bootstrap in a subprocess (span attributes, a span
event, a log record through the OTLP log handler, an allowlisted metric attribute, the
resource), and the Faro receiver (log, exception, event, measurement context, a span). Then
everything Loki, Tempo and Mimir hold for the run is read back (log lines with structured
metadata, whole traces, every series' labels including `target_info`); any raw value fails
the run. A new shape or path is one row (the Postgres slow-query log from 058 goes in
`PATHS`). The app-side redactor never sees resource attributes; Alloy masks them.

| Script | Proves |
|---|---|
| `test/frontend.sh` | D5 provisions; its own queries return a synthetic component error with route `/app/*` and boundary, LCP/INP/CLS p75 for the route, client TTFT, one stream abort, sessions and turns. |
| `test/redaction-e2e.sh` | No seeded secret is stored unmasked on any path; then the check fails on each of five mutated copies of the Alloy config (JWT, bearer, `AIza`, URL password attribute masks; `sk-` body mask). `MUTATE=0` skips the mutations. |
| `test/build-runtime.sh` | Two api versions as real spans and metrics, a synthetic board: D12's table shows the regression commit against its seat with positive p95, error and cost deltas and its build cost; the annotations and timeseries show both commits. `PHASE_S` sets each version's run time (default 240 s). |

All three set `ALLOY_FARO_PORT` (default 24347) and run their own compose project like the
other scripts.
