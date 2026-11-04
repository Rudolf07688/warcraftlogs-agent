# Sprint 2026-11-04 plan: Telemetry 1 (epic 395), 23 points

Goal: see the agent team and one chat request end to end, with telemetry kept across restarts and
secrets masked. Plan and decisions: `specs/telemetry_spec.md` §14 (stories win where they differ).
Iteration "Sprint 2026-11-04" (425). Branch `sprint-2026-11-04`, base `38606fd`.

## Feature 053 `053-telemetry-stack` (stream A, 11 pts), tier M, Ansel (dev-1), opus medium
Worktree `/home/rudolf/dev/wcl-worktrees/dev-a`.
- Observability stack with persistence and a durable export queue (sc-398, 5)
  - Plain `docker compose up` adds only Alloy (pinned image, `restart: unless-stopped`, ports on 127.0.0.1); the app runs unchanged.
  - The `observability` profile adds Loki, Tempo, Mimir (monolithic) and Grafana on named volumes with a `mem_limit` each. No MinIO, no Pyroscope.
  - Retention: content stream 7 days, logs 30 days, traces 7 days in dev, metrics 13 months.
  - Alloy exporters use `sending_queue` with `otelcol.storage.file` (`--stability.level=public-preview`).
  - A span, a log and a metric sent while the backends are stopped show in Grafana after they restart.
- Grafana datasource correlations (sc-399, 2), after 398. Drop first.
  - Datasources provisioned as code; click trace to logs, log line (`trace_id` structured metadata) to trace, exemplar to trace.
- claude-otel wrapper (sc-400, 2), after 398
  - `bin/claude-otel` sets the §5.2 env (cumulative, 10 s, version/entrypoint/repository, tool details, content on, `app.layer=build`) and execs `claude` with args passed through.
  - With Alloy down it warns and still starts.
  - A session with 2+ subagents shows cost by `agent.name` in Mimir and a nested subagent tree in Tempo (live check).
- Alloy redaction for both layers (sc-401, 2), after 398
  - Transform/redaction processors hash known secret keys and regex-mask bearer tokens, JWTs, `sk-*`/`AIza*` keys, Postgres DSNs in string attributes and log bodies.
  - Seeded secrets from build and runtime layers arrive masked in Loki and Tempo (repeatable test script).
  - Metric datapoints drop `session.id`, `prompt.id`, `user.account_uuid`, `user.email`, `client_request_id`.

## Feature 054 `054-backend-telemetry` (stream B, 12 pts), tier M, Nils (dev-3), opus high, security-core
Worktree `/home/rudolf/dev/wcl-worktrees/dev-b`.
- Backend telemetry bootstrap, off unless configured (sc-402, 3)
  - `backend/app/telemetry/` sets global tracer/meter/logger providers before ADK is imported; resource `service.name=api`, `service.version`/`vcs.ref.head.revision`=git sha, `app.layer=runtime`, `deployment.environment.name`.
  - OTLP http/protobuf (no grpcio); metrics cumulative, exponential histograms.
  - No OTLP endpoint: no providers or instrumentors; test suite unchanged.
  - OTel within ADK's pin (sdk<=1.42.1, contrib 0.63b1).
- One chat turn is one trace (sc-403, 3), after 402
  - FastAPI (route templates; /health and readiness excluded), SQLAlchemy on the single engine, Redis, httpx instrumented.
  - One chat turn = one trace HTTP → invoke_agent → generate_content/execute_tool → WCL httpx → SQL → Redis (in-memory exporter test).
  - FetchWriter/KbIndexer own traces documented. No google-genai instrumentation.
- GenAI spans for one-shot model calls (sc-404, 2), after 402. Second to drop.
  - One manual GenAI span in `wcl_agent/llm/generation.py` with gen_ai.* (operation, request model, usage tokens, finish reason).
  - A chat-title call shows model and tokens for Claude (vertex, anthropic) and Gemini.
- Backend logs to Loki with trace ids, through the redaction filter (sc-405, 2), after 402
  - OTLP log handler exports with trace_id/span_id; stdout stays the fallback.
  - The handler gets `RedactionFilter` explicitly.
  - A log line opens its trace; a test shows a token in `extra` is exported redacted.
- Content-capture policy per environment (sc-406, 2), after 402
  - Dev: prompts, responses, tool I/O on ADK spans/events and in the 7-day content stream.
  - ci/prod: the three ADK lockdown settings apply; tests prove no content exported; explicit default.
  - App-side redaction span processor masks secrets even with content on (test).

## Order and risks
Streams are independent (disjoint files); both start now. Contracts on the board (`contract:*`).
Risks: Alloy public-preview storage component; ADK otel pin; global instrumentors vs the suite;
Python 3.14 wheels; RAM with the stack up. Drop order: sc-399, then sc-404.
