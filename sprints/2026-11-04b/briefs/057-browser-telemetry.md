# Brief 057: browser telemetry (Faro and one trace from click to Postgres)

- **Feature / branch:** 057, `057-browser-telemetry`
- **Tier:** M (one Spec Kit pass: specify → plan → tasks → implement, no gates; answer your own clarify questions and record them on the board)
- **Seat:** `dev-2` (Tomas). Parallel developers: Ansel (dev-1) on 055 build telemetry (owns most of Alloy and compose), Nils (dev-3) on 056 runtime metrics (owns `telemetry/setup.py`). Read the board's `contract:*` and `owner:*` keys first: they bind you.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-c` (detached at the base). Base ref: sprint branch tip `sprint-2026-11-04b` = `3262948`. Create your branch there.
- **Security-core: yes.** Browser-controlled values (trace context, Faro session id) reach backend spans, and the Faro receiver accepts ingest from the browser. A qa-security review runs at your hand-off.
- **Migration:** none.
- **Read first:** `specs/telemetry_spec.md` §4, §6.6, §7.1, §9, §10. The stories below win where they differ.

## Stories, in this order (AC verbatim from Shortcut)

### Faro SDK in the frontend and Alloy faro receiver (sc-414, 3)
- `@grafana/faro-react` + `@grafana/faro-web-tracing` init in `frontend/src/telemetry/`, router wrapped; off when no endpoint is configured.
- Alloy `faro.receiver` with API key, CORS limited to the app origin, per-app rate limit.
- A page load shows Web Vitals in Loki; `npm test` is green.
- Pseudonymous user id hash only, no email.

PO notes: pin exact package versions; verify the faro.receiver arguments against the pinned Alloy image's docs (`grafana/alloy:v1.21.3` in compose). Faro's outputs must pass the redaction chain: your section at the end of `config.alloy` holds `faro.receiver` plus its own `otelcol.receiver.loki "faro"` bridge into `otelcol.processor.memory_limiter.default.input`; traces go to that same input. Edit nothing above your section (contract:alloy-config). The API key in the browser bundle is not a secret; the rate limit and CORS are the protection, so make them real. Config via `VITE_FARO_*` env (compose frontend environment hunk is yours, contract:compose); unset means Faro never initialises.

### One trace from browser click to Postgres (sc-415, 3)
Acceptance (as changed by the PO on the ticket, 2026-11-04):
- REST calls: Faro propagates `traceparent` to the API (same origin through the Vite proxy), and middleware copies `x-faro-session-id` to the span attribute `session.id`.
- Chat: the frontend opens a span when the user sends and puts its `traceparent` and the Faro session id into the chat message; the backend validates both (W3C format, bounded length) and parents the turn's root span ("chat turn") on that context, setting `session.id`. Invalid or missing values fall back to a fresh root trace.
- One chat send is one trace from the click to Postgres.
- `session.id` never becomes a metric label or spanmetrics dimension.

PO notes: chat goes over the WebSocket `/ws/chat` (`frontend/src/api/wsClient.ts` → `backend/app/api/ws.py`, turn starts around line 581 with `chat_turn_span()`), and `chat_turn_span` in `backend/app/telemetry/__init__.py` starts a fresh root on purpose (`context=Context()`). A browser WebSocket can't send custom headers, which is why the context travels in the message. Parse with the OTel W3C propagator rather than a hand-rolled regex, put the validation in a new `backend/app/telemetry/browser.py` (one definition used by both the middleware and `ws.py`), and register the middleware in `backend/app/main.py` (one hunk). Telemetry off must leave behaviour unchanged.

**Test the edge cases first** (before the happy path): missing fields, malformed or oversized traceparent, all-zero trace id, unsampled flag, a session id with control characters or 10 kB of text, an old frontend that sends no fields, telemetry off. Each must yield a fresh root trace or a dropped attribute, never an error to the user and never an unbounded attribute.

## File footprint (stay inside it; board `owner:stream-c` plus the shared keys)
- `frontend/**` (including `package.json`, `package-lock.json`)
- `backend/app/telemetry/__init__.py`, `backend/app/telemetry/browser.py` (new), `backend/app/api/ws.py`, `backend/app/main.py` (the middleware hunk only)
- `backend/tests/test_telemetry_trace.py`, new `backend/tests/test_telemetry_browser*.py`
- `observability/alloy/config.alloy`: one new Faro section at the end only; `docker-compose.yml`: the alloy Faro port line and the frontend service environment only; `observability/test/faro*` (new); a Faro section appended to `observability/README.md`
- `specs/057-browser-telemetry/**`
- Nothing else (not `telemetry/setup.py`, which is Nils's). Need something: ask on the board with key `owner:<path>`.

## Docker (explicit grant; overrides the developer file's "no docker compose")
- Only through `observability/test` scripts or `docker compose -p wcl-obs-tomas --profile observability ...`, observability services only, on 26xxx host ports (contract:test-stacks; `ALLOY_FARO_PORT` too). Never touch the `warcraftlogs-agent` project: it is live and observes this session. `down -v` after each run and before hand-off.
- The Faro proof (a synthetic Faro payload accepted from the allowed origin, rejected from another origin, rate-limited, arriving in Loki with a seeded secret masked) is a script `observability/test/faro.sh` that team-lead can re-run.

## Tests and proof
- `check.py run --as tomas` on your committed tree (receipt matters); `cd frontend && npm run build && npm test` (Vitest picks up only `src/**/*.test.tsx`).
- Backend: in-memory span exporter tests that a valid message context parents "chat turn" (same trace id), and the edge cases above.
- Frontend: Faro off without config; the send path puts traceparent and session id in the message.
- Live checks (team-lead runs them on the merged tip with a headless browser): post each as a board `question` with key `live-check:057` and exact steps (page load → Web Vitals in Loki; one chat send → one trace from the click span through "chat turn" to a Postgres span in Tempo).

## Hand-off
Stories to Under Review, a board `handoff`, and your final result: branch, commits, files, the `check.py` RESULT and RECEIPT lines, `npm` results, risks, and an AC-by-AC mapping. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
