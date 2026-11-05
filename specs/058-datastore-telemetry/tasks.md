# Tasks: Data-store telemetry (058)

**Input**: plan.md, spec.md, research.md, data-model.md, contracts/ (this directory)
**Tests**: required by the brief (stack scripts on seeded data, pytest for code and files).
Story labels: US1 = sc-417, US2 = sc-418, US3 = sc-419, US4 = sc-420, US5 = sc-424.

## Phase 1: Setup

- [X] T001 Benchmark the commenter (done before planning) in specs/058-datastore-telemetry/bench_commenter.py

## Phase 2: Foundational

- [X] T002 db/redis host ports overridable (`DB_PORT`, `REDIS_PORT`), env_file optional, db `command:` (pg_stat_statements, logging) in docker-compose.yml
- [X] T003 docker-proxy service and `docker-api` network; alloy environment (`WCL_PG_MONITOR_DSN`, `WCL_COMPOSE_PROJECT`), `observability/postgres` mount, network in docker-compose.yml
- [X] T004 Migration 0022 (extension + monitoring role from env) in backend/migrations/versions/0022_pg_stat_statements.py
- [X] T005 Variables without working values in .env.example
- [X] T006 Stack test skeleton (db + redis + alloy + backends on 25xxx, schema via alembic as owner, monitor password per run) in observability/test/datastores.sh and observability/test/datastores_check.py

## Phase 3: US1 Postgres exporter (sc-417)

- [X] T007 [US1] Custom queries (vector index size, embedding table rows) in observability/postgres/queries.yaml
- [X] T008 [US1] Section header, remote_write, postgres exporter + scrape + relabel allowlist in observability/alloy/config.alloy
- [X] T009 [US1] pg:* aliases in observability/mimir/rules/anonymous/datastores.yaml
- [X] T010 [US1] Seed (HNSW rows, slow statement) and assert top statement, index size = pg_relation_size, rows, monitor role (pg_monitor, not owner/superuser), no secret in labels/Alloy logs in datastores_check.py
- [X] T011 [US1] Migration test (up creates extension + role only with password; down removes) in backend/tests/test_telemetry_datastores.py

## Phase 4: US2 Redis exporter (sc-418)

- [X] T012 [US2] Redis exporter + scrape in observability/alloy/config.alloy; redis:* aliases in datastores.yaml
- [X] T013 [US2] Assert hit ratio = 7/10 from seeded hits/misses, no key-name label in datastores_check.py

## Phase 5: US3 sqlcommenter + slow-query log (sc-419)

- [X] T014 [US3] GitNexus impact on `instrument`, then the commenter flag in backend/app/telemetry/setup.py
- [X] T015 [US3] Tests: traceparent of the exported span appended with telemetry on; byte-identical SQL with telemetry off in backend/tests/test_telemetry_datastores.py
- [X] T016 [US3] docker discovery + loki.source.docker + loki.process (multiline, prefix) + otelcol.receiver.loki + transform "postgres" (resource, trace id, masks) in observability/alloy/config.alloy
- [X] T017 [US3] Assert slow line in Loki with trace id, derived field resolves to the trace, seeded secret string and numeric id masked, no parameters, lock wait + autovacuum lines present in datastores_check.py
- [X] T018 [US3] (not needed: the existing trace_id field resolves on postgres records, datastores.sh) Loki derivedFields only if T017 shows the existing field doesn't resolve, in observability/grafana/provisioning/datasources/datasources.yaml

## Phase 6: US4 cAdvisor, self-metrics, D9–D11 (sc-420)

- [X] T019 [US4] cadvisor service (after docker-proxy) in docker-compose.yml
- [X] T020 [US4] Scrapes: cadvisor, prometheus.exporter.self, loki/tempo/mimir /metrics, allowlists in observability/alloy/config.alloy; infra:*/meta:* aliases in datastores.yaml
- [X] T021 [P] [US4] D9 observability/grafana/dashboards/infra/postgres.json
- [X] T022 [P] [US4] D10 observability/grafana/dashboards/infra/redis.json
- [X] T023 [P] [US4] D11 observability/grafana/dashboards/infra/infra.json
- [X] T024 [US4] Dashboard tests (JSON, uids, aliases only, rate vs increase, window = step for bars/totals, units) in backend/tests/test_telemetry_datastores.py
- [X] T025 [US4] Stack: dashboards provisioned, every query valid, active series counted and under budget in datastores_check.py

## Phase 7: US5 alerts (sc-424)

- [X] T026 [US5] Alert rules in observability/grafana/provisioning/alerting/rules.yaml; threshold alias in datastores.yaml
- [X] T027 [US5] File test (uids, datasource, aliases) in backend/tests/test_telemetry_datastores.py
- [X] T028 [US5] Synthetic triggers: Firing then Normal for each rule in observability/test/alerts.sh

## Phase 8: Polish

- [X] T029 README section `## Data stores, infra and alerts (058)` in observability/README.md
- [X] T030 check.py run (SQLite) + --pg receipt; detect-changes; ownership check; live-check questions on the board

## Phase 9: Security rework (qa-security, one round)

- [X] T031 SEC-001 detail masks + pytest mask test + stack seeds in observability/alloy/config.alloy, backend/tests/test_telemetry_datastores.py, observability/test/datastores_check.py
- [X] T032 SEC-002/005 Postgres log file on the pglog volume, docker-proxy removed, in docker-compose.yml and observability/alloy/config.alloy
- [X] T033 SEC-003 cAdvisor hardened and residual risk documented in docker-compose.yml, observability/README.md
- [X] T034 SEC-004 tracestate/baggage out of the SQL comment in backend/app/telemetry/setup.py (+ test)
- [X] T035 SEC-007 0022 password rule and monitor-only existing role in backend/migrations/versions/0022_pg_stat_statements.py (+ tests)

## Dependencies

Phase 2 before all stories. US1 → US2 → US3 → US4 → US5 (shared config.alloy section and datastores.yaml;
the brief's order). Dashboards T021–T023 are parallel once the aliases exist.
