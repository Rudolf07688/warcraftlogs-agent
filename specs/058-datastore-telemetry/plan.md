# Implementation Plan: Data-store telemetry (058)

**Branch**: `058-datastore-telemetry` | **Date**: 2026-11-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/058-datastore-telemetry/spec.md`; brief
`sprints/2026-11-05/briefs/058-datastore-telemetry.md`; board decisions `scope:058:*` (#30–#38).

## Summary

Postgres and Redis exporters, cAdvisor and the stack's self-metrics are scraped by Alloy and remote-
written to Mimir; Postgres logs slow statements, lock waits and autovacuum to stderr, Alloy reads them
through a GET-only Docker proxy, masks literals and feeds them into the existing redaction chain to
Loki; the backend's SQLAlchemy instrumentation appends `traceparent` so a slow line links to its
trace. Dashboards D9–D11 read new aliases in `datastores.yaml`; two Grafana-managed alert rules are
provisioned. Proof: one stack script per story group on seeded, real-shaped data, plus pytest for
the commenter, the migration and the dashboard/alert files.

## Technical Context

**Language/Version**: Python 3.14 (backend), Alloy config language, PromQL/LogQL, Bash test scripts
**Primary Dependencies**: Alloy v1.21.3 (`prometheus.exporter.postgres/redis/self`, `prometheus.scrape`,
`prometheus.remote_write`, `discovery.docker`, `loki.source.docker`, `otelcol.receiver.loki`),
cAdvisor 0.54.1, tecnativa/docker-socket-proxy v0.4.1, opentelemetry-instrumentation-sqlalchemy 0.63b1
(already installed: no manifest change)
**Storage**: Postgres 17 + pgvector (extension `pg_stat_statements`, migration `0022`), Mimir, Loki
**Testing**: pytest via `check.py` (SQLite + `--pg`); stack scripts `observability/test/datastores.sh`,
`observability/test/alerts.sh` on project `wcl-obs-ansel`, 25xxx ports
**Target Platform**: Linux Docker host (local dev); Docker Desktop lacks cAdvisor host access (documented)
**Project Type**: web service + telemetry stack
**Performance Goals**: commenter overhead measured (+0.53 ms/statement median, research R2)
**Constraints**: added series well under the 50k budget (target < 5k); no new volumes; owner's
`pgdata` unchanged apart from the extension and the role; off-path SQL byte-identical
**Scale/Scope**: one database, one Redis, ~10 containers

## Constitution Check

- **I Reuse**: reuses the redaction chain (memory_limiter → stamp → redact → log_window → classify),
  lib.sh helpers, rules_check-style seeding, the 0004 role pattern, the dashboard alias test pattern.
- **II Small steps**: one story at a time in brief order (417 → 418 → 419 → 420 → 424), each proved by
  its script section before the next.
- **III Simplicity**: built-in Alloy exporters; one remote_write; two new tiny services only where
  security demands (docker-proxy, cadvisor — research R1). No new Python modules.
- **IV Typed boundaries**: no new API surface; config files are validated by the stack tests.
- **V Async**: no backend runtime change besides an instrumentor flag.
- **VI GitNexus**: `impact` on `instrument` before the edit; detect-changes before each commit.
- **VII shadcn**: no UI. **VIII Shortcut**: stories In Progress → Under Review.

Gate: PASS. Complexity tracking: the two extra services (justified in research R1).

## Project Structure

### Documentation (this feature)

```text
specs/058-datastore-telemetry/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md, tasks.md, checkpoint.md
├── bench_commenter.py           # R2 micro-benchmark
└── contracts/aliases.md, contracts/alerts.md
```

### Source Code (repository root)

```text
docker-compose.yml                          # db command + ports, redis ports, alloy env/mounts/network,
                                            # new docker-proxy, cadvisor (after alloy)
observability/alloy/config.alloy            # appended section "Data stores and infra (feature 058)"
observability/postgres/queries.yaml         # exporter custom queries (vector index size, rows)
observability/mimir/rules/anonymous/datastores.yaml
observability/grafana/dashboards/infra/{postgres,redis,infra}.json
observability/grafana/provisioning/alerting/rules.yaml
observability/grafana/provisioning/datasources/datasources.yaml   # Loki derivedFields: + span link
observability/test/datastores.sh, datastores_check.py, alerts.sh
backend/app/telemetry/setup.py              # SQLAlchemyInstrumentor line only
backend/migrations/versions/0022_pg_stat_statements.py
backend/tests/test_telemetry_datastores.py
.env.example, observability/README.md (## Data stores, infra and alerts (058))
```

**Structure Decision**: existing layout; new files only in the brief's footprint.

## Design notes (per story)

1. **sc-417** db `command:` adds `shared_preload_libraries=pg_stat_statements`,
   `pg_stat_statements.track_utility=off`, `compute_query_id=on`. 0022 runs `CREATE EXTENSION IF NOT
   EXISTS pg_stat_statements` and the monitoring role (data-model). Alloy: `prometheus.exporter.postgres
   "db"` (default collectors + the six §7.2 ones, `stat_statements { include_query = false }`,
   `custom_queries_config_path`), DSN from `sys.env("WCL_PG_MONITOR_DSN")`.
2. **sc-418** `prometheus.exporter.redis "cache"` (`redis_addr = "redis:6379"`, no key checks).
3. **sc-419** setup.py: `SQLAlchemyInstrumentor().instrument(skip_dep_check=True, enable_commenter=True,
   commenter_options={"db_driver": False, "db_framework": False})`. db logs per research R4; Alloy
   docker discovery filtered on the compose project (env `WCL_COMPOSE_PROJECT`) and service `db`.
   Loki's existing `trace_id` derived field (structured metadata) covers the postgres record too; the
   test proves it resolves there, and datasources.yaml changes only if that proof fails.
4. **sc-420** cadvisor service; scrapes of loki/tempo/mimir `/metrics`, `prometheus.exporter.self`;
   series allowlists; D9–D11 on aliases.
5. **sc-424** Grafana alert provisioning file; spend threshold constant in `datastores.yaml`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| docker-proxy service | Alloy must read docker logs; it also parses browser input (Faro) | raw socket in Alloy = host root on an Alloy compromise; `:ro` doesn't restrict the API |
| cadvisor service | naming containers needs the containerd socket on this host | Alloy's built-in cAdvisor would put containerd.sock (root-equivalent) and privileged mode into the Faro-facing collector |
