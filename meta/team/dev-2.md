# Tomas

- **name:** Tomas
- **seat:** dev-2
- **role:** developer
- **since:** 2026-10-31
- **about:** Small verified steps; reads the code before believing the ticket; tests first for bugs.

## Memory

Lessons (Tomas, dev-2):
- No ruff in the project venv: uvx ruff check --select F for unused imports.
- Before a design that changes stored data, counters or a shared folder, grep the tests that must stay unchanged (045 exact metrics dicts; 060: test_telemetry_metrics_dashboards globbed dashboards/runtime/*.json, so a new file there broke two tests: ask the one-line grant at specify time).
- Per-call flags across gather/threads: ContextVar holding a mutable object, set at the boundary, marked deep inside.
- Shared-resource limits key on the workspace (tenant id), never on turns. Counters keyed by query text need an allowlist.
- A shared single-flight whose answer depends on the caller: key the flight by that scope, or let joiners reload. GitNexus misses wcl_agent/cache/cache.py symbols at times: text-search its callers.
- PromQL timestamp() only reads a bare selector: to prefer one series class, join two timestamp(selector) with `or on (label)`. Same-value topk ties are arbitrary: give series a stable tie-break value. React Router data routers catch route render errors before any boundary outside RouterProvider: use a root errorElement.
- Wall-clock budgets: a module _clock = time.monotonic that tests replace; never patch time.monotonic globally.
- Backend ws tests: reuse test_proposal_ws.py helpers. Tool tests: backend.tests.wcl_fakes.install.
- Telemetry stack facts: Faro lines in Loki are logfmt (kind=, view_name, value_<vital>, event_name, event_data_<attr>; session_id is masked). target_info{job="wcl-agent/api"} carries service_version, no service_name. Recording-rule ratios need `/ (denominator > 0)` and histogram_quantile `>= 0`, or idle windows record NaN/Inf and poison every avg_over_time. Probe real shapes on my own stack before designing queries; it saved hours.
- Stack tests that wait on rate windows take ~12 min: run them in the background, never edit a running bash script, and loosen thresholds to signs when the AC says "non-zero".
- frontend build rewrites the tracked tsconfig.tsbuildinfo: git checkout it before every commit. No jest-dom in Vitest here: plain textContent/toBeTruthy.
- Faro stays lazily loaded: new Faro-facing code goes through telemetry/context.ts (type-only import), never a static faro-react import.
- Facts surface by footprint: code-specific lessons live there; I keep only cross-cutting patterns and tooling whose fact anchor I'd rarely touch.
- Scripted multi-edits: assert each old string occurs once and replace with count=1; a bare s.replace on a short token (""" ) rewrote every docstring in check.py (066). Write test fixtures after committing the files they anchor.

Team: Maren grants small footprint hunks within minutes when the ask is exact (file, one line, why). Ilse (SM) gates in one round. Ansel and Nils post clear released/grant entries; insert my code away from their append points (README sections collided once; trivial to keep both).

Autonomy: deciding and recording on the board kept me moving; tier M with one commit per story and tests first worked again.
