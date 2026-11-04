# Research: 054 backend telemetry

## R1 Startup order
- Decision: `configure_telemetry()` is called in `main.py` before `from fastapi import FastAPI`
  and before any ADK import. The telemetry package imports only stdlib, dotenv and OpenTelemetry.
- Rationale: `backend.app.config` imports ADK and fastapi (checked: `import backend.app.config`
  loads `google.adk`), so the bootstrap reads the environment itself and loads `.env` like
  config.py does. Global FastAPI instrumentation swaps `fastapi.FastAPI`, so it must run before
  `main.py` binds the name; SQLAlchemy's global instrumentation wraps `create_async_engine`
  before `db/session.py` binds it.
- Alternatives: `opentelemetry-instrument` (spec §6.1 rejects it); instrumenting the app and
  engine objects after creation (more `main.py` hunks than the brief allows).

## R2 Exporters
- Decision: OTLP http/protobuf for traces, logs and metrics, endpoint and headers from the
  standard `OTEL_EXPORTER_OTLP_*` env; BatchSpanProcessor / BatchLogRecordProcessor (bounded
  queues, drop on overflow); PeriodicExportingMetricReader with cumulative temporality and
  `ExponentialBucketHistogramAggregation` for histograms.
- Rationale: decision 12 (no grpcio on 3.14); batch processors never block the caller.

## R3 Content policy (ADK 2.10)
- ADK reads `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS` (default **on**),
  `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` (default NO_CONTENT) and
  `ADK_TELEMETRY_IGNORE_RUN_CONFIG` when a `TelemetryConfig` is built, from `os.environ`.
- Decision: lockdown forces `false` / `NO_CONTENT` / `1`; dev sets (setdefault) `true` /
  `SPAN_AND_EVENT`; both set `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` by
  default (spec §6.3). ADK's content log event in that mode: `gen_ai.client.inference.operation.details`.
- App-side enforcement in lockdown (clarify Q2): strip content attribute keys and drop
  `gen_ai.*` log events in the exporter wrappers.

## R4 Redaction
- Decision: exporter wrappers copy each span / log record with: sensitive-key attributes
  (`auth.redaction.is_sensitive_key`) masked when the value is a string; every string value
  scrubbed for bearer tokens, credentials in URLs, sensitive query parameters, JSON
  `"<sensitive key>": "..."` pairs, `sk-ant-…`, `AIza…` keys and JWTs. Events, links, status
  descriptions and log bodies get the same treatment.
- Rationale: numeric `gen_ai.usage.*_tokens` must survive the "token" key rule.

## R5 Chat turn traces
- Chat turns run over `/ws/chat`. Decision: exclude `/ws/chat` (and `/health`, `/api/health`)
  from ASGI tracing; `chat_turn_span()` opens a fresh root SERVER span per turn around
  `_start_turn` in `ws.py`. ADK's `invoke_agent` nests under it via contextvars.
- Queue-fed writers (FetchWriter, KbIndexer) run in their own tasks started at boot: their SQL
  spans start their own traces (accepted, §14.2).

## R6 Feedback loop
- The OTLP exporters log their own failures through `opentelemetry.*` loggers. The OTLP log
  handler drops records from those loggers so a dead collector cannot feed itself.

## R7 One-shot GenAI span
- Decision: `_with_retry` in `generation.py` opens one CLIENT span `"{operation} {model}"`
  (`chat`, `embeddings`) around the retry loop, with `gen_ai.operation.name`,
  `gen_ai.provider.name` (`anthropic`, `gcp.vertex_ai`, `gcp.gen_ai`), `gen_ai.request.model`,
  `gen_ai.response.model`, `gen_ai.usage.input_tokens`/`output_tokens`,
  `gen_ai.response.finish_reasons`; exceptions set `error.type` and an error status.
