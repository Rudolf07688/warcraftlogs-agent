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
- stream_response serves chat AND greeting/guide jobs/evals: chat-only behaviour keys on user_id != USER_ID. Tell ws.py about an outcome with a flag on the record, never by matching text.
- agent_runner tests use SimpleNamespace events and fake runners: getattr everything, add run_async kwargs only where needed.
- Uploader text into the model: report_tools.neutralise then caps; sanitise AFTER projecting.
- Importing backend.app.config loads ADK and fastapi: the telemetry bootstrap reads os.environ itself.
- wcl_agent never imports backend: its OTel instruments live in wcl_agent.
- OTel in tests: global providers set once per process; shared provider with swappable processors (test_telemetry_support._SPANS.target). Global patches (instrument()): fresh interpreter; test_telemetry_bootstrap PROBE is the real app bootstrap.
- Monkeypatch-order bugs (wrapt wraps vs `from x import f` bindings): a module-top import can silently fix them, so the fix line won't bite. Import after the patch, then mutate.
- Alloy spanmetrics with resource_metrics_key_attributes keeps the FIRST span's whole resource (stale service.version on target_info). Reproduce Alloy behaviour on my stack with raw OTLP JSON before blaming the app.
- Span names: setup._route_details gives the template at span start (no rename hook).
- Mimir keeps OTLP names without unit/_total suffixes; histograms native. Grafana features hardcoding Tempo names (service map _seconds_bucket/_sum) need copy rules.
- Grafana's Tempo serviceMap runs in the browser: test its Prometheus queries. Pyroscope 2.x: -architecture.storage=v2.
- Defense in depth hides bites: test each layer alone.
- Regexes over untrusted text: bound every repeat, cap length first.
- Dashboards: count over a range = round(increase(raw[$__range])); ratios min 0/max 1; bars or legend totals: window = step.
- Eval/seed tools must refuse the app's DATABASE_URL.

Process lessons:
- Run detect-changes BEFORE each commit. zsh: wrap the gitnexus CLI in a function.
- uv in agent shells: env -u VIRTUAL_ENV for lock/sync.
- Stack scripts: lib.sh needs bash; set ALLOY_FARO_PORT and PYROSCOPE_PORT too (27347/27040) or alloy fails on 12347; KEEP=1 stack by hand before a full rerun.
- mutate.py prints its verdict BEFORE the "restored" line: grep BITES, never tail -2.
- A fix that changes behaviour my earlier test pins: edit that test under a board decision.
- A pre-existing flake in someone's file: post it, let the owner fix it.
- Footprint gaps: ask early with the proven root cause and the exact change; Maren grants within minutes.
- Cross-owner fixes: check the other dev's merged selector against my change (absent label matches !="x").
- Ilse (SM) gates in one round. Ansel (dev-1) posts contract details unasked. Tomas (dev-2) works fast, posts plans up front. Maren (PO) reviews security-core diffs herself.
- An independent review still finds Lows mine missed.
