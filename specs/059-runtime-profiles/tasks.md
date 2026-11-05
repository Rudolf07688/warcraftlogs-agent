# Tasks: 059 runtime profiles and dashboards

## Phase 1: sc-461 (US1)
- [X] T001 [US1] Reproduce the 405→500 with a scratch app test (AttributeError in `_get_route_details`)
- [X] T002 [US1] Wrap the route lookup in `backend/app/telemetry/setup.py`
- [X] T003 [US1] Test off vs on (preflight, POST to GET-only) + bounded span names in `backend/tests/test_telemetry_trace.py`; mutate.py bites

## Phase 2: sc-463 (US2)
- [X] T004 [US2] Declare `pyyaml` (and the pinned profiler packages) in `pyproject.toml`, `uv lock`
- [X] T005 [US2] Board window decision text in `observability/board-backfill.sh` and README section
- [X] T006 [US2] Stack proof in `observability/test/provisioning.sh`: 8-day-old board entry dropped, fresh one lands

## Phase 3: sc-462 (US3)
- [X] T007 [US3] Instruments in `backend/app/telemetry/metrics.py`; attributes on `METRIC_ATTRIBUTES` in `setup.py`
- [X] T008 [US3] Finish reasons + conversation depth in `backend/app/agent_runner.py`
- [X] T009 [US3] Embedding latency + batch size in `backend/app/kb/embedder.py`
- [X] T010 [US3] In-memory reader tests (`backend/tests/test_telemetry_metrics.py`): values, labels, unknown reason → other, greeting not counted, allowlist; mutate.py on label hygiene
- [X] T011 [US3] Aliases in `observability/mimir/rules/anonymous/runtime.yaml`
- [X] T012 [US3] Panels D6 (service graph, p50/p99), D7 (finish reasons, depth), D8 (embedding latency, batch size)
- [X] T013 [US3] Tempo `serviceMap` in `datasources.yaml`; dashboard tests incl. window = step for bars/legend totals
- [X] T014 [US3] Stack proof: service graph query returns edges

## Phase 4: sc-421 (US4)
- [X] T015 [US4] `PYROSCOPE_SERVER_ADDRESS` in `telemetry/config.py`; `pyroscope.configure` + `PyroscopeSpanProcessor` in `setup.install`
- [X] T016 [US4] Tests: off by default, never configured in the suite, processor wired when set (fake pyroscope) in `backend/tests/test_telemetry_profiles.py`
- [X] T017 [US4] Compose `pyroscope` service + volume + backend env; Pyroscope datasource; Tempo `tracesToProfiles`
- [X] T018 [US4] Stack proof: CPU-bound span → profile id → Pyroscope flame graph for that span

## Phase 5: polish
- [X] T019 README section `## Profiles and runtime dashboards (059)`
- [X] T020 Live-check questions on the board; full `check.py run`; hand-off
