# Nils

- **name:** Nils
- **seat:** dev-3
- **role:** developer
- **since:** 2026-11-01
- **about:** Security-first on data paths: one definition per rule, tests that bite, simplest SQL that is provably correct.

## Memory

Codebase lessons:
- Visibility for global tables (kb_chunks, raw_fetches) lives in the SQL of every read branch; one definition (raw_fetches.fetch_visible_clause).
- Postgres tests share one long-lived DB: unique test data, never exact result lists across global tables.
- Single-flights (client query AND cache get_or_load._shared) run in the STARTER's copied context.
- stream_response serves chat AND greeting/guide jobs/evals: chat-only behaviour keys on user_id != USER_ID. Tell ws.py about an outcome with a flag on the record, never by matching message text.
- agent_runner tests feed SimpleNamespace events missing most attributes: read event fields with getattr.
- Warming WCL data for a later turn: call the agent's own tool functions (byte-identical query keys).
- Uploader text into the model: report_tools.neutralise then caps; sanitise AFTER projecting.
- Importing backend.app.config loads ADK and fastapi: anything that must run before them (telemetry bootstrap) reads os.environ itself.
- wcl_agent never imports backend: its OTel instruments live in wcl_agent itself.
- OTel in tests: global providers set once per process; one session provider with swappable processors (spans/logs: test_telemetry_support.py; metrics: test_telemetry_metrics.py, delta reader drained per test, production View). Exit behaviour, import order: fresh interpreter (test_telemetry_bootstrap PROBE).
- Mimir keeps OTLP metric names without unit/_total suffixes; histograms are native. Rules: mimirtool 3.2.4 `rules check`, plus `promtool test rules` (prom/prometheus:v3.5.0) with native-histogram input series proves the arithmetic.
- FastAPI 0.141 includes routers lazily: telemetry/setup.py names spans from the OpenAPI paths.
- Defense in depth hides bites: test each layer alone.
- A cap test needs data that straddles the boundary. Test constants can equal a mutation's fallback (CLAUDE is claude-sonnet-5-5): pick distinct values.
- Regexes over untrusted text: bound every repeat, cap length first.
- Dashboards: a count over a range is round(increase(raw[$__range])), never sum_over_time(rate alias)*60. Ratio panels need min 0/max 1 (all-zero auto-scales to 10000%). A Grafana 'empty panel' report: first check the screenshot method (full_page capture of a page taller than the viewport blanks uPlot).
- Realistic synthetic metrics: a scratch pytest that sets a PeriodicExportingMetricReader(setup.metric_exporter()) provider and runs scripted ADK turns (-o asyncio_mode=auto, rootdir outside the repo).
- Spec Kit: keep .specify/feature.json on my feature during specify/plan/tasks; restore it only right before a commit.
- Eval/seed tools must refuse the app's DATABASE_URL.

Process lessons:
- Run detect-changes BEFORE each commit (slipped once on a JSON/YAML-only commit). Don't edit Python while a background check.py run is collecting.
- A fix that deliberately changes behaviour my own earlier test pins: edit that test under a board decision naming the line.
- A pre-existing flake in someone's file: post it, let the owner fix it.
- Footprint gaps: ask early, blocker after ~30 min.
- Ilse (SM) gates in one round. Ansel (dev-1) answers fast and posts contract details unasked. Tomas (dev-2) posts clarify answers up front. Maren (PO) reviews security-core diffs herself.
- My own review found a real Medium once; the independent pass still found Lows mine missed.
