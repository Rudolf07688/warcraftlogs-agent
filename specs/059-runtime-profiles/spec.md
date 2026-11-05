# Feature Specification: Runtime profiles and dashboards

**Feature Branch**: `059-runtime-profiles`
**Created**: 2026-11-05
**Status**: Draft
**Input**: Telemetry 3 (epic 397) stories sc-461, sc-463, sc-462, sc-421 (brief `sprints/2026-11-05/briefs/059-runtime-profiles.md`). Design reference: `specs/telemetry_spec.md` §6.3, §6.4, §6.7, §8.1–8.3, §9, §14.

## Clarifications

### Session 2026-11-05

- Q: Widen the board backfill window or accept Loki's 7 days? → A: Accept. Loki's `reject_old_samples` is a per-tenant limit (one tenant here), so it cannot be widened for the board stream alone: widening it would also admit week-old content records that the 7-day content retention then deletes. Older sprints live in `meta/sprints/*/board.jsonl`, and D13 is fed by `teamstats.py`, not Loki. The Alloy filter stays at 6 days (a day of headroom). Documented in `board-backfill.sh` and the README.
- Q: Finish reasons from a spanmetrics dimension on ADK's span or an app counter? → A: App counter `app.llm.finish_reasons` (`gen_ai.request.model`, `app.llm.finish_reason`), counted on each non-partial model response in the agent runner. The span attribute is an array (spanmetrics would stringify combinations) and google-genai creates enum members for unknown values; the app maps to a fixed set, else `other`.
- Q: Where does conversation depth come from? → A: A turn counter in the ADK session state (`app_turns`, session-scoped key), read by the existing existence check and advanced with the turn's user message (`state_delta`). Chat turns only (workspace runs, not the greeting or guide jobs). Conversations started before the change count from their first later turn.
- Q: Embedding instrument labels? → A: `gen_ai.request.model` and `app.embedding.task` (`document`, `query`), per provider request, so batch size is the texts in that request. Fix round (live check #78): a failed request is recorded too, with `error.type` (its exception class).
- Q: How is profiling switched on? → A: `PYROSCOPE_SERVER_ADDRESS`, read by the telemetry config; profiling runs only when telemetry is on and the address is set. Compose sets it on the backend; the suite sets neither. Fix round (QA PERF-004): compose sets it only when `WCL_PROFILES` is set, so profiling is opt-in.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Requests keep their status with telemetry on (Priority: P1, sc-461)

The owner runs the app with telemetry on. A browser CORS preflight, or a request with the wrong
method for a route, gets the same answer it gets with telemetry off (200 for the preflight,
405 for the wrong method), never a 500.

**Independent Test**: send both requests to the app with and without the instrumentation and
compare statuses; check the recorded server span names.

**Acceptance Scenarios**:
1. **Given** telemetry on, **When** the browser sends an OPTIONS preflight from the dev origin, **Then** the status equals the telemetry-off status and the span is named `OPTIONS <route template>`.
2. **Given** telemetry on, **When** a client POSTs to a GET-only route in an included router, **Then** the status is 405 as with telemetry off and the span is named `POST <route template>`.

### User Story 2 - Declared dependency and a decided board backfill window (Priority: P1, sc-463)

A fresh environment that installs only the declared dependencies can run the pricing generator
and its tests. The owner knows how far back a board backfill reaches and why.

**Acceptance Scenarios**:
1. **Given** the project manifest, **Then** the YAML library the pricing tools import is a direct dependency.
2. **Given** a board entry older than the decided window and a fresh one, **When** the board is (re)read, **Then** the fresh entry lands, the old one is dropped as documented, and the old one does not hold back the fresh one.

### User Story 3 - Runtime dashboards answer the open questions (Priority: P2, sc-462)

On the API dashboard (D6) the owner sees the service graph (which service calls which, with
rates and errors) and p50/p95/p99 latency per route. On the agents dashboard (D7) the owner
sees why model responses ended (finish reasons) and how deep conversations get. On the RAG
dashboard (D8) the owner sees embedding latency and batch size.

**Acceptance Scenarios**:
1. **Given** traces from the API and its callers, **When** D6 loads, **Then** the service graph panel shows edges and p50/p99 sit beside p95.
2. **Given** a chat turn, **When** it ends, **Then** its model responses' finish reasons are counted under a bounded reason and its conversation depth is recorded, and D7 shows both.
3. **Given** embeddings computed for indexing or a search, **Then** their latency and batch size are recorded and D8 shows them.
4. Every new Mimir panel queries a recording-rule alias (or a whole range increase of a raw counter in a stat/table, as today); panels with per-interval bars or legend totals use a window equal to the step.

### User Story 4 - From a slow span to its flame graph (Priority: P3, sc-421)

From a slow backend span in Grafana, "Profiles for this span" opens the CPU flame graph of
that span.

**Acceptance Scenarios**:
1. **Given** the observability profile with profiling configured, **When** a CPU-bound request runs under a span, **Then** the span carries a profile id and the profiling backend returns a flame graph for that span.
2. **Given** profiling not configured (the test suite, a run without the stack), **Then** no profiler starts and nothing changes.

### Edge Cases

- A model provider returns a finish reason the app doesn't know: counted as `other`, never as a new label value.
- A conversation started before this feature: its depth counts from its first turn after the change (documented undercount).
- Profiling configured but the backend down: the app keeps serving; profiles are lost, as with telemetry export.
- Very short spans may carry no CPU samples (spec §6.7): an empty flame graph is expected for them.
- Feedback ratio (spec §7.5) is out of scope: the app has no feedback feature.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: With telemetry on, a request that only partly matches a route MUST get the status it gets with telemetry off, and its server span MUST be named by a route template or the bare method (bounded).
- **FR-002**: The YAML library MUST be a declared direct dependency.
- **FR-003**: The board backfill window is accepted at Loki's 7 days (Alloy drops at 6); the reason is documented next to the backfill script, in the README and on the board.
- **FR-004**: The app MUST count model-response finish reasons per model under a fixed enum label; unknown reasons map to `other`.
- **FR-005**: The app MUST record conversation depth (turns in the conversation so far, from a counter kept in the conversation's agent session state) as a histogram value at the end of each chat turn (not greeting or guide runs), labelled at most by agent; never by conversation, session or user id.
- **FR-006**: The app MUST record embedding latency and batch size per embedding request, labelled by model and task only.
- **FR-007**: Every new metric attribute MUST be on the metric attribute allowlist; anything else is dropped.
- **FR-008**: Recording-rule aliases MUST exist for the new metrics and for D6 p50/p99; D6, D7, D8 panels MUST query them.
- **FR-009**: The trace backend's datasource MUST link to the service graph (from the metrics backend) and to profiles; D6 MUST carry a service graph panel.
- **FR-010**: A profiling backend MUST run in the observability profile with persistent storage; the API MUST attach span profiles only when a profiling address is configured, and never in the test suite.
- **FR-011**: Profiler package versions MUST be pinned.

### Key Entities

- **Finish-reason counter**: per model response; labels model and reason (enum).
- **Conversation-depth histogram**: per chat turn; value = turns so far; label agent.
- **Embedding latency and batch-size histograms**: per embedding request; labels model and task (document, query).
- **Span profile**: CPU samples linked to a server root span by profile id. Fix round (QA PERF-001, SEC-001/002): `setup.SpanProfiles` instead of pyroscope-otel's processor; labels `span_id` and `span_name` (a route template, method or fixed name, final at span start), no trace id; the tags added are the tags removed.

## Success Criteria *(mandatory)*

- **SC-001**: 0 server errors for preflight and wrong-method requests with telemetry on (both cases tested).
- **SC-002**: A clean install from the manifest runs the pricing tests.
- **SC-003**: One chat turn produces a finish-reason count, a depth value and (with search) an embedding latency, visible on D7/D8 within two export intervals.
- **SC-004**: The D6 service graph shows at least one edge from a stack test.
- **SC-005**: A profiled slow span opens a non-empty flame graph in a stack test.
- **SC-006**: No new metric label can take an id or free-text value (allowlist and enum tests bite under mutation).

## Assumptions

- Spec §7.5 (feedback) stays reserved for all three telemetry sprints (PO decision #3).
- The service graph panel is Grafana's Tempo service map, which queries the `traces_service_graph_*` series by their fixed names; that is the one panel that cannot query an alias.
- The profiling backend receives profiles directly from the API (no collector hop), like a local dev setup.
