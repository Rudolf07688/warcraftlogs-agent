# Sprint 2026-11-05 plan: Telemetry 3 (Maren, PO)

Goal: data stores, profiles and build-to-runtime are visible in Grafana (epic 397, spec §14.3 sprint 3), plus the Telemetry 2 follow-ups and one QA bug in the same files. 26 points, three tier-M streams in parallel. Base `sprint-2026-11-05` = 6437aa2. Iteration 472. Alembic: 0022 (A only).

Drop order if it slips: Pyroscope (B), then local alerts (A), then D9–D11 (A).

## Stream A: 058-datastore-telemetry (Ansel, dev-1, opus high, security-core) 10 pts, worktree dev-a
- Postgres exporter with pg_stat_statements and pgvector queries (sc-417, 3)
  - `pg_stat_statements` enabled; Alloy `prometheus.exporter.postgres` with the non-default collectors from §7.2.
  - Custom queries for vector index size and embedding table rows.
  - Top queries by total time and the knowledge-base index size are visible in Grafana.
- Redis exporter next to the app's cache hit ratio (sc-418, 1)
  - Alloy `prometheus.exporter.redis` reports memory, evictions, keyspace hits/misses, clients and latency.
  - Redis's hit ratio shows next to `app.cache.requests` hit ratio.
- sqlcommenter and slow-query log linked to traces (sc-419, 2)
  - SQLAlchemy sqlcommenter appends `traceparent` to SQL.
  - Postgres logs statements over 250 ms, lock waits and autovacuum, collected through Docker logs into Loki.
  - A slow-query line opens its trace via a Loki derived field.
- Infra and meta-monitoring dashboards D9, D10, D11 (sc-420, 3)
  - cAdvisor container metrics and Alloy/Loki/Tempo/Mimir self-metrics are scraped.
  - D9 (Postgres), D10 (Redis) and D11 (infra and meta) are provisioned; D11 shows Alloy drops and queue, ingest rates and active series against the 50k budget.
- Minimal local alerts: telemetry pipeline drops and daily build spend (sc-424, 1)
  - Grafana-managed alert rules provisioned as code: Alloy exporter failures or dropped spans/logs; estimated Claude Code spend per day above a configurable threshold.
  - Each rule fires on a synthetic trigger.

## Stream B: 059-runtime-profiles (Nils, dev-3, opus medium) 9 pts, worktree dev-b
- Pyroscope span profiles for the backend (sc-421, 3) — cp314 wheel exists (pyroscope-io 1.4.0, pyroscope-otel 1.1.0), so the "no wheel" exit is closed.
  - Pyroscope container in the observability profile; `pyroscope-otel` `PyroscopeSpanProcessor` in the bootstrap.
  - From a slow span, "Profiles for this span" opens a flame graph.
- With telemetry on, a partly matching route returns 500 instead of 405 (sc-461, 2, QA)
  - Handle partial matches (no endpoint) and add a test with telemetry on.
- Runtime dashboards: service graph, finish reasons, conversation depth, embedding latency (sc-462, 3) — feedback ratio dropped (comment on ticket)
  - A Tempo serviceMap datasource over `traces_service_graph_*`, and a service graph panel on D6 (API RED). D6 also gets p50 and p99 latency.
  - D7: finish reasons, conversation depth, ~~feedback ratio~~, once the metrics exist (add them where missing).
  - D8: embedding latency and batch size (pgvector index size belongs to D9 in this epic).
  - Panels query recording-rule aliases.
- Declare PyYAML and widen Loki's accepted sample age for the board backfill (sc-463, 1)
  - Declare PyYAML in `pyproject.toml`.
  - Decide whether to widen the Loki window for the board stream or accept it.

## Stream C: 060-frontend-build-runtime (Tomas, dev-2, opus medium) 7 pts, worktree dev-c
- Frontend dashboard and error boundaries D5 (sc-416, 2)
  - Faro `ErrorBoundary` around the app shell and each chat panel; custom events per §7.1 where the app has them.
  - D5 shows Web Vitals p75 by route, JS error rate and top errors, client-side TTFT, stream aborts.
  - A thrown component error appears on D5 with its route.
- Build vs runtime dashboard D12 (sc-422, 3)
  - D12 overlays commit annotations (`service.version`) on runtime p95 latency, error rate and LLM cost per request.
  - A table maps commit → authoring seat (from the team board) → estimated build cost → runtime deltas.
  - A synthetic regression commit shows up against its authoring seat.
- End-to-end redaction tests (sc-423, 2)
  - One script seeds bearer tokens, JWTs, `sk-`/`AIza` keys and DSNs through the build layer (Claude Code), backend spans, logs and Faro.
  - It queries Loki, Tempo and Mimir and fails if any seeded value is found unmasked.
  - It runs green against the full stack.

## Deferred QA (stay in Backlog)
- sc-471 dashboard overcount (build dashboards, no story touches them; the rule "window = step" goes into every brief so no new panel repeats it).
- sc-459 REST trace context (security, setup.py propagators; 2 pts over budget, local-only app).
- sc-458 browser shares Alloy pipeline (needs a proxy or newer Alloy), sc-460 telemetry details.
