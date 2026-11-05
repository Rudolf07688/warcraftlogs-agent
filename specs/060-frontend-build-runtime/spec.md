# Feature Specification: Frontend dashboard, build-vs-runtime dashboard and end-to-end redaction tests

**Feature Branch**: `060-frontend-build-runtime`
**Created**: 2026-11-05
**Status**: Draft
**Input**: Sprint 2026-11-05 brief 060 (Shortcut sc-416, sc-423, sc-422; epic 397 "Telemetry 3"). Design reference: `specs/telemetry_spec.md` §1 goal 4, §7.1, §8.2 (D5, D12), §10, §12 (P7), §14.

## Clarifications

### Session 2026-11-05 (answered by the developer, board scope:060:*)

- Q: Faro's own ErrorBoundary or our own? → A: Our own small boundary reporting through the registered Faro instance (same payload shape as Faro's: component stack, "React ErrorBoundary" name); importing Faro's would load Faro into the main bundle that 057 keeps Faro-free.
- Q: Which panels get a boundary? → A: The app shell, the sidebar, the message list and the composer.
- Q: How is the route attached? → A: Faro's view meta is the matched route template, set at start and on each navigation; errors also carry route and boundary name.
- Q: What is a real stream abort? → A: The chat connection closing while that connection's turn streams (lost, or closed by the app); an error frame is not an abort.
- Q: What does a runtime delta compare against? → A: The version's mean over the dashboard range minus the mean of all versions over the same range (stated on the dashboard).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A broken panel is reported, not shown (sc-416, Priority: P1)

The owner uses the chat. When one part of the screen fails to render (the message list, the
sidebar, the composer, or the whole app shell), that part shows a plain "something went wrong"
notice with a retry button, the rest of the app keeps working, and the failure is reported to
the frontend telemetry with the route it happened on. The notice never shows the error's text
or stack (it can carry model or WCL text). Chat moments (message sent, first token on screen,
answer complete, stream cut off) are reported as events, so the owner can see on the Frontend
dashboard (D5) Web Vitals at p75 by route, the JS error rate and top errors, client-side
time-to-first-token and stream aborts.

**Why this priority**: it is the visible part of the sprint and the error boundary protects the user.

**Independent Test**: a component that throws inside each boundary renders the fallback (no
message text), reports once with its route, and the other panels stay mounted; a synthetic
component error posted to the receiver appears on D5's top-errors query with its route.

**Acceptance Scenarios**:

1. **Given** the message list throws while rendering, **When** the app renders, **Then** the message list area shows the plain fallback with a retry, the sidebar and composer still work, and one error with route and boundary name is reported.
2. **Given** a fallback is showing, **When** the user presses retry, **Then** the panel renders again.
3. **Given** a turn is sent, **When** the first token is on screen and the answer finishes, **Then** `agent_message_sent`, `agent_first_token_rendered` (with the time since send) and `agent_response_completed` each fire exactly once for that turn.
4. **Given** a turn is streaming, **When** the connection drops or the chat is left, **Then** `stream_aborted` fires once; a server error frame or a normal finish never fires it.
5. **Given** a synthetic component error with a known route reaches the stack, **When** D5's top-errors query runs, **Then** the error appears with that route.

---

### User Story 2 - Seeded secrets never reach a backend (sc-423, Priority: P1)

The owner needs proof that secrets (bearer tokens, JWTs, `sk-`/`AIza` keys, DSN passwords)
sent through the telemetry paths of the app and the build layer (shaped like Claude Code, the real backend
telemetry bootstrap, the browser receiver) are masked before they are stored in any backend
(logs, traces including span attributes and events, metrics including labels and values).

**Why this priority**: it is the sprint's security proof; a test that passes when it should not is the worst outcome.

**Independent Test**: one script runs against a fresh test stack and exits 0; the same script exits non-zero when one redaction rule in a copied collector config is disabled.

**Acceptance Scenarios**:

1. **Given** the full test stack, **When** the script seeds every secret shape through every path, **Then** no seeded value is found unmasked in any backend and the script passes.
2. **Given** a copy of the collector config with one redaction rule disabled, **When** the script runs, **Then** it fails and names the leak.
3. **Given** a new secret shape or a new path (for example a database slow-query log), **When** a maintainer adds it, **Then** it is one row in one table.

---

### User Story 3 - Which commit and seat moved the numbers (sc-422, Priority: P2)

The owner opens the Build ⇄ Runtime dashboard (D12) and sees, over runtime p95 latency, error
rate and LLM cost per request, a marker for each running app version (commit), and a table
mapping commit → authoring seat (from the team board) → estimated build cost → runtime deltas.
The attribution rule is stated on the dashboard.

**Why this priority**: it joins the two layers (spec goal 4); it depends on data the other streams already produce.

**Independent Test**: a scripted run with two app versions, the second slower and failing more, plus a board naming the second commit's seat, shows the second commit in the table against that seat with a positive latency and error delta.

**Acceptance Scenarios**:

1. **Given** two versions ran in the dashboard's range, **When** D12 loads, **Then** each version shows as an annotation over the three runtime panels.
2. **Given** a board hand-off or merge entry names a commit, **When** the table loads, **Then** the commit row shows that entry's seat, the build-cost estimate when one exists, and its runtime deltas.
3. **Given** a running version no board entry names, **Then** the row shows "unattributed" rather than a guess.

### Edge Cases

- An error thrown inside the fallback itself, or before telemetry is configured: no crash loop, nothing reported when telemetry is off.
- A second socket (React StrictMode remount) closing must not abort another socket's turn.
- An `error` frame ends the turn without `agent_response_completed` or `stream_aborted`.
- No board usage file yet (mid-sprint): build cost is left empty, not estimated as zero.
- Event attributes stay bounded: no message text, no ids beyond what 057 sends.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The app shell and each chat panel (sidebar, message list, composer) MUST sit inside its own error boundary that reports the error to the frontend telemetry with the route template and boundary name, and renders a plain fallback with a retry.
- **FR-002**: The fallback MUST NOT render the error message or stack.
- **FR-003**: A panel boundary MUST contain its failure: the other panels stay mounted.
- **FR-004**: The app MUST send `agent_message_sent`, `agent_first_token_rendered` (time since send), `agent_response_completed` (duration) and `stream_aborted` (reason) once each at their moment; `agent_feedback` is not sent (no feedback feature).
- **FR-005**: Every frontend signal MUST carry the current route template, so D5 can group by route.
- **FR-006**: D5 MUST show Web Vitals p75 by route, JS error rate, top errors with route, client TTFT and stream aborts, reading the logs backend directly.
- **FR-007**: One script MUST seed the secret shapes through the build layer, the real backend bootstrap (span attributes, span events, a log record through the logging handler) and the browser receiver, query logs, traces and metrics (labels and values, span attributes and events), and fail on any unmasked seeded value.
- **FR-008**: The secret shapes and the paths MUST each be one table, so adding one is one row.
- **FR-009**: The script's bite MUST be proven: red with one Alloy redaction rule disabled in a copied config, green on the real one.
- **FR-010**: D12 MUST overlay running-version annotations on runtime p95 latency, error ratio and LLM cost per request.
- **FR-011**: D12's table MUST map commit → seat → estimated build cost → runtime deltas, and state its attribution rule and delta definition.
- **FR-012**: Panels with per-interval bars or legend totals MUST use a query window equal to the step (sc-471), checked by a test.

### Key Entities

- **Commit attribution**: commit (7-char sha), seat (board author and seat id), feature key, build-cost estimate (USD, optional).
- **Running version**: the app's `service.version` as seen on its telemetry resource.
- **Seeded secret**: a shape name, a value generated per run, the path it enters by.

## Success Criteria *(mandatory)*

- **SC-001**: A thrown component error appears on D5 with its route within two minutes.
- **SC-002**: The redaction script passes on the real configuration and fails on each mutated one tried.
- **SC-003**: A synthetic regression commit appears in D12's table against its authoring seat with a non-zero runtime delta.
- **SC-004**: The existing frontend and backend test suites stay green.

## Assumptions

- Faro stays lazily loaded (057): the boundary reports through the registered Faro instance and is a no-op when telemetry is off.
- No Loki ruler this sprint: D5 queries the logs backend directly.
- "Stream aborted" means the chat connection closed while a turn was streaming (the app has no stop button).
- Build cost per commit is estimated from the sprint's per-agent usage file (written at wrap-up); without it the cost is empty.
- Runtime delta = a version's mean over the dashboard range minus the mean of all versions over the same range.
- The Postgres log path (058) is not a row in the redaction script's `PATHS`: `observability/test/datastores.sh` already seeds a secret through it and proves it masked (decision on board #67). The script covers the build layer, the backend and the browser receiver.
