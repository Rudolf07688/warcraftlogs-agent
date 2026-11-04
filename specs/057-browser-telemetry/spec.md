# Feature Specification: Browser telemetry (Faro) and one trace from click to Postgres

**Feature Branch**: `057-browser-telemetry`
**Created**: 2026-11-04
**Status**: Draft
**Input**: Shortcut stories sc-414 (Faro SDK and Alloy receiver) and sc-415 (one trace from
browser click to Postgres), epic 396 "Telemetry 2"; design reference `specs/telemetry_spec.md`
§4, §6.6, §7.1, §9, §10. Security-core: browser-controlled values reach backend spans, and the
receiver takes ingest from the browser.

## Clarifications

### Session 2026-11-04

- Q: Honour an unsampled (`-00`) browser context? -> A: No: the turn starts a fresh root. The backend decides its own sampling; Faro's `omitTraceContextForUnsampledSessions` is on, so the browser omits it for unsampled sessions too.
- Q: Which session ids are accepted? -> A: 1 to 64 characters of `[A-Za-z0-9._:-]`; anything else is dropped (the turn still runs). Faro ids are about 10 alphanumerics.
- Q: Names in the chat message? -> A: `traceparent` and `faro_session_id`, read from the raw frame in `ws.py`. `ChatTurn` (schemas.py, not in the footprint) ignores extra fields, so old and new clients both validate.
- Q: Where do the receiver's origin and key live? -> A: Literals in the Faro section of `config.alloy` (Alloy gets no env from the compose hunks 057 owns); the browser key is public by design.
- Q: Baggage for `session.id` (spec 6.6)? -> A: Not now: the story's AC names only the span attribute; nothing downstream reads baggage.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The browser reports page health when configured (Priority: P1, sc-414)

The owner opens the app with the observability stack running and finds the page's Web Vitals,
errors and route changes in Loki, labelled as the web app. Without a Faro endpoint configured
the app behaves exactly as before and loads no telemetry code paths.

**Independent Test**: build the frontend with and without `VITE_FARO_URL`; check that Faro
initialises only with it. Post a synthetic Faro payload to the receiver (`observability/test/faro.sh`).

**Acceptance Scenarios**:

1. **Given** no Faro endpoint, **When** the app starts, **Then** Faro never initialises and no request goes to a collector.
2. **Given** an endpoint and key, **When** the page loads and the router navigates, **Then** Web Vitals and route-change events are sent.
3. **Given** a signed-in user, **When** Faro reports, **Then** the user is identified only by a one-way pseudonymous hash, never an email or name.
4. **Given** the receiver, **When** a payload arrives from the app origin with the key, **Then** it is accepted and its logs reach Loki **after** the redaction chain (a seeded secret arrives masked).
5. **Given** the receiver, **When** a payload arrives from another origin, or without the key, or faster than the rate limit, **Then** it is refused.

### User Story 2 - One chat send is one trace (Priority: P1, sc-415)

The owner sends a chat message and follows one trace from the click through the backend's
"chat turn" and the agent's spans to the Postgres statements, tagged with the browser session.
REST calls from the page join their browser trace the same way.

**Independent Test**: backend tests with an in-memory span exporter for the chat path and for
a REST call; frontend tests that the send path writes the context into the message.

**Acceptance Scenarios**:

1. **Given** Faro is on, **When** the user sends a message, **Then** a client span opens and the message carries its W3C `traceparent` and the Faro session id.
2. **Given** a valid `traceparent` in the message, **When** the turn starts, **Then** "chat turn" is a child of that span (same trace id) and carries `session.id`.
3. **Given** a REST call with `traceparent` and `x-faro-session-id`, **When** it is served, **Then** the server span joins the browser trace and carries `session.id`.
4. **Given** missing, malformed, oversized, all-zero, unsampled or control-character values, or an old frontend that sends nothing, **When** a turn or request arrives, **Then** the turn is a fresh root trace (or the attribute is dropped), the user sees no error, and no attribute is unbounded.
5. **Given** telemetry off in the backend, **When** the same messages arrive, **Then** behaviour is unchanged.
6. **Given** any signal, **Then** `session.id` is never a metric label or span-metrics dimension.

## Requirements *(mandatory)*

- **FR-001**: Faro initialises only when `VITE_FARO_URL` is set; the router is wrapped for route events.
- **FR-002**: The browser user id is a one-way hash of the account id; no email or name leaves the browser.
- **FR-003**: Alloy runs a `faro.receiver` with an API key, CORS limited to the app origin, and a rate limit. Its logs enter the pipeline at the memory limiter through their own bridge, its traces at the same input, so both pass the redaction chain; nothing goes to Loki directly.
- **FR-004**: Compose publishes the receiver port on loopback only and gives the frontend service its `VITE_FARO_*` settings.
- **FR-005**: The chat message carries optional `traceparent` and `faro_session_id`; old clients omit them.
- **FR-006**: One validation module (`backend/app/telemetry/browser.py`) turns those values into a parent context and a session id, used by both the WebSocket path and the REST middleware. Trace context is parsed with the OTel W3C propagator after a length bound; an invalid, all-zero or unsampled context yields none. A session id is accepted only as a short token of safe characters, else dropped.
- **FR-007**: "chat turn" is parented on the validated context and sets `session.id`; without one it starts a fresh root exactly as before.
- **FR-008**: A middleware copies `x-faro-session-id` (validated) to `session.id` on the current server span; with telemetry off it does nothing.
- **FR-009**: `session.id` is span-only (board contract:session-id).
- **FR-010**: `observability/test/faro.sh` proves accept / reject-origin / reject-key / rate limit / Loki arrival with a masked seeded secret.

## Assumptions

- The API key in the browser bundle is not a secret; CORS and the rate limit are the protection.
- The app origin is `http://localhost:5173` (the Vite dev server); the receiver config names it.
- Unsampled browser context starts a fresh backend root: the backend decides its own sampling.

## Success Criteria

- **SC-001**: With the stack up, a page load shows Web Vitals in Loki.
- **SC-002**: One chat send is one trace in Tempo from the click span through "chat turn" to a Postgres span.
- **SC-003**: Every edge input in FR-006 produces a fresh root or a dropped attribute and never an error.
- **SC-004**: `npm test` and `check.py run` are green; `faro.sh` passes.
