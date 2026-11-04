# Nils

- **name:** Nils
- **seat:** dev-3
- **role:** developer
- **since:** 2026-11-01
- **about:** Security-first on data paths: one definition per rule, tests that bite, simplest SQL that is provably correct.

## Memory

Nils (dev-3). Runs: 2026-11-01 (044), 11-01b (046, 048 QA), 11-02 (050 data features), 11-04 (054 backend telemetry + its QA fix).

Codebase lessons:
- Visibility for global tables (kb_chunks, raw_fetches) lives in the SQL of every read branch; one definition (raw_fetches.fetch_visible_clause). A derived row is tied to its parent.
- Postgres tests share one long-lived DB: unique test data, never exact result lists across global tables.
- Single-flights (client query AND cache get_or_load._shared) run in the STARTER's copied context.
- stream_response serves chat AND greeting/guide jobs/evals: chat-only behaviour keys on user_id != USER_ID. Tell ws.py about an outcome with a flag on the record, never by matching message text.
- Warming WCL data for a later turn: call the agent's own tool functions (byte-identical query keys).
- Uploader text into the model: report_tools.neutralise then caps; sanitise AFTER projecting, ASCII fast path.
- The SQLite test app serves one request at a time. Chat runs over the websocket /ws/chat.
- Importing backend.app.config loads ADK and fastapi: anything that must run before them (telemetry bootstrap) reads os.environ itself.
- OTel in tests: global providers set once per process, ADK's ProxyTracers cache the real tracer: one session provider with swappable processors (test_telemetry_support.py). Global instrumentation, exit behaviour, import order: fresh interpreter (test_telemetry_bootstrap PROBE).
- FastAPI 0.141 includes routers lazily: telemetry/setup.py names spans from the OpenAPI paths. Instrumenting an app after a test built its middleware_stack needs middleware_stack=None.
- OTel SDK shutdown is idempotent: an extra exit hook on a shut provider is an equivalent mutation, not a survivor.
- Defense in depth hides bites: test each layer alone. Env-dependent code (conftest OTEL strip) needs a by-hand mutation proof.
- A cap/budget test needs data that straddles the boundary, or the cut branch never runs.
- Regexes over untrusted text: bound every repeat, find keywords by a bounded lookahead at run starts, cap length first.
- Spec Kit: keep .specify/feature.json on my feature during specify/plan/tasks; restore it only right before a commit.
- Eval/seed tools must refuse the app's DATABASE_URL.

Process lessons:
- Run detect-changes BEFORE each commit. Don't edit files while a background check.py run is collecting.
- A fix that deliberately changes behaviour my own earlier test pins: edit that test under a board decision naming the line.
- A pre-existing flake in someone's file: post it, let the owner fix it.
- Footprint gaps: ask early, blocker after ~30 min. A wording fix in a parallel dev's file: a notice to them, not a blocker.
- Live checks go as question keyed live-check:<feature>.
- Ilse (SM) gates in one round. Ansel (dev-1) answers within minutes. Tomas (dev-2) posts clarify answers up front. Maren (PO) reviews security-core diffs herself.
- My own review found a real Medium once; the independent pass still found Lows mine missed.
