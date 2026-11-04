# Feature Specification: Build telemetry (board into Loki, RED from traces, D1/D2, pricing)

**Feature Branch**: `055-build-telemetry`

**Created**: 2026-11-04

**Status**: Draft

**Input**: Sprint 2026-11-04b stream A (Telemetry 2, epic 396): stories sc-407, sc-409, sc-408, sc-410, in that order, on top of a Mimir ruler foundation. Design reference `specs/telemetry_spec.md` §4.2, §5, §6.5, §8.2, §8.3, §9, §14; the story AC and the PO's notes win where they differ.

## Clarifications

### Session 2026-11-04

- Q: Which Loki stream do board entries land in? → A: The 30-day stream (board text is agent prose, not prompts); redaction applies either way (board #30).
- Q: What does "backfills after a Loki restart" cover? → A: A restart with its volume is covered by Alloy's queue and tail position; after data loss a backfill script resets the tail position and Alloy re-reads the files (entry ts kept, Loki dedups), within Loki's reject window (board #31).
- Q: How is seat cost derived? → A: Per sprint from usage.txt, seat = roster name in the agent label, USD = weighted units × Opus input list price, labelled so (board #32).
- Q: How are prices exposed? → A: Recording rules generated from pricing.yaml (vector constants), cost rule in the same group; a test catches drift (board #33).
- Q: Which `cc:*` aliases exist? → A: cost (5m, 1h), tokens, cache hit ratio, sessions, active time, LOC, commits, PRs, edit decisions (board #34).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Team board in Loki with trace links (sc-407, Priority: P1)

The owner and team-lead look at a sprint's team board next to the build telemetry: each board
entry is a log line in Loki, and from a hand-off entry they open the trace of the tool call
that posted it.

**Why this priority**: Claude Code reports every developer as `agent.name=developer`; the board
is the only source of seat identity, so it is the join between the team and its telemetry.

**Independent Test**: post a board entry with a `TRACEPARENT` set, start the stack, find the
entry in Loki with its trace id and only the allowlisted index labels; restart Loki with an
empty volume and find it again.

**Acceptance Scenarios**:

1. **Given** a session that passes `TRACEPARENT` to Bash, **When** an agent posts a board entry, **Then** the entry stores the full traceparent (trace id and span id).
2. **Given** a plain shell without `TRACEPARENT`, **When** an agent posts, **Then** the entry posts without the field, and older entries without it still read, wait and render.
3. **Given** the observability stack, **When** an entry is appended to a board file, **Then** it appears in Loki with its trace id as a link target and only §9.2 index labels.
4. **Given** a board entry text holding a secret, **When** it reaches Loki, **Then** the secret is masked by the same redaction chain as all other logs.
5. **Given** Loki loses its data, **When** it comes back, **Then** the board backfills from the file.
6. Session transcripts are not tailed.

---

### User Story 2 - RED metrics from traces (sc-409, Priority: P2)

Rate, errors and duration per HTTP route come from the backend's spans, with exemplars that
link a latency point to a trace, plus a service graph.

**Independent Test**: send synthetic server spans for two routes (one of them `/ws/chat`),
query the RED aliases and see the calls, the errors, p95 without the chat route, exemplars on
the latency histogram, and no id or raw URL label.

**Acceptance Scenarios**:

1. **Given** server spans with `http.route`, **When** they pass Alloy, **Then** span metrics exist per route with the §4.2 extra dimensions and exemplars, and service-graph metrics exist for client/server pairs.
2. **Given** span attributes `session.id`, `url.full`, `db.query.text` or ids, **Then** none of them is a metric label.
3. **Given** the recording rules, **Then** `app:http_requests:rate5m` is per service, route and status code, and `app:http_latency:p95` excludes `/ws/chat` and routes matching `.*/generate`.

---

### User Story 3 - Build dashboards D1 and D2 (sc-408, Priority: P3)

The owner sees Claude Code spend, tokens and cache efficiency (D1) and the agent team's cost
and activity by model, `agent.name` and board seat (D2).

**Independent Test**: provision Grafana, load both dashboards, and check every panel query
uses a recording-rule alias and every cost panel says "estimated, list price".

**Acceptance Scenarios**:

1. D1 extends the existing overview dashboard (same uid); D2 is a new dashboard linked to and from "Agent Team: Improvement" (D13), which keeps working.
2. Cost is shown by model, by `agent.name` and by board seat (per sprint, pushed at wrap-up); if seat cost can't be derived honestly, per role, and the board says so.
3. Panels on live Claude Code metrics query `cc:*` aliases, not raw metric names.

---

### User Story 4 - LLM pricing and cost rules (sc-410, Priority: P4, drop first)

Runtime LLM cost in dollars is computed from token counts and a versioned price table.

**Independent Test**: push synthetic token usage for one Claude and one Gemini model and check
`genai:cost_usd:rate5m` equals tokens × price per second.

**Acceptance Scenarios**:

1. A price table (model × token type) in the repo is exposed as `llm_price_usd_per_token`.
2. `genai:cost_usd:rate5m` is USD per second by `gen_ai_request_model`, `gen_ai_agent_name`, and matches the arithmetic for Claude and Gemini.
3. A price change is a config commit; cost computed for the past stays at the old price.

### Edge Cases

- Board entries posted while Alloy or Loki is down: the file is the source of truth; the tail resumes from its position (Alloy) or re-reads (Loki loss).
- Board dir mounted from a worktree, where `./.git` is a file: the mount path is configurable.
- A model with no price row: no cost series (not zero), so a missing price is visible.
- Cursor files and the `active` file in the board dir must not be tailed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The board tool MUST store the full `TRACEPARENT` of the posting process on each entry when it is set and valid, and post without it otherwise.
- **FR-002**: Reading, waiting and rendering MUST work for entries with and without the field.
- **FR-003**: The collector MUST tail only board `*.jsonl` files into Loki through the redaction chain, with index labels limited to the §9.2 allowlist; entry fields (author, kind, key, id, trace id) stay structured metadata.
- **FR-004**: The board MUST backfill into an empty Loki.
- **FR-005**: The `bin/claude-otel` comment MUST state that only `CLAUDE_CODE_ENABLE_TELEMETRY`, `..._BETA` and `TRACEPARENT` reach the session's Bash.
- **FR-006**: Span metrics and service graph MUST be computed from all traces before any sampling, with exemplars, without ids, raw URLs, SQL text or `session.id` as dimensions.
- **FR-007**: The metrics store MUST evaluate version-controlled recording rules, one file per owner.
- **FR-008**: RED, build (`cc:*`) and cost aliases MUST exist as recording rules with the names in the board contracts.
- **FR-009**: D1 and D2 MUST be provisioned from version-controlled JSON; cost panels labelled "estimated, list price".
- **FR-010**: Seat cost per sprint MUST be pushed by the wrap-up stats tool.
- **FR-011**: The price table MUST be the single source of prices; price history MUST stay correct after a change.
- **FR-012**: Every stack proof MUST be a re-runnable script under `observability/test/`.

### Key Entities

- **Board entry**: id, ts, author (seat name), kind, text, optional key/supersedes/refs, new optional traceparent.
- **Price row**: model id, token type (input, output, cache read, cache write), USD per token, effective date (implicit in git history).
- **Recording rule alias**: stable name a dashboard queries; owned by one rules file.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A board entry is searchable in Loki within 1 minute of posting and its trace opens in one click.
- **SC-002**: After a Loki data loss, 100% of board entries are back after the collector re-reads the file.
- **SC-003**: A seeded secret in a board entry never arrives unmasked.
- **SC-004**: Every panel of D1 and D2 queries an alias; zero raw metric names on live-metric panels.
- **SC-005**: Computed cost matches tokens × list price within 1% for one Claude and one Gemini model.
- **SC-006**: No span-metric series carries an id, raw URL or session label.

## Assumptions

- Mimir runs without multitenancy; its tenant id is `anonymous`.
- Board text is agent prose, not prompts: it goes to the 30-day stream.
- Runtime token usage carries token types input and output only; cached input is priced as input (an overestimate, stated on the panel).
- Live per-seat attribution is Telemetry 3; this feature gives per-sprint seat cost.
- Model ids come from what `wcl_agent/llm/` emits; list prices are public list prices at the commit date.
