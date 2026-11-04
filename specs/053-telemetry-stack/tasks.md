# Tasks: Telemetry stack, claude-otel wrapper, Alloy redaction

**Input**: spec.md, plan.md, research.md in this directory.

## Phase 1: Setup
- [X] T001 Create `observability/` layout and `observability/test/lib.sh` (compose wrapper `-p wcl-dev-a`, OTLP JSON senders, pollers)

## Phase 2: Stack and persistence (US1, sc-398)
- [X] T002 [US1] `observability/loki/loki.yaml`: OTLP label allowlist, 30d retention, 7d `{content="true"}` stream
- [X] T003 [P] [US1] `observability/tempo/tempo.yaml`: monolithic, local storage, 7d retention, OTLP gRPC/HTTP in
- [X] T004 [P] [US1] `observability/mimir/mimir.yaml`: monolithic, filesystem, 13-month retention, OTLP resource promotion, exemplars, native histograms
- [X] T005 [US1] `observability/alloy/config.alloy`: receiver, memory limiter, stamping, batch, three exporters with persistent bounded queues
- [X] T006 [US1] `docker-compose.yml`: alloy (always), loki/tempo/mimir/grafana (profile), volumes, mem_limits, backend OTEL env
- [X] T007 [US1] `observability/test/persistence.sh`: backends stopped → send span/log/metric → start → find all three; retention config asserted

## Phase 3: Redaction (US2, sc-401)
- [X] T008 [US2] Redaction + metric label hygiene + content routing in `config.alloy`
- [X] T009 [US2] `observability/test/redaction.sh`: seeded secrets for `app.layer` build and runtime in logs, spans, span events; banned metric labels absent; content routing checked
- [X] T010 [US2] Mutation proof: disable each rule, script fails

## Phase 4: Wrapper (US3, sc-400)
- [X] T011 [US3] `bin/claude-otel`: §5.2 env, reachability warning, `exec claude "$@"`
- [X] T012 [US3] `observability/test/claude-otel.sh`: stub claude; env, args, warning with Alloy down

## Phase 5: Correlations (US4, sc-399)
- [X] T013 [US4] `observability/grafana/provisioning/datasources/datasources.yaml`
- [X] T014 [US4] `observability/test/provisioning.sh`: datasources and correlation settings via Grafana API

## Phase 6: Polish
- [X] T015 `observability/README.md` (start, ports, retention, queue, tests, live checks)
- [X] T016 Live-check questions on the board (`live-check:053`)
- [ ] T017 check.py receipt, change detection, hand-off
