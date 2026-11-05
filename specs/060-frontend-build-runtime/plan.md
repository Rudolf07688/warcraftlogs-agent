# Implementation Plan: Frontend dashboard, build-vs-runtime dashboard and end-to-end redaction tests

**Branch**: `060-frontend-build-runtime` | **Date**: 2026-11-05 | **Spec**: [spec.md](spec.md)

## Summary

Three slices, in brief order: (1) error boundaries and chat events in the React app plus D5 on
Loki (sc-416); (2) one end-to-end redaction script over every telemetry path, proven red on a
mutated Alloy copy (sc-423); (3) D12 with cross-layer recording rules and a small board/usage
helper that pushes commit → seat → cost facts to Mimir (sc-422).

## Technical Context

**Language/Version**: TypeScript 5 / React 19 (frontend), Python 3.14 (helpers, backend bootstrap), bash
**Primary Dependencies**: `@grafana/faro-react` 2.13 (lazy, already installed), Grafana 13.2, Loki 3.7, Tempo 2.10, Mimir 3.2, Alloy 1.21
**Storage**: none new (Mimir gauges pushed over OTLP like `teamstats.py`)
**Testing**: Vitest (`src/**/*.test.tsx`), pytest (`backend/tests/test_telemetry_cross_dashboards.py`), stack scripts under `observability/test/`
**Constraints**: no new packages; Faro stays out of the main bundle; no `config.alloy`/compose/`loki.yaml` changes; stack only as `wcl-obs-tomas` on 26xxx ports
**Scale/Scope**: one app, a handful of commits per sprint (commit labels are low-cardinality)

## Constitution Check

- I Reuse: Faro's error-boundary semantics and view meta, `redaction_check.py` seed shapes, `lib.sh` helpers, `teamstats.py` usage parsing and pricing (imported, not edited), existing RED/cost aliases. PASS
- II Small steps: one story per commit, tests first per slice. PASS
- III Simplest design: no Loki ruler, no new service; one helper script and one rules file. PASS
- IV Typed boundaries: typed event API in `telemetry/chatEvents.ts`; JSON dashboards checked by tests. PASS
- V Async FastAPI: backend app code untouched. PASS
- VII shadcn: the fallback uses the existing `Button` component. PASS

## Design

### sc-416 frontend

- `telemetry/context.ts`: the Faro API pick gains `pushError`, `pushEvent`, `setView`; new
  `reportError(error, context)`, `pushTelemetryEvent(name, attrs)`, `setRoute(template)` /
  `currentRoute()`. All no-ops while Faro is off.
- `telemetry/ErrorBoundary.tsx`: class boundary `TelemetryBoundary {name, fallback?}`; on catch,
  reports `React ErrorBoundary <name>` with the component stack, context `{boundary, route}`;
  renders `PanelFallback` (plain text + Retry that resets the boundary). Never the message.
- `telemetry/chatEvents.ts`: `startTurnEvents(model)` returns a per-turn object
  (`completed()`, `failed()`, `aborted(reason)`); module pointer to the live turn for
  `firstTokenRendered()`. Each event at most once per turn.
- `api/wsClient.ts`: per-socket turn like the existing `chatSend`: send → start; `done` →
  completed; `error` → failed; `onclose` mid-turn → aborted (`closed` when `close()` was called,
  else `connection_lost`).
- `components/MessageList.tsx` `LiveMessage`: effect on the first non-empty stream text →
  `firstTokenRendered()` (after commit = rendered).
- `telemetry/faro.ts`: `setView({name: route})` at init and on router changes (route template
  from `matchRoutes`).
- `main.tsx` shell boundary around `RouterProvider`; `App.tsx` boundaries around Sidebar,
  MessageList, Composer.
- D5 `dashboards/runtime/frontend.json` (uid `wcl-d5-frontend`), Loki only, logfmt lines
  (`kind=measurement|exception|event`, `view_name`, `value_<vital>`, `event_name`, `event_data_*`).

### sc-423 redaction e2e

- `observability/test/redaction_e2e.py`: `SHAPES` (name → generator, from
  `redaction_check.seed`) and `PATHS` (name → sender). Paths: build layer (OTLP, resource
  `service.name=claude-code`, its event names, span event `tool.output`, metric datapoint
  attribute), backend (subprocess of `backend.app.telemetry.configure_telemetry` with
  `OTEL_EXPORTER_OTLP_ENDPOINT` at the test Alloy: span attributes, a span event, a log record
  through `otlp_log_handler`, a metric attribute), Faro (receiver payload: log, exception,
  event, measurement context). Queries Loki (streams + structured metadata), Tempo (trace JSON
  incl. events), Mimir (series labels and values, `target_info`). Fails on any raw value.
- The backend path is checked twice: the app-side processor alone would hide an Alloy gap, so
  secrets are also placed where the app-side redactor does not look (resource attribute) —
  whatever the backend emits must arrive masked.
- `redaction-e2e.sh`: fresh stack, run, then a mutated copy (`ALLOY_CONFIG_DIR`, as
  `mutation.sh`) for a few rules, each must go red; the checkout's files are never written.

### sc-422 D12

- `observability/build-runtime/commits.py`: reads board JSONL files (default: `meta/sprints/*/board.jsonl`
  plus the live board dir), `meta/team/*.md` roster, `meta/sprints/*/usage.txt`; pushes
  `build.commit.info{commit,seat,feature}` = 1 and `build.commit.cost_usd{commit,seat,feature}`
  (only when a usage row matches) at the entry's timestamp. `--dry-run` prints the table.
- `observability/mimir/rules/anonymous/cross.yaml`: `cross:running_version:info`,
  `cross:commit_seat:info`, `cross:running_commit:info`, `cross:http_latency:p95`,
  `cross:http_error_ratio:5m`, `cross:llm_cost_per_request:5m`, each also `_by_commit`.
- `dashboards/cross/build-runtime.json` (uid `wcl-d12-build-runtime`): annotation on
  `cross:running_commit:info`, three timeseries by commit, the attribution table (merge of
  instant queries), a text panel stating the rules.
- `observability/test/build-runtime.sh`: pushes two versions' synthetic spans and metrics
  (B slower and erroring), a board naming B's seat, runs `commits.py`, waits for the rules, and
  asserts through Grafana's query API that the table query returns B with the seat and Δ > 0.

### Tests

- Vitest: boundary (fallback without message, one report with route, siblings mounted, retry),
  events (once each, abort only on close mid-turn, StrictMode-safe), view route.
- pytest `test_telemetry_cross_dashboards.py`: uids/folders, D5 Loki-only with logfmt fields
  used, D12 Mimir queries read `cross:*` aliases or the pushed `build_commit_*`, cross.yaml
  rules well-formed, window = step for bars/legend totals, `commits.py` attribution on a
  fixture board.
- Granted one-line change in `test_telemetry_metrics_dashboards.py` (board #17).
