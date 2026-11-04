# Tasks: Runtime metrics (056)

## Phase 1: Setup

- [X] T001 Pin `google-adk==2.10.0` and `opentelemetry-exporter-otlp-proto-http==1.42.1` in pyproject.toml; `uv lock` (uv.lock changes only in the specifier lines)

## Phase 2: Foundational

- [X] T002 Session meter provider fixture (production `setup.meter_provider` View, delta in-memory reader, drained per test) in backend/tests/test_telemetry_metrics.py

## Phase 3: US1 ADK core metrics (sc-411)

- [X] T003 [US1] Test: a scripted ADK turn (test_telemetry_support.scripted_agent) exports gen_ai.client.token.usage (model + token type), gen_ai.invoke_agent.duration, inference_calls, tool_calls by agent, every attribute allowlisted and no id, in backend/tests/test_telemetry_metrics.py
- [X] T004 [US1] Test: the version pins match the installed versions and the semconv opt-in is part of the content policy, in backend/tests/test_telemetry_metrics.py

## Phase 4: US2 app metrics (sc-412)

- [X] T005 [US2] Allowlist app.cache.name, app.cache.result, app.rag.index, app.rag.strategy in backend/app/telemetry/setup.py
- [X] T006 [US2] `app.cache.requests` counter from `_record` in wcl_agent/cache/cache.py
- [X] T007 [US2] KB and TTFT instruments + record helpers in backend/app/telemetry/metrics.py
- [X] T008 [US2] Record retrieval metrics at the end of `search()` in backend/app/kb/search.py
- [X] T009 [US2] Record TTFT at the first model text token in backend/app/agent_runner.py
- [X] T010 [US2] Tests for T006–T009 plus a forbidden attribute dropped, in backend/tests/test_telemetry_metrics.py; mutate.py on the allowlist and each record site

## Phase 5: US3 dashboards (sc-413)

- [X] T011 [US3] observability/mimir/rules/anonymous/runtime.yaml (contract aliases + D7/D8 helpers); mimirtool lint/check
- [X] T012 [P] [US3] D7: evolve observability/grafana/dashboards/runtime/app-api-llm.json (same uid) onto aliases
- [X] T013 [P] [US3] D6: observability/grafana/dashboards/runtime/api-red.json over app:http_* aliases
- [X] T014 [P] [US3] D8: observability/grafana/dashboards/runtime/rag.json over rag:* and cache:* aliases
- [X] T015 [US3] Test: dashboards parse and every Mimir panel expr references only recording-rule aliases (runtime.yaml or the 055 contract names), in backend/tests/test_telemetry_metrics_dashboards.py

## Phase 6: Polish

- [ ] T016 check.py full run, detect-changes, live-check questions, hand-off

Dependencies: T001 → T002 → US1 → US2 → US3 (T011 before T012–T015). MVP = US1.
