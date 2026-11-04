# Feature Specification: Backend telemetry (traces, logs, content policy)

**Feature Branch**: `054-backend-telemetry`
**Created**: 2026-11-04
**Status**: Draft
**Input**: Shortcut stories sc-402..406 (epic 395, "Telemetry 1"); design reference
`specs/telemetry_spec.md` §6.1–6.3, §6.6, §10, §14. Security-core.

## Clarifications

### Session 2026-11-04

- Q: Where does the app-side redaction run: a span processor on the request path, or a wrapper around the exporters? → A: A wrapper around the span and log exporters (the "redaction span processor" of §6.1): it runs in the export thread, so redaction never costs the event loop, and it sees every record, including the agent framework's own log events.
- Q: Beyond the three ADK lockdown settings, does the app enforce "no content outside dev" itself? → A: Yes. In lockdown the same wrapper strips the known content attributes (gen_ai input/output/system/tool messages, gcp.vertex.agent request/response/tool args/tool response/data, HTTP bodies) and drops `gen_ai.*` content log events, so a framework bug cannot leak content.
- Q: Is the content policy (env settings) applied when telemetry is off? → A: No. With no endpoint the bootstrap does nothing at all (no env changes, no providers), so the test suite is untouched; nothing can export without providers.
- Q: Do the one-shot GenAI spans carry prompt or reply content? → A: No. Metadata only (operation, provider, models, tokens, finish reason, error type), in every environment.
- Q: How does a local (non-compose) run pick up the endpoint from `.env`? → A: The bootstrap loads `.env` the same way the settings do (honouring `WCL_LOAD_DOTENV`), before deciding; it must not import the settings module, which imports the agent framework.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Telemetry is off unless configured (Priority: P1, sc-402)

The owner runs the backend with the observability stack (053) and sees its traces, logs and
metrics, labelled with the service, version, layer and environment. Without a collector
configured, the backend behaves exactly as before.

**Why this priority**: every other story builds on the bootstrap, and "off by default" protects
the test suite and any run without the stack.

**Independent Test**: start the app with and without the collector endpoint; check which
providers and instrumentations are present and what resource labels they carry.

**Acceptance Scenarios**:

1. **Given** no collector endpoint, **When** the backend starts, **Then** no telemetry
   pipeline or library instrumentation is installed and the test suite is unchanged.
2. **Given** a collector endpoint, **When** the backend starts, **Then** tracer, meter and
   logger pipelines are installed before the agent framework is imported, with the resource
   `service.name=api`, the git sha as `service.version` and `vcs.ref.head.revision`,
   `app.layer=runtime` and `deployment.environment.name`.
3. **Given** a collector endpoint that is down, **When** the backend starts and serves
   requests, **Then** it starts and serves normally; export failures stay quiet.

---

### User Story 2 - Content policy per environment (Priority: P1, sc-406)

In dev the owner can read prompts, answers and tool input/output on the agent's spans and
events (7-day content stream). Anywhere else no content leaves the process, and secrets never
do, in any environment.

**Independent Test**: run an agent turn with in-memory exporters under `dev` and under
`ci`/`prod`/unset; search the exported data for the prompt, answer and a planted secret.

**Acceptance Scenarios**:

1. **Given** `WCL_ENVIRONMENT=dev`, **When** a turn runs, **Then** prompt, response and tool
   I/O are on the agent spans/events, and content log events carry `app.content="true"`.
2. **Given** `WCL_ENVIRONMENT` is `ci`, `prod`, unset or anything else, **When** a turn runs,
   **Then** the three agent lockdown settings are in force and no prompt, response or tool
   content is exported.
3. **Given** content capture is on, **When** a span attribute, event or log carries a secret
   (bearer token, API key, credentials in a URL, a sensitive key's value), **Then** the
   exported value is masked.

---

### User Story 3 - Logs with trace ids, redacted (Priority: P1, sc-405)

The owner opens a log line in Grafana and jumps to its trace. Secrets passed as structured
log fields are exported redacted.

**Independent Test**: log inside a span with a token in `extra`; inspect the exported record.

**Acceptance Scenarios**:

1. **Given** telemetry on, **When** code logs inside a span, **Then** the exported record
   carries that span's trace and span id, and stdout logging still works.
2. **Given** a token passed in `extra`, **When** it is exported, **Then** the value is the
   redaction marker.
3. **Given** the collector is down, **When** the exporter logs its own failures, **Then** those
   records are not fed back into the exporter (no loop).

---

### User Story 4 - One chat turn is one trace (Priority: P2, sc-403)

The owner opens a chat turn in Tempo and sees the whole turn as one trace: the turn's entry
span, the agent invocation, model calls and tool executions, and under them the WCL HTTP
calls, SQL statements and Redis commands.

**Independent Test**: drive one chat turn with fakes and in-memory exporters; all spans share
one trace id with the expected parent chain.

**Acceptance Scenarios**:

1. **Given** telemetry on, **When** a chat turn runs, **Then** its spans form a single trace
   rooted at the turn's entry span, with `invoke_agent` → `generate_content` / `execute_tool`
   → WCL HTTP → SQL → Redis beneath it.
2. **Given** an HTTP request to a route, **When** it is traced, **Then** the span names the
   route template, never the raw path; health and readiness requests are not traced.
3. Queue-fed background writers (FetchWriter, KbIndexer) may start their own traces; this is
   documented.

---

### User Story 5 - GenAI spans for one-shot model calls (Priority: P3, sc-404)

Chat titles, suggestions, reports, guides and embeddings each show up as a GenAI client span
with model, token usage and finish reason, for Claude (Anthropic API and Model Garden) and
Gemini. Second to drop if the sprint slips.

**Independent Test**: a chat-title call against faked Claude (both providers) and Gemini
clients; inspect the exported span.

**Acceptance Scenarios**:

1. **Given** telemetry on, **When** a one-shot call runs, **Then** one span carries
   `gen_ai.operation.name`, `gen_ai.request.model`, input/output token usage and finish reason.
2. **Given** a call that fails, **Then** the span ends with an error status and error type.

### Edge Cases

- `WCL_ENVIRONMENT` set to an unknown value or different case → treated as lockdown unless it
  is exactly `dev` after trimming and lower-casing.
- Content settings already in the environment: in lockdown the three settings are forced; in
  dev an explicit operator value is respected.
- Token-usage attributes (`gen_ai.usage.*_tokens`) are numbers, not secrets, and must not be
  masked by the "token" key rule.
- Collector unreachable at shutdown: the flush is bounded by the exporter timeout.
- The websocket chat route lasts the whole connection: it is not traced as one span.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Telemetry MUST be enabled iff `OTEL_EXPORTER_OTLP_ENDPOINT` is set; when off,
  no provider or instrumentation is installed.
- **FR-002**: When on, the tracer, meter and logger providers MUST be set before the agent
  framework is imported, with the resource attributes of US1 scenario 2.
- **FR-003**: Export MUST use OTLP over HTTP/protobuf; metrics MUST use cumulative temporality
  and exponential histograms. Telemetry packages MUST stay within the agent framework's pin.
- **FR-004**: Export MUST never block a request or startup: batching with bounded queues,
  failures dropped quietly.
- **FR-005**: The environment MUST come from `WCL_ENVIRONMENT`; only `dev` enables content;
  every other value (including unset) MUST force the three lockdown settings.
- **FR-006**: An app-side redaction step MUST mask secrets in every exported span attribute,
  span event, status message and log record (body and attributes), with content on or off.
- **FR-007**: In lockdown, known content attributes and content log events MUST be removed
  before export even if the agent framework emitted them.
- **FR-008**: Log records carrying prompt/response/tool content MUST carry `app.content="true"`.
- **FR-009**: An OTLP log handler MUST export app logs with trace/span ids and MUST carry the
  redaction filter itself; stdout logging stays.
- **FR-010**: Web routes, SQL on the app engine, Redis and outbound HTTP MUST be instrumented;
  health/readiness and the websocket connection MUST be excluded; each chat turn MUST be the
  root of its own trace.
- **FR-011**: One-shot model calls MUST each produce one GenAI client span (see US5).
- **FR-012**: No id (session, user, tenant, conversation) MAY become a metric label.

### Key Entities

- **Telemetry configuration**: endpoint present, environment, content allowed, version.
- **Content policy**: the env settings it forces and the content attribute/event names it
  strips in lockdown.

## Success Criteria *(mandatory)*

- **SC-001**: With no endpoint, the full test suite passes unchanged and no instrumentation is
  installed (test).
- **SC-002**: In every non-dev environment, a planted prompt, answer and tool result appear in
  0 exported records (test).
- **SC-003**: A planted secret appears in 0 exported records, with content on (test,
  mutation-checked).
- **SC-004**: A traced chat turn produces exactly 1 trace id across all its spans (test).
- **SC-005**: With the collector down, startup and a request complete without waiting on the
  exporter (test with an unreachable endpoint).

## Assumptions

- The observability stack (053) provides Alloy on `http://alloy:4318` and sets the env vars.
- Live checks (Tempo, Grafana, real model calls) are run by team-lead on the merged tip.
- System metrics, custom app metrics, sqlcommenter and Pyroscope are later sprints.
