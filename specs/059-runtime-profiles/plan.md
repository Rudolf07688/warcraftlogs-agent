# Implementation Plan: Runtime profiles and dashboards

**Branch**: `059-runtime-profiles` | **Date**: 2026-11-05 | **Spec**: [spec.md](spec.md)

## Summary

Four stories in one stream: the 405-to-500 fix in the FastAPI route lookup (done, 67eee52),
PyYAML declared and the board window accepted at 7 days, four new app instruments with their
aliases and D6–D8 panels (service graph, p50/p99, finish reasons, conversation depth,
embedding latency and batch size), and Pyroscope span profiles linked from Tempo.

## Technical Context

**Language/Version**: Python 3.14 (uv), Grafana 13.2.5, Tempo 2.10.10, Mimir 3.2.4, Loki 3.7.9, Alloy 1.21.3
**Primary Dependencies**: OpenTelemetry SDK 1.42.1 / contrib 0.63b1 (pinned by ADK 2.10), google-adk 2.10.0; new: pyroscope-io 1.4.0, pyroscope-otel 1.1.0 (cp314 wheels), pyyaml (declared)
**Storage**: Pyroscope on a named volume `pyroscope-data`; ADK session state gains one key `app_turns`
**Testing**: pytest via `check.py` (in-memory metric reader, `test_telemetry_support.py`); stack scripts under `observability/test/` on compose project `wcl-obs-nils`, 27xxx ports
**Target Platform**: local Docker compose, observability profile
**Constraints**: telemetry and profiling off unless configured (suite unchanged, §14.2); metric labels bounded (§9.3, `METRIC_ATTRIBUTES`); panels with per-interval bars or legend totals use window = step (sc-471)

## Constitution Check

- I reuse: existing View allowlist, `metrics.py` pattern, `runtime.yaml` alias file, `test_telemetry_metrics_dashboards.py` checks, `lib.sh` helpers. Pass.
- II small steps: one commit per story. Pass.
- III simplest: app counter over span parsing; direct SDK → Pyroscope (no Alloy hop); accept the Loki window rather than a per-stream workaround. Pass.
- IV typed boundaries: finish reason mapped to a fixed set; task is a `Literal`. Pass.
- V async: instruments are synchronous O(1) calls; profiler runs in its own native thread. Pass.
- VII shadcn: no UI. VIII Shortcut: stories In Progress, Under Review at hand-off.

## Design

| Piece | Where | How |
|---|---|---|
| 405 fix | `telemetry/setup.py` | wrap the instrumentation's `_get_route_details`, `None` on AttributeError (done) |
| PyYAML | `pyproject.toml`, `uv.lock` | `pyyaml>=6.0.3` |
| Board window | `board-backfill.sh`, README | accept 7 d (decision #19); stack proof in `provisioning.sh` |
| Finish reasons | `telemetry/metrics.py`, `agent_runner.py` | `app.llm.finish_reasons` counter on each non-partial event with a reported reason |
| Conversation depth | `agent_runner.py`, `metrics.py` | `_ensure_session` returns the stored `app_turns`; `run_async(state_delta={"app_turns": n+1})`; histogram at turn end, chat only |
| Embeddings | `kb/embedder.py`, `metrics.py` | duration + batch size per `embed_texts` request |
| Allowlist | `setup.py` | `app.llm.finish_reason`, `app.embedding.task` |
| Aliases | `rules/anonymous/runtime.yaml` | `app:http_latency:p50`, `app:http_latency:p99`, `genai:finish_reasons:rate5m`, `genai:turns_per_conversation:p50/p95`, `rag:embedding_latency:p95`, `rag:embedding_batch_size:avg5m` |
| Panels | `api-red.json`, `app-api-llm.json`, `rag.json` | D6 service graph (Tempo serviceMap) + p50/p99; D7 finish reasons + depth; D8 embedding latency + batch size |
| Datasources | `datasources.yaml` | Tempo `serviceMap` (mimir), `tracesToProfiles` (pyroscope); new Pyroscope datasource |
| Profiling | `telemetry/config.py`, `setup.py`, compose | `PYROSCOPE_SERVER_ADDRESS`; `pyroscope.configure` + `PyroscopeSpanProcessor` in `install()` |
| Stack proof | `observability/test/provisioning.sh` | service graph edges, profiled span flame graph, board window |

## Project Structure

Only the files in the brief's footprint; see the table above. No migration, no frontend.

## Complexity Tracking

None.
