# Tasks: 060 frontend, build vs runtime, redaction e2e

## Phase 1: sc-416 error boundaries, events, D5 (US1)

- [X] T001 [US1] Tests first: frontend/src/telemetry/ErrorBoundary.test.tsx (fallback hides the message, one report with route and boundary, siblings stay, retry)
- [X] T002 [US1] context.ts reportError / pushTelemetryEvent / route; ErrorBoundary.tsx
- [X] T003 [US1] Tests first: frontend/src/api/wsClient.test.tsx ("chat events") and MessageList.test.tsx cases (once each, abort only mid-turn close, other socket safe)
- [X] T004 [US1] chatEvents.ts, wsClient.ts wiring, LiveMessage first-token effect
- [X] T005 [US1] faro.ts view = route template (+ test in faro.test.tsx)
- [X] T006 [US1] main.tsx shell boundary, App.tsx panel boundaries (the route tree's root errorElement came with the QA fix round, T020)
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
- [X] T019 check.py run on committed tree, detect-changes, live-check questions, hand-off

## Phase 5: QA fix round (sweep 2026-11-05 and live pass)

- [X] T020 [US1] routes.tsx: root `errorElement` (RouteErrorFallback) so route render errors show the plain fallback and report with `boundary=shell`; `resetKey` (conversation id) on the panel boundaries; tests in routes.test.tsx, ErrorBoundary.test.tsx, App.test.tsx
- [X] T021 [US1] D5 "Client TTFT p95" grouped with `by ()`; frontend.sh sends three TTFT events and expects one tile and one series
- [X] T022 [US3] commits.py: `merge:<feature>` keys, SHA from the text when there are no refs (tested on this sprint's board); cross.yaml: running version prefers a known version, commit seat tie-break; build-runtime.sh adds a stray `unknown` Resource
- [X] T023 docs: T003/T019 above, the Postgres path decision (#67) in the spec Assumptions, README and `redaction_e2e.py`
