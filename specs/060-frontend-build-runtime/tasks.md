# Tasks: 060 frontend, build vs runtime, redaction e2e

## Phase 1: sc-416 error boundaries, events, D5 (US1)

- [X] T001 [US1] Tests first: frontend/src/telemetry/ErrorBoundary.test.tsx (fallback hides the message, one report with route and boundary, siblings stay, retry)
- [X] T002 [US1] context.ts reportError / pushTelemetryEvent / route; ErrorBoundary.tsx
- [X] T003 [US1] Tests first: frontend/src/telemetry/chatEvents.test.tsx and wsClient.test.tsx cases (once each, abort only mid-turn close, other socket safe)
- [X] T004 [US1] chatEvents.ts, wsClient.ts wiring, LiveMessage first-token effect
- [X] T005 [US1] faro.ts view = route template (+ test in faro.test.tsx)
- [X] T006 [US1] main.tsx shell boundary, App.tsx panel boundaries
- [X] T007 [US1] dashboards/runtime/frontend.json (D5) + granted line in test_telemetry_metrics_dashboards.py + backend/tests/test_telemetry_cross_dashboards.py D5 checks
- [X] T008 [US1] observability/test/frontend.sh: synthetic component error + vitals + events → D5 queries return them with the route
- [X] T009 [US1] npm run build, npm test, commit

## Phase 2: sc-423 redaction e2e (US2)

- [X] T010 [US2] observability/test/redaction_e2e.py (SHAPES, PATHS, backend subprocess, Faro, queries)
- [X] T011 [US2] observability/test/redaction-e2e.sh (fresh stack, green run, mutated copies red)
- [X] T012 [US2] run green + red, commit

## Phase 3: sc-422 D12 (US3)

- [X] T013 [US3] Tests first: commits.py attribution on a fixture board (test_telemetry_cross_dashboards.py)
- [X] T014 [US3] observability/build-runtime/commits.py
- [X] T015 [US3] observability/mimir/rules/anonymous/cross.yaml + dashboards/cross/build-runtime.json + static tests
- [X] T016 [US3] observability/test/build-runtime.sh synthetic regression, run green
- [X] T017 [US3] commit

## Phase 4: polish

- [X] T018 README section "## Frontend, build vs runtime and redaction e2e (060)"
- [ ] T019 check.py run on committed tree, detect-changes, live-check questions, hand-off
