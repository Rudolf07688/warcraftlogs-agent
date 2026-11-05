# Brief 059: runtime profiles and dashboards (Pyroscope, 405 fix, D6–D8 completion, PyYAML + board backfill window)

- **Feature / branch:** 059, `059-runtime-profiles`
- **Tier:** M (one Spec Kit pass: specify → plan → tasks → implement, no gates; answer your own clarify questions and record them on the board)
- **Seat:** `dev-3` (Nils). Parallel developers: Ansel (dev-1) on 058 data-store telemetry, Tomas (dev-2) on 060 frontend, build-vs-runtime and redaction e2e. Read the board's `contract:*` and `owner:*` keys first: they bind you.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b` (detached at the base). Base ref: sprint branch tip `sprint-2026-11-05` = `6437aa2`. Create your branch there.
- **Security-core:** no. Label hygiene stays the risk: bounded enums only, never ids or `session.id`; finish reasons are an enum, conversation depth is a histogram value, never a label.
- **Migration:** none.
- **Read first:** `specs/telemetry_spec.md` §6.3, §6.4, §6.7, §7.5, §8.1, §8.2 (D6–D8), §8.3, §9, §14. The stories below win where they differ.

## Stories, in this order (AC verbatim from Shortcut; Pyroscope is first to drop if the sprint slips, so do it last)

### With telemetry on, a request that only partly matches a route returns 500 instead of 405 (sc-461, 2, QA bug)
From the ticket: with telemetry on, the FastAPI instrumentation (route naming in `backend/app/telemetry/setup.py`, `name_span_by_route`) raises AttributeError on any request that only partly matches a route in an included router: a CORS preflight OPTIONS, or a POST to a GET-only route. A 405 becomes a 500. Reproduced with FastAPI 0.141.1 in a scratch app.
- Handle partial matches (no endpoint) and add a test with telemetry on.
- PO addition: the test asserts both cases (OPTIONS preflight from the dev origin, POST to a GET route) return the same status as with telemetry off, and the span still gets a bounded name.

### Runtime dashboards: service graph panel, finish reasons, conversation depth, feedback, embedding latency (sc-462, 3)
- A Tempo serviceMap datasource over `traces_service_graph_*`, and a service graph panel on D6 (API RED). D6 also gets p50 and p99 latency.
- D7: finish reasons, conversation depth, feedback ratio, once the metrics exist (add them where missing).
- D8: embedding latency and batch size (pgvector index size belongs to D9 in this epic).
- Panels query recording-rule aliases.
- **Changed AC (PO, comment on the ticket):** feedback ratio is out. The app has no feedback feature and §7.5 is reserved. Don't build one.

### Declare PyYAML and widen Loki's accepted sample age for the board backfill (sc-463, 1)
- `observability/pricing/generate.py` and `backend/tests/test_team_pricing.py` use PyYAML, which the project only gets transitively (google-adk, uvicorn[standard]). Declare it in `pyproject.toml`.
- Loki refuses samples older than 7 days (`reject_old_samples`), so `observability/board-backfill.sh` restores only the last week of the team board. Decide whether to widen the window for the board stream or accept it (older sprints live in meta/ exports).
- PO note: the window lives in two places, Loki's limits and Alloy's `log_window` filter (6 days). If you widen it, widen both and keep the content stream's 7-day retention untouched; "accept it, with the reason" is an allowed outcome. Record the choice as a `decision`.

### Pyroscope span profiles for the backend (sc-421, 3)
- Pyroscope container in the observability profile; `pyroscope-otel` `PyroscopeSpanProcessor` in the bootstrap.
- From a slow span, "Profiles for this span" opens a flame graph.
- Allowed outcome: "no Python 3.14 (cp314) wheel for pyroscope-io", with evidence, and the story closes without code.
- PO note: that outcome is closed. PyPI has `pyroscope_io-1.4.0-cp314-cp314-manylinux2014_x86_64` and `pyroscope-otel 1.1.0` (needs `opentelemetry-sdk>=1.27,<2`, compatible with our 1.42.1 pin). Profiling is off unless configured, exactly like the rest of telemetry (the suite runs unchanged, §14.2), and must never start in tests. Pin both versions.

## PO notes (read the code before believing these)
- Finish reasons: ADK's `generate_content` span may already carry `gen_ai.response.finish_reasons`; a spanmetrics dimension (an array attribute!) or an app counter are both fine, pick the one with bounded labels and say why. Conversation depth: turns per conversation at the end of a turn, a histogram recorded where the turn ends (`backend/app/agent_runner.py`). Embedding latency and batch size: where embeddings are computed under `backend/app/kb/`.
- Every metric attribute must be in `METRIC_ATTRIBUTES` (`setup.py`); the View drops the rest.
- **Panels with per-interval bars or legend totals** must use a window equal to the step (sc-471: overlapping `increase` windows on the build dashboards overcount by a third). Your dashboard tests check it for every panel you add or touch.
- Tempo needs `tracesToProfiles` (Pyroscope datasource) and `serviceMap` (Mimir) in its jsonData.

## File footprint (stay inside it; board `owner:stream-059`)
- `backend/app/telemetry/**` (setup.py except the `SQLAlchemyInstrumentor().instrument(...)` line(s), which are Ansel's; metrics.py; config.py; new modules), `backend/app/agent_runner.py`, `backend/app/kb/**`
- `pyproject.toml`, `uv.lock` (yours alone this sprint)
- `docker-compose.yml`: a new `pyroscope` service placed after `grafana`, a `pyroscope-data` volume after `grafana-data`, and env lines on the `backend` service. Ansel owns the `db`, `redis` and `alloy` blocks.
- `observability/alloy/config.alloy`: only the spanmetrics connector and the `log_window` filter blocks. Ansel appends a new section at the end; leave it alone.
- `observability/grafana/provisioning/datasources/datasources.yaml`: the Tempo block and a new Pyroscope datasource. Ansel owns the Loki `derivedFields` list.
- `observability/loki/loki.yaml`, `observability/tempo/tempo.yaml`, `observability/board-backfill.sh`, `observability/test/provisioning.sh`
- `observability/mimir/rules/anonymous/runtime.yaml`, `observability/grafana/dashboards/runtime/{api-red,app-api-llm,rag}.json`
- `backend/tests/test_telemetry_*.py` that exist today, new `backend/tests/test_telemetry_profiles*.py`
- `observability/README.md`: one new section `## Profiles and runtime dashboards (059)` (plus edits to the existing Loki window text if you change it).
- `specs/059-runtime-profiles/**`
- Nothing else (not frontend, not `observability/grafana/dashboards/{build,infra,cross}`, not `runtime/frontend.json`). Need something: ask on the board with key `owner:<path>`.

## Docker (explicit grant; overrides the developer file's "no docker compose")
- Only through `observability/test` scripts or `docker compose -p wcl-obs-nils --profile observability ...`, observability services only, on 27xxx host ports via the env overrides (board `contract:test-stacks`). Never touch the `warcraftlogs-agent` project: it is live and observes this session. `down -v` after each run and before hand-off.

## Tests and proof
- `check.py run --as nils` on your committed tree (receipt matters). In-memory reader tests for each new instrument and for the allowlist; mutation-check the 405 fix and label hygiene with `mutate.py`.
- A stack script proves: the service graph panel's query returns edges; a profiled slow span (a CPU-bound function under a span, run against your test stack) has a profile id and Pyroscope returns its flame graph for that span; the board backfill window as decided (seed a board entry older than 7 days, assert it lands or is dropped as decided).
- Live checks (team-lead runs them on the merged tip): post each as a board `question` with key `live-check:059` and exact steps (one chat turn → finish reason, conversation depth, embedding latency in Mimir; D6 service graph; "Profiles for this span" from a chat turn span).

## Hand-off
Stories to Under Review, a board `handoff`, and your final result: branch, commits, files, the `check.py` RESULT and RECEIPT lines, risks, and an AC-by-AC mapping. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
