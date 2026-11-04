# Brief 053: telemetry stack, claude-otel wrapper, Alloy redaction

- **Feature / branch:** 053, `053-telemetry-stack`
- **Tier:** M (one Spec Kit pass: specify → plan → tasks → implement, no gates; answer your own clarify questions and record them on the board)
- **Seat:** `dev-1` (Ansel). Parallel developer: Nils (dev-3) on 054 backend telemetry, disjoint files.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a` (detached at the base). Base ref: sprint branch tip `sprint-2026-11-04` = `38606fd`. Create your branch there.
- **Security-core:** no (stream B is). But sc-401 is security work: make the redaction test bite.
- **Migration:** none.
- **Read first:** `specs/telemetry_spec.md` §3, §4, §5, §8.1, §10, §14 (decisions 6–12 are binding). The stories below win where they differ.

## Stories (acceptance criteria verbatim from Shortcut)

### Observability stack with persistence and a durable export queue (sc-398, 5)
- Plain `docker compose up` adds only Alloy (pinned image, `restart: unless-stopped`, ports on 127.0.0.1); the app runs unchanged.
- The `observability` profile adds Loki, Tempo, Mimir (monolithic) and Grafana on named volumes with a `mem_limit` each. No MinIO, no Pyroscope.
- Retention: content stream 7 days, logs 30 days, traces 7 days in dev (Tempo can't keep content traces shorter than the rest), metrics 13 months.
- Alloy exporters use `sending_queue` with `otelcol.storage.file` (public preview: run with `--stability.level=public-preview`).
- A span, a log and a metric sent while the backends are stopped show in Grafana after they restart.

### Grafana datasource correlations: trace to logs, logs to trace, exemplar to trace (sc-399, 2)
- Datasources are provisioned as code.
- In Grafana you can click from a trace to its logs, from a log line (`trace_id` structured metadata) to its trace, and from a metric exemplar to its trace.
- Drop first in sprint 1 if it slips.

### claude-otel wrapper: Claude Code telemetry for the agent team (sc-400, 2)
- `bin/claude-otel` sets the env from spec §5.2 (cumulative temporality, 10 s interval, include version/entrypoint/repository, tool details, content capture on, resource attributes with `app.layer=build`) and execs `claude` with the arguments passed through.
- With Alloy down it prints a warning and still starts.
- A session with two or more subagents shows cost by `agent.name` in Mimir and a nested subagent tree in Tempo.

### Alloy redaction for both layers (sc-401, 2)
- Alloy transform/redaction processors hash the known secret keys and regex-mask bearer tokens, JWTs, `sk-*`/`AIza*` keys and Postgres DSNs in string attributes and log bodies.
- Seeded secrets from both the build layer and the runtime layer arrive masked in Loki and Tempo (a repeatable test script).
- Metric datapoints drop `session.id`, `prompt.id`, `user.account_uuid`, `user.email`, `client_request_id`.

Order: 398 first (everything depends on it), then 401, 400, 399.

## File footprint (stay inside it)
- `observability/**` (new: Alloy, Loki, Tempo, Mimir, Grafana config, provisioning, test scripts, a short README)
- `docker-compose.yml` (the only shared-looking file; it is yours alone this sprint)
- `bin/claude-otel` (new)
- `specs/053-telemetry-stack/**`
- Nothing under `backend/`, `wcl_agent/`, `frontend/`, `.env.example`, `pyproject.toml`, `uv.lock` (stream B owns `.env.example` and the Python deps). Need something else: ask on the board with key `owner:<path>`.

## Contracts with stream B (also on the board, keys `contract:*`)
- **env:** the backend exports telemetry iff `OTEL_EXPORTER_OTLP_ENDPOINT` is set. In `docker-compose.yml` give the `backend` service: `OTEL_EXPORTER_OTLP_ENDPOINT: http://alloy:4318`, `OTEL_EXPORTER_OTLP_PROTOCOL: http/protobuf`, `WCL_ENVIRONMENT: dev`, `WCL_GIT_SHA: ${WCL_GIT_SHA:-unknown}`. The backend must still start when Alloy is down (B's job; don't add a `depends_on` that blocks the backend on Alloy health).
- **content stream:** Alloy routes to the 7-day content stream (a bounded Loki label, e.g. `content="true"`, with its own `retention_stream`) every log record that (a) carries the attribute `app.content="true"` (the backend sets it on any log carrying prompt/response/tool content) or (b) is a known content event: Claude Code's prompt/response/tool-content events and GenAI `gen_ai.*` message events. Name the exact event names you route in your spec and on the board.
- **ports:** Alloy OTLP gRPC `127.0.0.1:4317`, HTTP `127.0.0.1:4318`; Grafana `127.0.0.1:3000`. Make host ports overridable by env vars (`${ALLOY_OTLP_HTTP_PORT:-4318}` style) so a second stack never collides.

## Constraints and decisions already made
- Pin every image to an exact version. `otelcol.storage.file` is public preview: Alloy runs with `--stability.level=public-preview`. Verify the arguments against the pinned version's docs, don't assume.
- Bound the file-backed queue (size) so plain `docker compose up` without the profile (Alloy only, backends absent) can't fill the disk. Say what happens when it's full.
- Index labels: only the small allowlist of spec §9.2. Metric label hygiene per spec §4.2 step 4. Claude Code delta → set cumulative in the wrapper (spec §4.2 step 5).
- No tail sampling, no spanmetrics/servicegraph, no dashboards this sprint (sprint 2).
- Grafana holds no data: provisioning only, anonymous or admin login local-only.
- `bin/claude-otel`: content capture on (owner decision 7), `OTEL_LOG_TOOL_DETAILS=1`. Reachability check to Alloy before exec: warn, never block. Bash, `set -euo pipefail`, args passed through with `exec claude "$@"`.

## Docker (explicit grant for this stream; overrides the developer file's "no docker compose")
- Always `docker compose -p wcl-dev-a --profile observability ...` from your worktree, and only bring up the observability services (not db, redis, backend, frontend). Use non-default host ports via the env overrides if anything is bound.
- Tear down with `docker compose -p wcl-dev-a --profile observability down -v` after each test run and before hand-off. Never touch another compose project. About 10 GB RAM is free; keep `mem_limit`s modest.
- The persistence test (stop backends, send, restart, see data) and the redaction test must be scripts under `observability/` that team-lead can re-run on the merged tip.

## Tests and proof
- The Python suite must stay green: `check.py run --as ansel` on your committed tree (you change no Python, so it should be a formality; the receipt still matters).
- Your scripts prove 398 (persistence, retention config present), 401 (seeded secrets masked in Loki and Tempo for both `app.layer` values; mutation: disable a rule and the script fails) and 399 (datasource provisioning loads; correlation config present).
- Live checks (team-lead runs them on the merged tip; post each as a board `question`, key `live-check:053`, with exact steps): the real Claude Code session with two or more subagents through `bin/claude-otel` (sc-400 AC 3), and the clicks in Grafana (sc-399).

## Hand-off
Stories to Under Review, a board `handoff`, and your final result: branch, commits, files, the `check.py` RESULT and RECEIPT lines, your script results, risks, and an AC-by-AC mapping.
