# Feature Specification: Telemetry stack, claude-otel wrapper, Alloy redaction

**Feature Branch**: `053-telemetry-stack`
**Created**: 2026-11-04
**Status**: Draft
**Input**: Brief `sprints/2026-11-04/briefs/053-telemetry-stack.md` (Shortcut sc-398, sc-399, sc-400, sc-401; epic 395) and `specs/telemetry_spec.md` §3, §4, §5, §8.1, §10, §14 (decisions 6–12 binding).

## Clarifications

### Session 2026-11-04 (answered by the developer, recorded on the board)

- Q: Which log records go to the content stream? → A: `app.content="true"`; Claude Code (`service.name=claude-code`) events `user_prompt`, `assistant_response`, `tool_result`, `tool_decision`, `api_request_body`, `api_response_body`; any `event.name` starting `gen_ai.` (board `contract:content-stream:053`).
- Q: How big is the disk queue and what happens when full? → A: bytes-bounded per signal (traces 256 MiB, logs 256 MiB, metrics 64 MiB); retry until the backend returns; when full, new data is refused (retryable error, logged), senders never block (board `scope:053:queue`).
- Q: Which defaults does the collector stamp? → A: `service.namespace=wcl-agent`, `deployment.environment.name=unknown`, `app.layer=build` for `claude-code` else `runtime`, only when missing (board `scope:053:grafana-labels`).
- Q: Dashboard UI login? → A: anonymous admin, login form off, loopback port only, no stored data.
- Q: Redaction engine? → A: OTTL transform only (stable); the dedicated redaction processor is experimental in the pinned collector (board `scope:053:redaction`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Telemetry is collected locally and survives backend outages (Priority: P1, sc-398)

The owner runs the app with plain `docker compose up`. A local collector is always running and accepts traces, logs and metrics from the app and from Claude Code. When the owner wants to look at the data, they add the `observability` profile, which starts storage backends and a dashboard UI. Data sent while the backends were down is not lost: it is queued on disk and delivered once they are back.

**Why this priority**: every other story sends data into this stack.

**Independent Test**: `observability/test/persistence.sh` sends a span, a log and a metric while the backends are stopped, starts them, and finds all three in the backends.

**Acceptance Scenarios**:

1. **Given** the repository, **When** the owner runs `docker compose up` without a profile, **Then** only the collector is added to the app services, it restarts unless stopped, and its ports listen on 127.0.0.1 only.
2. **Given** the `observability` profile, **When** it is started, **Then** log, trace and metric backends and the dashboard UI start, each on a named volume with a memory limit.
3. **Given** the backends are stopped, **When** a span, a log and a metric are sent to the collector and the backends are then started, **Then** all three can be queried from the backends.
4. **Given** retention settings, **Then** the content stream keeps 7 days, logs 30 days, traces 7 days and metrics 13 months.

---

### User Story 2 - Secrets never reach the backends (Priority: P1, sc-401)

Whatever the build layer (Claude Code) or the runtime layer (the app) sends, known secret keys arrive hashed, and token-shaped values (bearer tokens, JWTs, `sk-*` and `AIza*` keys, Postgres DSNs with passwords) arrive masked, in attributes, span events and log bodies. Per-user and per-session identifiers never become metric labels.

**Why this priority**: content capture is on in dev (owner decision 7); the collector is the last line of defense.

**Independent Test**: `observability/test/redaction.sh` seeds secrets from both layers and checks the stored data in the log and trace backends; disabling any one rule makes it fail.

**Acceptance Scenarios**:

1. **Given** a log and a span from each layer that carry each secret shape, **When** they are stored, **Then** none of the raw secrets can be found, and each appears masked or hashed.
2. **Given** a metric datapoint with `session.id`, `prompt.id`, `user.account_uuid`, `user.email` and `client_request_id`, **When** it is stored, **Then** none of those labels exist on the series.

---

### User Story 3 - Claude Code sessions report telemetry through a project wrapper (Priority: P2, sc-400)

The owner starts Claude Code with `bin/claude-otel` instead of `claude`. The wrapper turns on Claude Code's metrics, events and traces with the settings of spec §5.2 and passes every argument through. If the collector is not reachable, it warns and starts anyway.

**Independent Test**: run the wrapper with a stub `claude` on `PATH` that prints its env and args; run it with the collector down and see the warning and the exec.

**Acceptance Scenarios**:

1. **Given** the wrapper, **When** it runs, **Then** it sets the §5.2 env (cumulative temporality, 10 s metric interval, version/entrypoint/repository included, tool details on, content capture on, resource attributes with `app.layer=build`) and execs `claude` with the arguments unchanged.
2. **Given** the collector is down, **When** the wrapper runs, **Then** it prints one warning to stderr and still execs `claude`.
3. **Given** a real session with two or more subagents (live check), **Then** cost by `agent.name` is queryable in the metrics backend and the trace backend shows the nested subagent tree.

---

### User Story 4 - Click between traces, logs and metrics (Priority: P3, sc-399)

In the dashboard UI the owner jumps from a trace to its logs, from a log line to its trace, and from a metric exemplar to its trace. The datasources are provisioned from files.

**Independent Test**: `observability/test/provisioning.sh` checks via the UI's API that the three datasources load with their correlation settings; the clicks themselves are a live check.

**Acceptance Scenarios**:

1. **Given** the profile is up, **Then** the three datasources exist, provisioned from the repository, and the UI holds no other data.
2. **Given** a trace, a log with `trace_id` and an exemplar, **Then** each links to the other as described.

### Edge Cases

- Backends absent for days (plain `docker compose up`): the disk queue is bounded; when full, the collector refuses new data for that signal and logs the drop; senders are never blocked and the disk is not filled.
- Collector down: the app and Claude Code still run (their exporters drop data); the wrapper warns.
- A log body that is a map (structured GenAI events): the masks apply to its top-level string values too.
- Second stack on the same host: every host port is overridable by env.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Plain compose adds only the collector (pinned image, `restart: unless-stopped`, host ports bound to 127.0.0.1 and overridable by env: OTLP gRPC 4317, OTLP HTTP 4318). The app services are unchanged except the backend's telemetry env (contract `contract:env`), with no dependency of the backend on the collector.
- **FR-002**: The `observability` profile adds a log, a trace and a metric backend (metrics monolithic, filesystem storage) and the dashboard UI (127.0.0.1:3000, overridable), each with a named volume and a memory limit. No object store, no profiler.
- **FR-003**: Retention: content stream 7 days, other logs 30 days, traces 7 days, metrics 13 months.
- **FR-004**: Every collector exporter uses a persistent, size-bounded disk queue; the collector runs at the stability level that this needs.
- **FR-005**: The collector stamps `service.namespace`, `deployment.environment.name` and `app.layer` when missing.
- **FR-006**: Redaction (both layers, all signals): hash the values of `access_token`, `refresh_token`, `client_secret`, `authorization`, `api_key`, `password`; mask bearer tokens, JWTs, `sk-*`/`AIza*` keys and Postgres DSN passwords in every string attribute (resource, span, span event, log, datapoint) and in log bodies.
- **FR-007**: Metric datapoints lose `session.id`, `prompt.id`, `user.account_uuid`, `user.email`, `client_request_id`.
- **FR-008**: Log records are routed to the 7-day content stream when they carry `app.content="true"` or are a known content event (exact names in research.md and on the board, key `contract:content-stream`).
- **FR-009**: Log index labels are only those of spec §9.2 plus the bounded content label.
- **FR-010**: `bin/claude-otel` sets the §5.2 env and execs `claude "$@"`; it warns but never blocks when the collector is unreachable.
- **FR-011**: The dashboard UI's datasources are provisioned as code with trace→logs, log→trace and exemplar→trace correlations; it stores no telemetry and is reachable only locally.
- **FR-012**: Repeatable scripts under `observability/` prove FR-003/004 (persistence), FR-006/007 (redaction) and FR-011 (provisioning), and tear down after themselves.

### Key Entities

- **Signal**: a span, log record or metric datapoint, carrying resource attributes (`service.*`, `deployment.environment.name`, `app.layer`).
- **Content stream**: the log records that carry prompt, response or tool content; kept 7 days.
- **Export queue**: per-exporter on-disk queue, bounded in size.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 3 of 3 signals sent during a backend outage are found after restart (persistence script passes).
- **SC-002**: 0 raw seeded secrets found in the log and trace backends, for both layers (redaction script passes), and disabling any single rule makes the script fail.
- **SC-003**: 0 banned identifiers on stored metric series.
- **SC-004**: The wrapper starts Claude Code in 100% of runs, collector up or down.
- **SC-005**: The three datasources and their correlation settings load on first start with no manual steps.
- **SC-006**: The Python suite stays green (no Python change).

## Assumptions

- Local, single-user dev stack; no auth on the backends beyond loopback binding; the dashboard UI uses a local admin login.
- Prod-only parts (prod drop lists, tail sampling), spanmetrics/servicegraph, dashboards, board/transcript tailing, Faro and profiles are out of scope (sprint 2/3).
- The backend's own exporter and its "starts without the collector" behaviour belong to 054.
