# Feature Specification: Runtime metrics (ADK metrics, app metrics, runtime dashboards)

**Feature Branch**: `056-runtime-metrics`

**Created**: 2026-11-04

**Status**: Draft

**Input**: Telemetry 2, stream B (sc-411, sc-412, sc-413). Source: `specs/telemetry_spec.md` §6.3, §6.4, §8.2 (D6–D8), §8.3, §9, §14.2; the stories win where they differ.

## Clarifications

### Session 2026-11-04

- Q: Does 411 add ADK metrics or enable experimental ones? → A: Neither; ADK 2.10.0 emits the core set already, the semconv opt-in is set by 054's policy at start-up; 411 pins versions and proves the series and labels (board scope:056:adk).
- Q: Where is the cache counter defined, given `wcl_agent` must not import the backend? → A: In `wcl_agent/cache/cache.py` via the OTel API; KB and TTFT in `backend/app/telemetry/metrics.py` (scope:056:cache).
- Q: Which cache results exist? → A: hit (incl. cached not-found), miss (loader ran: miss, lock timeout, Redis down), error (corrupt entry or loader failure); never stale (scope:056:cache).
- Q: Label names? → A: Namespaced `app.cache.name`, `app.cache.result`, `app.rag.index`, `app.rag.strategy`; TTFT reuses `gen_ai.request.model`, `gen_ai.agent.name` (scope:056:labels).
- Q: When does TTFT start and stop? → A: Start of the turn to its first model text token, once per turn; the closing no-answer message never counts (scope:056:ttft).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agent and model metrics by model and agent (Priority: P1, sc-411)

The operator opens Grafana after a chat and sees how many tokens each model used (by token type), how long agent invocations took, and how many model and tool calls each invocation made, broken down by model and agent, never by conversation, user or session.

**Why this priority**: The agent's cost and latency are the app's main runtime risk; everything in D7 builds on these series.

**Independent Test**: A scripted agent turn (fake model) on an in-memory metric reader behind the production metric pipeline yields the token-usage, invocation-duration and per-invocation call-count series, each labelled with enum values only.

**Acceptance Scenarios**:

1. **Given** telemetry is on, **When** one chat turn runs, **Then** token usage (by model and token type), agent invocation duration (by agent) and inference and tool calls per invocation (by agent) are exported.
2. **Given** any agent metric, **When** its labels are inspected, **Then** each is one of a fixed set (model, agent, token type, operation, provider, tool) and none is an id.
3. **Given** the app starts with telemetry on, **Then** the GenAI semantic-convention opt-in is set by the app itself, and the agent framework and telemetry SDK versions are pinned exactly.

---

### User Story 2 - App metrics: WCL cache, knowledge search, time to first token (Priority: P2, sc-412)

The operator sees the WCL cache hit ratio per cache family, knowledge-base retrieval latency, the number of chunks returned, the best hit's score and how often a search found nothing, and how long users wait for the first word of an answer, per model and agent.

**Why this priority**: These are the signals generic instrumentation cannot infer (a hit versus a miss, an empty search, the first token).

**Independent Test**: In-memory metric reader tests drive the cache, the search and a streamed turn with fakes and read each series and its labels.

**Acceptance Scenarios**:

1. **Given** a WCL cache lookup, **When** it is a hit, a miss or an error, **Then** `app.cache.requests` counts one under that cache family and result.
2. **Given** a knowledge search, **When** it returns, **Then** its duration, chunk count and top score are recorded by index and strategy, and an empty result also increments the empty-result counter.
3. **Given** a streamed chat turn, **When** its first answer text arrives, **Then** `app.llm.stream.ttft` records the wait once, by model and agent.
4. **Given** any of these metrics, **When** a caller supplies an attribute outside the allowlist (an id, a query), **Then** it is dropped before export.

---

### User Story 3 - Runtime dashboards D6, D7, D8 (Priority: P3, sc-413)

The operator opens three provisioned dashboards: API RED (D6), Agents and LLM (D7, evolving the existing API and LLM dashboard, same uid) and Knowledge base (D8). Panels query stable recording-rule aliases, so a semantic-convention rename touches one rules file.

**Why this priority**: Visualisation of P1 and P2; first to be cut (to D7 only) if the sprint slips.

**Independent Test**: The dashboard JSON parses, every metric panel query uses an alias from the rules files or the agreed contracts, and the rules file passes the Mimir rules linter.

**Acceptance Scenarios**:

1. **Given** the stack is up and one chat turn has run, **When** D6, D7 and D8 are opened, **Then** their panels show data (cost waits for the pricing rules of 055).
2. **Given** the latency panels, **Then** the chat websocket and the streaming generate routes are excluded.

### Edge Cases

- Telemetry off (no endpoint, the test suite): every instrument is a no-op and behaviour is unchanged.
- A turn that streams no text (tools only, then the closing no-answer message): no time-to-first-token is recorded.
- A model fallback mid-turn: the time to first token carries the model in use when the text arrived.
- Cache inactive (no Redis): no cache metric, as today's stats.
- A knowledge search whose first pass times out raises: nothing is recorded for it.
- Cardinality: every label set is bounded by enums (15 cache families x 3 results; 4 indexes x 4 strategies; configured models x agents).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Agent metrics named in sc-411 MUST be exported when telemetry is on, labelled only by allowlisted enum attributes.
- **FR-002**: The GenAI semantic-convention opt-in (`gen_ai_latest_experimental`) MUST be set in code at telemetry start-up, unless the operator set the variable.
- **FR-003**: The agent framework and the OTLP exporter MUST be pinned to exact versions matching the lock file.
- **FR-004**: `app.cache.requests` MUST count WCL cache lookups by cache family and result (hit, miss, error); `stale` is never emitted because the cache never serves stale data.
- **FR-005**: Knowledge search MUST record retrieval duration, chunks returned, top score and an empty-result count, by index and strategy (index only for count, score and empties).
- **FR-006**: `app.llm.stream.ttft` MUST record, once per streamed turn, the seconds from turn start to the first model text, by model and agent.
- **FR-007**: Every metric attribute MUST be in the allowlist; anything else is dropped; `session.id` and every id are never allowlisted.
- **FR-008**: Recording rules `genai:tokens:rate5m`, `genai:invoke_agent_latency:p95`, `rag:retrieval_latency:p95`, `cache:hit_ratio` MUST be defined in the runtime rules file and pass the Mimir linter.
- **FR-009**: D6, D7 and D8 MUST be provisioned JSON whose metric panels query only recording-rule aliases; D7 keeps the existing uid.

### Key Entities

- **Metric instrument**: name, unit, kind, allowed attributes; one definition each.
- **Recording-rule alias**: stable name over raw OTel series, owned per file.
- **Dashboard**: provisioned JSON, uid, panels over aliases.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After one chat turn, the operator can read tokens by model and type, invocation latency and calls per invocation without writing a query.
- **SC-002**: Zero exported metric series carries an id, a session id, a query text or a raw path (verified by test).
- **SC-003**: Every new instrument is covered by an automated test that reads the exported data; a removed label filter fails a test.
- **SC-004**: All three dashboards open with populated panels after one live chat (live check by team-lead).

## Assumptions

- ADK 2.10.0 already emits the core metrics; no experimental ADK metrics are enabled.
- Mimir's no-auth tenant is `anonymous` (rules dir `observability/mimir/rules/anonymous/`, 055).
- RED and cost aliases come from 055 (`contract:red-aliases`, `contract:cost-alias`); D6 and D7 build against the names before 055 merges.
- In-process memo hits of the WCL cache are not counted, as in the existing admin stats.
