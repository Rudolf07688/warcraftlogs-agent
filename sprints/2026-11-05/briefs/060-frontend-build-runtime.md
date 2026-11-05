# Brief 060: frontend dashboard, build-vs-runtime dashboard and end-to-end redaction tests

- **Feature / branch:** 060, `060-frontend-build-runtime`
- **Tier:** M (one Spec Kit pass: specify → plan → tasks → implement, no gates; answer your own clarify questions and record them on the board)
- **Seat:** `dev-2` (Tomas). Parallel developers: Ansel (dev-1) on 058 data-store telemetry, Nils (dev-3) on 059 runtime profiles and dashboards. Read the board's `contract:*` and `owner:*` keys first: they bind you.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-c` (detached at the base). Base ref: sprint branch tip `sprint-2026-11-05` = `6437aa2`. Create your branch there.
- **Security-core:** no, but sc-423 is the sprint's security proof: a test that passes when it shouldn't is the worst outcome. Mutation-check it (break a redaction rule in a copied Alloy config, the way `observability/test/mutation.sh` does, and show the script goes red).
- **Migration:** none.
- **Read first:** `specs/telemetry_spec.md` §1 (goal 4), §7.1, §8.2 (D5, D12), §10, §12 (P7), §14. The stories below win where they differ.

## Stories, in this order (AC verbatim from Shortcut)

### Frontend dashboard and error boundaries (D5) (sc-416, 2)
- Faro `ErrorBoundary` around the app shell and each chat panel; custom events per §7.1 where the app has them.
- D5 shows Web Vitals p75 by route, JS error rate and top errors, client-side TTFT, stream aborts.
- A thrown component error appears on D5 with its route.

### End-to-end redaction tests: seeded secrets never reach a backend (sc-423, 2)
- One script seeds bearer tokens, JWTs, `sk-`/`AIza` keys and DSNs through the build layer (Claude Code), backend spans, logs and Faro.
- It queries Loki, Tempo and Mimir and fails if any seeded value is found unmasked.
- It runs green against the full stack.

### Build vs runtime dashboard: which commit and seat moved the numbers (D12) (sc-422, 3)
- D12 overlays commit annotations (`service.version`) on runtime p95 latency, error rate and LLM cost per request.
- A table maps commit → authoring seat (from the team board) → estimated build cost → runtime deltas.
- A synthetic regression commit shows up against its authoring seat.

## PO notes (read the code before believing these)
- **Edge cases first.** D5: the error boundary's fallback must not render the error message or stack to the user (it may carry model or WCL text); report to Faro, show a plain fallback with a retry. A boundary per chat panel must not reset the whole app. Custom events: `agent_message_sent`, `agent_first_token_rendered`, `agent_response_completed`, `stream_aborted` exist as moments in the chat flow today; `agent_feedback` does not (no feedback feature, §7.5 reserved): skip it. Event attributes are bounded (no message text, no ids beyond what 057 already sends).
- Faro data lands in Loki; D5 can query Loki directly (LogQL `quantile_over_time` / `rate`) — no Loki ruler this sprint (you don't own `loki.yaml`). Check the label and structured-metadata names 057 actually writes (`frontend/src/telemetry/faro.ts`, the Faro section of `config.alloy`, `observability/test/faro.sh`).
- D12: `service.version` / `vcs.ref.head.revision` are on the backend resource (`backend/app/telemetry/setup.py`, `bin/01_start_app.sh`); check which become Mimir labels (`mimir.yaml` promotion) before designing the annotation. Commit → seat: the board's `merge` and `handoff` entries carry `--ref <sha>` and the author; the board is in Loki (feature 055). Build cost: the Claude Code cost aliases (`cc:cost_usd:*`) over the stream's window, or the sprint's `usage.txt` via a small script like `.claude/team/teamstats.py` (don't edit that file; put a new helper under `observability/build-runtime/`). State your attribution rule plainly on the dashboard; an estimate is fine, a confident wrong number isn't. Cost per request = `genai:cost_usd:rate5m` over the request rate alias.
- **Panels with per-interval bars or legend totals** must use a window equal to the step (sc-471: overlapping `increase` windows on the build dashboards overcount by a third). Your dashboard tests check it.
- sc-423 paths: build layer = OTLP shaped like Claude Code's (resource `service.name=claude-code`, its event names; you can't run a real Claude Code against the test stack), backend = the real `backend/app/telemetry` bootstrap in a subprocess pointed at your test stack's Alloy (span attributes, span events, a log record through the logging handler), Faro = a payload to the receiver. Query every backend, including Mimir labels/values and Tempo span attributes and events, not only Loki. The existing `observability/test/redaction.sh` and `redaction_check.py` cover Alloy alone; extend or reuse them (they're yours this sprint).
- Ansel adds a Postgres slow-query log path in parallel; it isn't in your stack yet. Make the seed list and path list easy to extend (one table), and note it in your hand-off.

## File footprint (stay inside it; board `owner:stream-060`)
- `frontend/src/**` (yours alone this sprint), `frontend/package.json` / `package-lock.json` only if a Faro package is missing (ask first)
- New: `observability/grafana/dashboards/runtime/frontend.json` (uid `wcl-d5-frontend`), `observability/grafana/dashboards/cross/**` (uid `wcl-d12-build-runtime`), `observability/mimir/rules/anonymous/cross.yaml`, `observability/build-runtime/**`, `observability/test/redaction-e2e.sh` (+ helpers), `observability/test/frontend.sh`, `observability/test/build-runtime.sh`, `backend/tests/test_telemetry_cross_dashboards.py`
- `observability/test/redaction.sh`, `observability/test/redaction_check.py`
- `observability/README.md`: one new section `## Frontend, build vs runtime and redaction e2e (060)`.
- `specs/060-frontend-build-runtime/**`
- Nothing else (not `config.alloy`, compose, datasources, `loki.yaml`, `provisioning.sh`, `pyproject.toml`, backend app code). Need something: ask on the board with key `owner:<path>`.

## Docker (explicit grant; overrides the developer file's "no docker compose")
- Only through `observability/test` scripts or `docker compose -p wcl-obs-tomas --profile observability ...`, observability services only, on 26xxx host ports via the env overrides (board `contract:test-stacks`; `ALLOY_FARO_PORT` too). Never touch the `warcraftlogs-agent` project: it is live and observes this session. `down -v` after each run and before hand-off.

## Tests and proof
- `check.py run --as tomas` on your committed tree (receipt matters); `cd frontend && npm run build && npm test` (Vitest picks up only `src/**/*.test.tsx`).
- Frontend: a thrown child inside each boundary reports to Faro with the route and renders the fallback, not the message; the custom events fire once each at the right moment (and `stream_aborted` on a real abort only).
- Scripts assert values, not presence: a synthetic component error appears on D5's top-errors query with its route; D12's table shows the synthetic regression commit against its seat with a non-zero runtime delta; the e2e redaction script is red on the mutated config and green on the real one.
- Live checks (team-lead runs them on the merged tip with a headless browser): post each as a board `question` with key `live-check:060` and exact steps.

## Hand-off
Stories to Under Review, a board `handoff`, and your final result: branch, commits, files, the `check.py` RESULT and RECEIPT lines, the frontend build/test lines, risks, and an AC-by-AC mapping. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
