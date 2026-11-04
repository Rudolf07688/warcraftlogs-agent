# Implementation Plan: Browser telemetry (057)

**Branch**: `057-browser-telemetry` | **Spec**: [spec.md](spec.md)

## Summary

Backend: one module (`backend/app/telemetry/browser.py`) validates browser-controlled trace
context and session id; `chat_turn_span(traceparent, faro_session_id)` parents the turn on it,
`ws.py` passes the two raw frame fields, a pure ASGI middleware tags REST server spans.
Frontend: `src/telemetry/` (Faro init, off without `VITE_FARO_URL`; a light `context.ts` the
socket and REST client use; user hash). Alloy: a `faro.receiver` section at the end of
`config.alloy` bridged into the existing redaction chain; compose port and frontend env.

## Technical context

- Python 3.14, FastAPI, OTel 1.4x (`TraceContextTextMapPropagator`); React 19 + Vite, Vitest.
- `@grafana/faro-react` and `@grafana/faro-web-tracing`, both pinned `2.13.0`.
- Alloy `grafana/alloy:v1.21.3`: `faro.receiver` arguments checked with `alloy validate` on that image.
- Constitution: I (reuse the OTel propagator, `chat_turn_span`), III (one module, no new framework), IV (typed
  boundaries: raw frame fields validated as `object`), V (middleware is pure ASGI, no blocking).

## Design decisions

See the spec's Clarifications and the board keys `scope:057:*`. Impact: `chat_turn_span` is
called by `ws.chat` only (and three telemetry tests); the new arguments are optional.
Guard tests (`guards.py`) concern the raw store, provider layer and WCL queries: none touch this.

## Files

Backend: `telemetry/__init__.py`, `telemetry/browser.py` (new), `api/ws.py`, `main.py`;
tests `test_telemetry_browser.py`. Frontend: `src/telemetry/{context,faro}.ts` (+ tests),
`api/wsClient.ts`, `api/restClient.ts`, `auth/AuthProvider.tsx`, `main.tsx`, `vite-env.d.ts`,
`package.json`/lock. Infra: `alloy/config.alloy` (end), `docker-compose.yml` (alloy port,
frontend env), `test/faro.sh`, README section.

## Risks

- Faro bundle size: loaded by dynamic import only when configured.
- `session_id` in Faro log lines is masked by the shared redaction rule (documented, spans keep it).
- A non-browser client ignores CORS: key and rate limit are the controls (tested).
