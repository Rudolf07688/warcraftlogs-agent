# Implementation Plan: Runtime metrics (ADK metrics, app metrics, D6–D8)

**Branch**: `056-runtime-metrics` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

## Summary

ADK already emits the core GenAI metrics; 411 pins versions and proves the series and labels through the production View. 412 adds four app instruments (one cache counter in the standalone `wcl_agent` cache, KB and TTFT instruments in `backend/app/telemetry/metrics.py`) on the OTel metrics API (no-op without a provider) and allowlists their namespaced attribute keys. 413 adds `observability/mimir/rules/anonymous/runtime.yaml` (four aliases, linted with a pinned mimirtool image) and three dashboards over aliases (D7 evolves `app-api-llm.json`, same uid).

## Technical Context

**Language/Version**: Python 3.14; ADK 2.10.0; OTel SDK/API 1.42.1, contrib 0.63b1
**Primary Dependencies**: opentelemetry-api metrics (proxy meter), opentelemetry-sdk (tests: InMemoryMetricReader)
**Storage**: Mimir (native histograms from exponential OTLP histograms); no app DB change, no migration
**Testing**: pytest, in-memory metric reader behind `setup.meter_provider` (production View); mutate.py for label hygiene
**Target Platform**: API process (docker compose stack, local)
**Constraints**: telemetry off = no-op; labels bounded enums, never ids or `session.id`; no compose/Alloy/mimir.yaml edits
**Scale/Scope**: ~15x3 cache series, ≤16 KB series, models x agents for TTFT

## Constitution Check

- I Reuse: ADK metrics reused as-is; cache metric hangs off the existing `_record`; production View/allowlist reused in tests. PASS
- II Small steps: 411 → 412 → 413, each verified. PASS
- III Simplicity: OTel API only, no wrapper layer, no new service. PASS
- IV Typed boundaries: label values come from existing enums/Literals (CacheFamily, Kind, result mode). PASS
- V Async: recording is synchronous in-memory aggregation, no I/O on the request path. PASS
- VI GitNexus: impact run (risk:056 notice). PASS
- VII shadcn: no UI. N/A. VIII Shortcut: stories In Progress. PASS

## Project Structure

```text
backend/app/telemetry/setup.py        # METRIC_ATTRIBUTES += app.cache.*, app.rag.*
backend/app/telemetry/metrics.py      # new: KB retrieval + TTFT instruments, record helpers
wcl_agent/cache/cache.py              # app.cache.requests counter from _record
backend/app/kb/search.py              # record retrieval metrics at the end of search()
backend/app/agent_runner.py           # TTFT at the first model text token
backend/tests/test_telemetry_metrics.py  # new: in-memory reader tests (411 + 412)
observability/mimir/rules/anonymous/runtime.yaml
observability/grafana/dashboards/runtime/{app-api-llm.json (D7), api-red.json (D6), rag.json (D8)}
pyproject.toml, uv.lock               # google-adk==2.10.0, exporter ==1.42.1
```

## Phase 0/1

See [research.md](research.md), [data-model.md](data-model.md) (instruments, attributes, aliases), [quickstart.md](quickstart.md).
