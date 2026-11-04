# Implementation Plan: Backend telemetry (traces, logs, content policy)

**Branch**: `054-backend-telemetry` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/054-backend-telemetry/spec.md`

## Summary

A new package `backend/app/telemetry/` sets up OpenTelemetry for the API process when (and only
when) `OTEL_EXPORTER_OTLP_ENDPOINT` is set: one resource, OTLP http/protobuf exporters for
traces, logs and metrics, global FastAPI / SQLAlchemy / Redis / httpx instrumentation, the ADK
content policy for the environment, and an exporter-side redaction wrapper that masks secrets
always and strips content outside dev. `main.py` calls the bootstrap before FastAPI and ADK are
imported and adds the OTLP log handler (which carries `RedactionFilter` itself). Each websocket
chat turn gets its own root span; `generation.py` gets one GenAI client span per one-shot call.

## Technical Context

**Language/Version**: Python 3.14
**Primary Dependencies**: opentelemetry-sdk/api 1.42.1 (ADK pin), opentelemetry-exporter-otlp-proto-http 1.42.1, opentelemetry-instrumentation-{fastapi,sqlalchemy,redis,httpx} 0.63b1. No grpcio, no google-genai instrumentation.
**Storage**: none (no migration)
**Testing**: pytest with the SDK's in-memory span/log exporters and metric reader; one subprocess test for the real startup order
**Target Platform**: Linux container (compose) and local uvicorn
**Project Type**: web service (FastAPI backend)
**Performance Goals**: no export work on the event loop beyond the SDK's span bookkeeping; batching, bounded queues
**Constraints**: off unless configured; content only in dev; never block on the collector
**Scale/Scope**: ~5 new modules, 3 small hunks in existing files

## Constitution Check

| Principle | Status |
|---|---|
| I Reuse | Redaction keys reuse `auth.redaction.is_sensitive_key` / `RedactionFilter`; ADK's own spans are used, not re-created; standard OTel instrumentors, no hand-rolled ones. |
| II Step-wise | Order 402 → 406 → 405 → 403 → 404, each with its tests green before the next. |
| III Simplicity | Global instrumentors patched in the bootstrap (one call in `main.py`); no custom metrics this sprint; one span helper for chat turns. |
| IV Typed | `TelemetryConfig` frozen dataclass; exporter wrappers typed against SDK interfaces. |
| V Async | Exporters run in SDK background threads; nothing awaits the collector. |
| VI GitNexus | impact run before each edit of `generation.py`, `main.py`, `ws.py`. |
| VII shadcn | n/a (no UI). |
| VIII Backlog | Shortcut stories moved by the developer; follow-ups posted as `backlog:` notices. |

Gate: PASS.

## Project Structure

```text
backend/app/telemetry/
├── __init__.py      # configure_telemetry(), otlp_log_handler(), chat_turn_span()
├── config.py        # TelemetryConfig from the env (.env honoured), version lookup
├── policy.py        # ADK content env per environment; content attribute / event names
├── redaction.py     # scrub rules + RedactingSpanExporter / RedactingLogExporter
└── setup.py         # resource, providers, exporters, instrumentors
backend/app/main.py           # +bootstrap call (before fastapi/ADK imports), +OTLP log handler
backend/app/api/ws.py         # +chat_turn_span around each turn (grant pending: owner:ws.py)
wcl_agent/llm/generation.py   # GenAI span around _with_retry
backend/tests/test_telemetry_*.py
```

**Structure Decision**: a backend package (the API process owns its telemetry); `wcl_agent`
only uses the OpenTelemetry API (no-op without a provider), never the backend package.

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|---|---|---|
| Per-turn root span in `ws.py` | Chat runs over one websocket per session; ASGI tracing would make one span per connection | Leaving the websocket traced puts every turn of a session in one hours-long trace |
| Exporter wrappers instead of span processors | Redaction off the event loop; logs need dropping in lockdown | A processor's `on_end` runs on the loop and cannot mutate a finished span |
