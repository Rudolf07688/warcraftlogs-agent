# Tasks: Backend telemetry (054)

**Input**: `specs/054-backend-telemetry/` (spec, plan, research, data-model, contracts)
**Tests**: required (brief: every AC proven by a test; security tests mutation-checked)

## Phase 1: Setup

- [X] T001 Add OTel deps within the ADK pin (exporter-otlp-proto-http 1.42.1, instrumentation-fastapi/sqlalchemy/redis/httpx 0.63b1) in pyproject.toml and uv.lock
- [X] T002 Document the telemetry env vars in .env.example

## Phase 2: Foundational

- [X] T003 TelemetryConfig (endpoint, environment, content_allowed, version) reading the env and `.env` without importing backend.app.config, in backend/app/telemetry/config.py

## Phase 3: US1 bootstrap, off unless configured (sc-402)

- [X] T004 [US1] Resource, OTLP http exporters, batch processors, cumulative + exponential-histogram metric reader, global providers in backend/app/telemetry/setup.py; `configure_telemetry()` in backend/app/telemetry/__init__.py (no-op without endpoint, idempotent, returns the active config)
- [X] T005 [US1] Call the bootstrap in backend/app/main.py before the fastapi and ADK imports
- [X] T006 [US1] Tests in backend/tests/test_telemetry_bootstrap.py: off → no providers/instrumentors; subprocess import of main with a dead endpoint → providers set before ADK import, resource attrs, FastAPI class and engine instrumented, import does not hang; exporter protocol http; metric temporality/aggregation

## Phase 4: US2 content policy (sc-406)

- [X] T007 [US2] ADK env per environment (lockdown forced, dev setdefault, semconv opt-in) in backend/app/telemetry/policy.py, applied by the bootstrap
- [X] T008 [US2] Scrub rules + RedactingSpanExporter / RedactingLogExporter (mask secrets always; strip content attrs and drop gen_ai.* events in lockdown; app.content="true" on gen_ai.* events in dev) in backend/app/telemetry/redaction.py, wired in setup.py
- [X] T009 [US2] Tests in backend/tests/test_telemetry_content.py: real ADK turn (scripted Claude, in-memory exporters) under dev has prompt/answer/tool I/O and content mark; under ci/prod/unset/garbage none appears anywhere; secrets masked with content on; token counts survive; mutation-check policy flip and redaction removal

## Phase 5: US3 logs (sc-405)

- [X] T010 [US3] `otlp_log_handler()` (RedactionFilter attached, opentelemetry.* loggers dropped) in backend/app/telemetry/__init__.py; wire it next to `_install_log_redaction` in backend/app/main.py
- [X] T011 [US3] Tests in backend/tests/test_telemetry_logs.py: trace/span id on exported record, token in extra exported redacted (mutation-check), exporter self-logs not exported, stdout handler kept

## Phase 6: US4 one turn = one trace (sc-403)

- [X] T012 [US4] Instrumentors (FastAPI excluded urls, SQLAlchemy global, Redis, httpx) in backend/app/telemetry/setup.py; `chat_turn_span()` in backend/app/telemetry/__init__.py
- [X] T013 [US4] Wrap each turn in `chat_turn_span` in backend/app/api/ws.py (granted #28, #32)
- [X] T014 [US4] Tests in backend/tests/test_telemetry_trace.py: one turn through `_start_turn` with scripted Claude, a WCL tool over a mock transport, fake Redis and the SQLite DB → one trace id, expected parent chain; HTTP route span uses the template, /health untraced; ws.chat opens a fresh root per turn

## Phase 7: US5 one-shot GenAI spans (sc-404)

- [X] T015 [US5] GenAI CLIENT span around `_with_retry` in wcl_agent/llm/generation.py
- [X] T016 [US5] Tests in backend/tests/test_telemetry_genai.py: chat title on Claude (anthropic + vertex) and Gemini → model, tokens, finish reason; failure → error status

## Phase 8: Polish

- [X] T017 Full suite via check.py, GitNexus detect-changes, board contract note (event names), live-check question, hand-off

## Phase 9: QA security rework (board review:054)

- [X] T018 SEC-001: outside dev drop exception.message/stacktrace and status descriptions, cut SQL parameters from any text, in backend/app/telemetry/policy.py and redaction.py; test backend/tests/test_telemetry_errors.py
- [X] T019 SEC-002/008: linear secret pattern, 16 KiB value cap, span limits and log value limit in redaction.py and setup.py; timing tests in test_telemetry_redaction.py
- [X] T020 SEC-003: metrics View with an attribute allowlist in setup.py; Host-header test in test_telemetry_bootstrap.py
- [X] T021 SEC-005: conftest strips OTEL_* (granted hunk), exporter timeout 2 s; exit-time test in test_telemetry_bootstrap.py

## Dependencies

T001 → T003 → US1 → US2 → US3 → US4 → US5 → T017. US5 is independent of US2–US4 except T004.
