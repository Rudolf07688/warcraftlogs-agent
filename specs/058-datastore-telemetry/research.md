# Research: 058 data-store telemetry

## R1 Docker access and cAdvisor (probed 2026-11-05 on this host: Docker 29.6, cgroup v2, containerd image store)

- cAdvisor 0.52.1 (gcr.io) with the Docker API: every container fails ("failed to identify the
  read-write layer ID ... layerdb/mounts/<id>/mount-id: no such file"); only the root cgroup.
- cAdvisor 0.54.1 (ghcr.io) without the containerd socket: the Docker factory fails ("unable to create
  containerd client"); only the root cgroup.
- cAdvisor 0.54.1 with `/run/containerd/containerd.sock:ro`, `/sys:ro`, `/var/lib/docker:ro`, Docker
  API through the proxy, not privileged: names, images and the compose labels appear; CPU, memory,
  pressure and task metrics per container. No network metrics (they need the host's /proc per pid).
- **Decision**: separate `cadvisor` service (observability profile), Docker API via `docker-proxy`
  (GET-only, internal network `docker-api`), containerd.sock only in cadvisor. Alloy reads docker logs
  and discovery through the same proxy. **Rejected**: Alloy's built-in `prometheus.exporter.cadvisor`
  (docs ask for privileged mode plus `/`, `/var/run`, the socket read-write: all inside the collector
  that parses browser payloads); raw socket `:ro` (does not restrict the API).

## R2 sqlcommenter cost (specs/058-datastore-telemetry/bench_commenter.py)

3000 statements after a 200 warm-up, each in its own span, one connection, `pg.py` Postgres on loopback:

| variant | median | p95 |
|---|---|---|
| off (no instrumentation) | 485–490 µs | 646–659 µs |
| spans (054 today) | 545–568 µs | 731–776 µs |
| commenter, statement cache on | 1084–1087 µs | 1438–1503 µs |
| commenter, `prepared_statement_cache_size=0` | 1478–1482 µs | 1781–1818 µs |

Unique text per statement means one prepare per execution: +~0.53 ms per statement. A chat turn's
~30 statements: ~16 ms against seconds of model time. **Decision**: commenter on (telemetry only),
cache on, `db_driver`/`db_framework` off (shorter comment, no version strings).

## R3 Double EngineTracer (pre-existing, 054)

`create_async_engine` is wrapped and so is the `create_engine` it calls: two `EngineTracer`s per
engine. Per statement two spans start; the second overwrites `context._otel_span`, so the first is
never ended or exported; with the commenter the SQL carries two `traceparent` comments and only the
**last** is the exported span. **Decision**: the log parser takes the last traceparent; the root fix is
backlog (board `backlog:sqlalchemy-double-tracer`; setup.py beyond the instrumentor line is 059's).

## R4 Postgres log path

- `jsonlog` needs `logging_collector=on`, which writes files under pgdata instead of stderr: rejected.
  stderr with `log_line_prefix='%m [%p] q=%Q %e '` (timestamp, pid, query id, SQLSTATE).
- `log_min_duration_statement=250ms`, `log_lock_waits=on`, `log_autovacuum_min_duration=0`,
  `log_parameter_max_length=0` (bind values never in duration lines; on-error default is 0 already).
- Multi-line messages (SQLAlchemy SQL has newlines; autovacuum reports span lines): joined in
  `loki.process` with `stage.multiline` on the prefix.
- Masking (OTTL on the postgres records only, before the shared redaction): quoted strings
  (`'…'`, `E'…'`, `$$…$$`) → `'?'`; numeric literals not part of an identifier or `$n` → `?` in SQL-bearing
  records (duration statements, `STATEMENT:`, `QUERY:`); in every other record also double-quoted
  values and `=(…)` key details are masked, except allowlisted operational messages (autovacuum and
  autoanalyze reports, lock-wait/acquired lines, checkpoints, startup/shutdown), which carry only
  object names and counters.
- Trace id: last `traceparent='00-<32>-<16>-<2>'` in the record → `trace_id`/`span_id` (R3).

## R5 Metrics path

`prometheus.remote_write` to Mimir `/api/v1/push`: native exporter names, WAL on `alloy-data`
(survives backend absence up to the WAL's keepalive). The OTLP path would rename series and turn
job/instance into resource attributes. Series kept by name allowlist per scrape.

## R6 Alerts

Grafana provisioning `alerting/*.yaml` (apiVersion 1, groups → rules with `data` queries and a
threshold expression). State read at `/api/prometheus/grafana/api/v1/rules`. Exporter send failures
count only after retries end, so the synthetic trigger is a permanent refusal: a log record 2 h older
than its stream's newest gets Loki's 400.

## R7 Security rework (qa-security, qa-reports/2026-11-05/058-security.md)

- **SEC-001** row values: DETAIL/CONTEXT/HINT kept only in known shapes (key and row details, lock
  waits, deadlocks, parameters), otherwise `<detail withheld>`; `Failing row contains (...)` and
  `Key (...)=(...)` masked whole (greedy to the record's last `)`). Proved by pytest on the masks
  of config.alloy and by datastores.sh seeding NOT NULL, CHECK and a `)` inside a key value.
- **SEC-002/005** Docker proxy removed: Postgres writes its log with `logging_collector` into the
  `pglog` volume (the image's `/var/log/postgresql`, root:postgres 1775, is copied into it), Alloy
  tails it read-only. Alloy has no Docker access.
- **SEC-003** cAdvisor still needs containerd.sock (R1) and now the Docker socket (no proxy):
  both root-equivalent. Hardened (digest pin, `cap_drop: ALL`, `no-new-privileges`, read-only root,
  internal network, observability profile) and documented as residual risk. Probed: it still
  names containers with no capabilities and a read-only root.
- **SEC-004** `tracestate: False`, `baggage: False`. In 0.63b1 the commenter injects with a
  module-level `TraceContextTextMapPropagator`, so baggage never reaches the SQL (the option is a
  guard for a later version); tracestate did, and the test with a client tracestate bites.
- **SEC-007** 0022: password `[A-Za-z0-9]{16,}`, role name `fullmatch`, an existing role must be
  monitor-only, never the owner or runtime role; downgrade refuses to drop anything else.
