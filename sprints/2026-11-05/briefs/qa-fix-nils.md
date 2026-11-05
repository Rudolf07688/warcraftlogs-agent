# Fix brief (tier S): 059 sweep + live-pass fixes, Nils

- **Seat:** `dev-3` (Nils). Parallel fixers: Ansel (dev-1, 058 fixes), Tomas (dev-2, 060 fixes). Board keys bind you.
- **Tier:** S (short plan, then implement; no Spec Kit). Branch `059-fix` from the sprint tip `sprint-2026-11-05` = `fcef188`, in worktree `/home/rudolf/dev/wcl-worktrees/dev-b` (check out the new branch there).
- **Security-core:** yes for item 2 (profile labels bypass redaction). Reports: `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-05-sweep/{performance,security,bugs}.md` and board #75, #78.
- **Migration:** none.

## Fix these (each with a test that bites, `mutate.py`)
1. **Critical, Pyroscope tag leak (performance.md).** `SQLAlchemyInstrumentor` attaches two EngineTracers to every async engine; one span per statement is never ended, and outside a request it is a root span, so `PyroscopeSpanProcessor` adds thread tags it never removes (profiler CPU grows until restart). Fix the double tracer itself (backlog sc-474, now in this round: one tracer per engine, one span and one traceparent per statement, pool events once). The whole of `backend/app/telemetry/setup.py` is yours this round, including the SQLAlchemy line; keep Ansel's commenter options exactly.
2. **Medium x2, profile labels (security.md).** The processor reads `span_name` at span start, before the route renaming, so Pyroscope labels carry raw paths with ids and client text, and tags are removed under the renamed name, so stale tags pile up. Tag only what is bounded (the route template, or the server root span's final name) and make add/remove use the same key. Prove: a request to `/api/conversations/<id>` leaves no id in any profile label and no tag left behind.
3. **Low, profiler always on (performance.md, security.md).** `docker-compose.yml` sets `PYROSCOPE_SERVER_ADDRESS` on the backend unconditionally; profiling must be off unless the observability profile runs (e.g. default empty, set by an opt-in env var documented in the README). You own only the backend env lines in compose.
4. **Live FAIL #75, two target_info series for one process** (`service_version=fcef188` and `unknown`). Find the second Resource (a provider, the profiler or a meter built before config reads `WCL_GIT_SHA`) and make one process export one version. Test: every provider's resource carries the configured version.
5. **Live FAIL #78, D8 blank when embeddings fail.** Record failed provider requests too (bounded `error.type`), so D8 shows an outage; update the D8 panel if it needs the label. The timeout itself (sc-428) is out of scope.
6. **Low, service map node latency (bugs.md).** Copy `_seconds_sum` (and count if needed) under Grafana's expected name in `runtime.yaml`, like the bucket copy.

## Footprint
`backend/app/telemetry/**`, `backend/app/kb/embedder.py`, `docker-compose.yml` (backend env lines only), `observability/mimir/rules/anonymous/runtime.yaml`, `observability/grafana/dashboards/runtime/rag.json`, `backend/tests/test_telemetry_*.py` (not the `DASHBOARD_FILES` line), `observability/README.md` (059 section), `observability/test/provisioning.sh`, `specs/059-runtime-profiles/**`. Nothing else.

## Proof and hand-off
`check.py run --as nils` on the committed tree (receipt). Stack runs only as before (`wcl-obs-nils`, 27xxx, `down -v`). Board `handoff` + final result: branch, commits, RESULT/RECEIPT lines, finding-by-finding mapping. Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
