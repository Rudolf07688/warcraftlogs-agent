# Feature Specification: Data-store telemetry (Postgres, Redis, slow-query links, D9–D11, local alerts)

**Feature Branch**: `058-datastore-telemetry`

**Created**: 2026-11-05

**Status**: Draft

**Input**: Sprint 2026-11-05 brief `058-datastore-telemetry.md` (epic 397 "Telemetry 3"), stories
sc-417, sc-418, sc-419, sc-420, sc-424. Design reference: `specs/telemetry_spec.md` §7.2–7.4, §8.2
(D9–D11), §8.4, §9, §14. The stories win where they differ.

## Clarifications

### Session 2026-11-05

Answered by the developer (owner preference 16); each is a board decision `scope:058:*`.

- Q: How does the collector read Docker (container logs, container names)? → A: Through a GET-only
  Docker socket proxy on an internal network; Alloy never mounts the raw socket (#32).
  **Superseded by the security rework (T032, research R7):** the proxy still exposed every
  container's files and env, so it is gone. Postgres writes its log to files on the `pglog` volume,
  Alloy tails them read-only and has no Docker access at all; only cAdvisor names containers.
- Q: Where does cAdvisor run? → A: A separate, unprivileged service in the observability profile with
  read-only host mounts, because naming containers on this Docker needs the containerd socket (#33).
- Q: How do exporter metrics reach Mimir? → A: Prometheus remote write with series allowlists and fixed
  job/instance labels, outside the OTLP path (#34).
- Q: Is statement text a metric label? → A: No; top statements by query id, text found in the masked
  slow-query log by the same id; utility statements untracked (#35).
- Q: What is the Postgres log format and masking? → A: stderr format with a parseable prefix (since
  T032 written by the logging collector to files on the `pglog` volume), bound values
  never logged, Alloy masks literals and quoted values and routes through the redaction chain (#36);
  the monitoring role exists only when its password is configured (#37); the sqlcommenter carries
  only `traceparent` (#30); the spend threshold is one constant rule (#38).

## User Scenarios & Testing *(mandatory)*

The user is the owner (a single developer running the app and its telemetry stack locally) and
the agent team that builds it. They look at Grafana to understand how the app's data stores
behave and whether the telemetry pipeline itself is healthy.

### User Story 1 - See what the database spends its time on (Priority: P1) — sc-417

The owner opens the Postgres dashboard and sees connections, throughput, cache hit ratio, locks,
long transactions, vacuum and WAL activity, the statements that cost the most total time, and the
size of the knowledge base's vector indexes and the row count of its embedding tables.

**Why this priority**: the app's latency is dominated by database and model calls; without
statement-level data the owner can't tell which query to fix.

**Independent Test**: seed a database with a vector index holding rows and run a deliberately
slow statement; the dashboard's top statement by total time is that statement and the index size
equals what the database itself reports.

**Acceptance Scenarios**:

1. **Given** statement statistics are enabled, **When** a statement runs repeatedly for 0.4 s,
   **Then** it is the top statement by total time in Grafana.
2. **Given** the knowledge base has an HNSW index with rows, **When** the owner opens D9,
   **Then** the index size shown is greater than zero and equals the database's own relation
   size, and the embedding table row count equals the rows inserted.
3. **Given** the collector connects to the database, **Then** it uses a monitoring-only role
   (never the owner or a superuser) and no password appears in any metric label or collector log.

---

### User Story 2 - Compare Redis's hit ratio with the app's (Priority: P2) — sc-418

The owner opens the Redis dashboard and sees memory used against the limit, evictions,
operations per second, connected clients, command latency and Redis's own keyspace hit ratio
next to the app's cache hit ratio.

**Why this priority**: the two ratios disagree by design (the app counts logical lookups, Redis
counts key reads); seeing both side by side shows whether the cache layer works.

**Independent Test**: make a known number of hits and misses against a fresh Redis; the Redis hit
ratio shown equals hits / (hits + misses).

**Acceptance Scenarios**:

1. **Given** a fresh Redis, **When** 7 reads hit and 3 miss, **Then** Redis's hit ratio is 0.7.
2. **Given** the app reports cache lookups, **Then** D10 shows the app ratio in the panel next to
   Redis's.
3. **Given** any keys exist, **Then** no key name becomes a metric label.

---

### User Story 3 - Jump from a slow query to its trace (Priority: P1) — sc-419

When a statement takes longer than 250 ms, Postgres logs it; the line lands in Loki with the trace
id of the request that issued it, and one click opens that trace in Tempo. Lock waits and
autovacuum runs are logged too.

**Why this priority**: the trace shows which request and agent step caused the slow statement; the
log alone does not.

**Independent Test**: run a slow statement carrying a trace context; the log line in Loki carries
that trace id and the datasource's derived field resolves it; a secret literal in the statement
never appears in Loki.

**Acceptance Scenarios**:

1. **Given** telemetry is on, **When** the app runs a statement inside a traced request,
   **Then** the SQL sent to the database carries the W3C `traceparent` of the statement's span.
2. **Given** telemetry is off, **Then** the SQL sent is byte-identical to the uninstrumented SQL.
3. **Given** a statement runs for more than 250 ms, **Then** its log line is in Loki with the
   statement's trace id as a link that opens the trace.
4. **Given** that statement contained a string or numeric literal (for example a password or an
   account id) or bound parameters, **Then** Loki holds the line with the literals masked and no
   parameter values.
5. **Given** a session waits on a lock longer than the deadlock timeout or autovacuum processes a
   table, **Then** the corresponding Postgres log line is in Loki.

---

### User Story 4 - Watch the infrastructure and the telemetry pipeline (Priority: P2) — sc-420

The owner opens D11 and sees container CPU and memory per service, the collector's export queue
and drops, ingest rates per backend, and active series against the 50k budget.

**Why this priority**: the telemetry stack must stay within its resource and cardinality budget
on a laptop; drops must be visible, not silent.

**Independent Test**: bring up the stack; D9, D10 and D11 are provisioned, every panel query is
valid, and the active-series panel shows the live count with the 50k budget line.

**Acceptance Scenarios**:

1. **Given** the observability profile runs, **Then** container metrics and the self-metrics of
   the collector and the three storage backends are scraped.
2. **Given** D9, D10 and D11 are provisioned, **Then** each loads with uids `wcl-d9-postgres`,
   `wcl-d10-redis`, `wcl-d11-infra` and every query reads a recording-rule alias.

---

### User Story 5 - Be told when telemetry breaks or the build spend runs away (Priority: P3) — sc-424

Two Grafana-managed alert rules, provisioned from the repository: one for collector export
failures or dropped spans/logs, one for estimated Claude Code spend per day above a configurable
threshold.

**Why this priority**: first in the drop order after Pyroscope; useful but not needed to read the
dashboards.

**Independent Test**: trigger each condition synthetically; each rule goes Firing and back to
Normal.

**Acceptance Scenarios**:

1. **Given** the backend refuses a log batch for good, **Then** the pipeline rule fires, and goes
   back to Normal once the failure window has passed.
2. **Given** synthetic build spend above the threshold, **Then** the spend rule fires; raising the
   threshold returns it to Normal.

### Edge Cases

- The owner's existing database volume: it must start unchanged apart from the extension and the
  new role.
- Monitoring password not configured: the migration skips the role (no default password), the
  exporter reports the database as down, nothing else breaks.
- Several compose projects on one Docker host (the owner's stack and the test stacks): each
  collector reads only its own project's containers.
- A multi-line SQL statement in the log: one record per log message, not per line.
- Error messages that quote values (duplicate key details, invalid input): masked like literals.
- Telemetry backends down: exporter metrics wait in the collector's write-ahead log; logs wait in
  the existing disk queue.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The database MUST load statement statistics at start and the migration MUST create
  the extension; the existing data volume starts unchanged otherwise.
- **FR-002**: The collector MUST scrape Postgres with the §7.2 non-default collectors
  (`stat_statements`, `long_running_transactions`, `statio_user_indexes`,
  `stat_activity_autovacuum`, `process_idle`, `database_wraparound`) and never include SQL text
  as a label.
- **FR-003**: Custom queries MUST report the size of every vector index (HNSW, IVFFlat) and the
  live row count of every table with a vector column.
- **FR-004**: The collector MUST connect to Postgres as a role that is a member of `pg_monitor`
  only: no superuser, no table ownership, no table privileges.
- **FR-005**: The collector MUST scrape Redis for memory, evictions, keyspace hits and misses,
  clients and command latency, without key checks.
- **FR-006**: With telemetry on, every SQL statement issued inside a recording span MUST carry a
  `traceparent` comment; with telemetry off, SQL MUST be unchanged.
- **FR-007**: Postgres MUST log statements over 250 ms, lock waits and autovacuum runs, with bound
  parameter values never logged for non-error statements.
- **FR-008**: Postgres log lines MUST reach Loki through the collector's redaction path, with
  string and numeric literals in SQL and quoted values in messages masked, and the trace id as
  structured metadata.
- **FR-009**: The Loki datasource MUST offer a link from the slow-query line's trace id to Tempo.
- **FR-010**: The collector MUST scrape container metrics (bounded labels: compose service only)
  and the self-metrics of itself, Loki, Tempo and Mimir (only the series D11 and the alerts need).
- **FR-011**: D9, D10, D11 MUST be provisioned; their queries MUST use recording-rule aliases
  from `datastores.yaml` or an existing rule file; per-interval bars or legend totals MUST use a
  window equal to the step.
- **FR-012**: Two Grafana-managed alert rules MUST be provisioned: pipeline failures/drops, and
  daily build spend above a configurable threshold.
- **FR-013**: No DSN or password MUST be in the repository, the collector's UI or logs, or a
  metric label.
- **FR-014**: The test stack's db and redis host ports MUST be overridable, defaulting to 5432 and
  6379.

### Key Entities

- **Monitoring role**: a login role in `pg_monitor`, name and password from the environment.
- **Slow-query record**: a Loki record from the `postgres` service: masked message, duration,
  query id, severity, trace id and span id as structured metadata.
- **Recording-rule aliases**: `pg:*`, `redis:*`, `infra:*`, `meta:*` series the dashboards read.
- **Alert rules**: two provisioned rules with a threshold the owner can change in one place.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a seeded stack, the top statement by total time is the seeded slow one, and the
  vector index size equals the database's own figure (exact bytes).
- **SC-002**: Redis's hit ratio equals hits / (hits + misses) made by the test (to 0.01).
- **SC-003**: A slow statement's log line is in Loki within 60 s with its trace id, and a seeded
  secret literal in it is absent from Loki.
- **SC-004**: D9, D10 and D11 load with every panel query valid; the stack's added series stay
  below 10% of the 50k budget.
- **SC-005**: Each alert rule goes Firing within 3 minutes of its trigger and Normal again.
- **SC-006**: The added per-statement overhead of the trace comment is measured and recorded.

## Assumptions

- Local-only app and stack (spec §14 decision 5). As built (T032): Postgres logs go to files on
  the `pglog` volume (`logging_collector`), not to stderr and Docker's log driver; `docker compose
  logs db` shows only the start-up lines.
- Grafana alert notifications need no contact point beyond the default; the state is what counts.
- Query text stays out of metric labels (§9.3); the slow-query log is where statement text is
  read, linked by query id.
- The owner (team-lead) adds the monitoring password to `.env` before the live check.
