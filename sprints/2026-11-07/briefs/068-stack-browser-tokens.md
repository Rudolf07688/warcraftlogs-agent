# Brief 068-stack-browser-tokens (Ansel, seat dev-1)

- **Feature / branch:** `068-stack-browser-tokens`, tier **S**, opus medium. Not security-core.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-d` (detached at `9ff8602`). Base: `9ff8602`.
- **In parallel:** Vera (065, lists your tools in developer.md from `contract:tool-names`),
  Tomas (066), Nils (067; his `obsq.py` may read your `stack.py` env file).
- **Story:** sc-533 (3). Items 4-5 moved to sc-537 (Nils).

## Footprint (yours alone)

- new `.claude/team/stack.py`, `.claude/team/browse.py`, `.claude/team/tokens.py`
- new `backend/tests/test_team_stack.py`, `test_team_browse.py`, `test_team_tokens.py`
- new fact file for the Grafana plugin source-map recipe (sc-529 item; `facts.py add`)
- `frontend/package.json` + `frontend/package-lock.json`: **only** for one devDependency if
  `browse.py` needs it (e.g. `playwright-core` driving the system `/usr/bin/google-chrome`, no
  browser download). Post a `decision` keyed `scope:068:browser-dep` first. Prefer no dependency.
- Read-only: `observability/test/lib.sh`, `docker-compose.yml`, `frontend/vite.config.ts`,
  `backend/tests/test_064_prompt_budget.py` and the app's prompt/tool-schema assembly.

## Acceptance criteria (verbatim from the story)

1. Stack-up helper that picks free ports and writes the env file (Ansel keeps it by hand).
2. Headless browser on the developer's own port (Tomas: the drop test was only proven in the lead's browser).
3. Offline token counter for a chat request (Vera hand-rolled chars/4).

## Notes from Maren

- `stack.py`: free ports chosen by bind check, a per-developer compose project name, the env file
  written where git never sees it (e.g. under `git rev-parse --git-dir`, so no `.gitignore` edit),
  a `down` that removes what `up` made. Never the owner's compose project, default ports or `.env`;
  fakes only, no credentials. Which services it brings up is your call; say it in `--help`.
- `browse.py`: drives `/usr/bin/google-chrome` headless against the developer's own port: a
  screenshot with the window taller than the page, the page text, and a short scripted interaction
  (click, type, wait for text) enough to re-run something like the chat drop test.
- `tokens.py`: assemble a chat request the way the app does (instruction, tool schemas, history;
  reuse what `test_064_prompt_budget.py` uses), and print chars and tokens per part and provider. An
  exact tokenizer only if it works offline with no new dependency; otherwise a clearly labelled
  estimate. No network.
- These are **D21 building blocks**: one contract test per promise (e.g. "the ports it writes were
  free and distinct", "down removes the project"). A test that needs Docker or Chrome may skip
  cleanly when they're absent.
- **Live pass:** after the merge Maren posts `live-check:068-stack` and `live-check:068-browse`
  for team-lead. Put in your hand-off the exact command for each and the EXPECT facts it should show
  (facts, not wording).

## Rules for every stream this sprint (D21, D22, steer #1)

- **Context:** this sprint the team builds P14, its own retro. Read
  `meta/sprints/2026-11-05b/retro.md` and the P14 section of `meta/team-optimisation.md` (from
  the main checkout `/home/rudolf/dev/warcraftlogs-agent`, read-only) before you plan.
- **Testing shape (D21, use it already):** targeted tests while you build, one honest contract
  test per promise the story makes, no full suites mid-build, mutation (`mutate.py`) only for a
  security or concurrency guard, one bite each. Hand-off proof: `check.py run <your test
  files> --as <you>` on the committed head, and paste its RESULT line. A targeted run writes no
  receipt today; that's expected. Maren runs the one full suite at the merged tip.
- **GitNexus (D22, use it already):** `impact` before editing an existing Python function or
  class, and `detect-changes` once before hand-off, only when your diff changes code symbols.
  Not for markdown, agent files, skills, YAML or new stand-alone files. Don't post GitNexus
  results that change no decision.
- **Contracts:** the board keys `contract:board-to`, `contract:check-cli`, `contract:facts-cli`
  and `contract:tool-names` fix the interfaces other streams document or use. If your design
  needs a change to a contract you implement, post a `decision` on that same key with the new
  text (it supersedes the old one) before your hand-off; Vera documents whatever the latest
  entry says.
- **Board tests:** never run `board.py init`/`close` in a real checkout: the board root is the
  git common dir shared by every worktree, and `init` switches the live board for the whole
  team. Test board behaviour in a temporary `git init` repo, as `backend/tests/test_team_board.py`
  does.
- **No credentialed or live calls**, no `.env`, no default ports, never push. A check that
  needs the owner's stack: post a `question` with key `live-check:<feature>-pre` and the exact
  command, and team-lead runs it.
- **Tickets:** move your stories to In Progress at the start and Under Review in the hand-off.
- **Hand-off:** about 20 lines: branch, base, head; files; one line per AC with its proof;
  decisions; facts added or fixed; the `Retro:` line. Don't repeat your board `handoff`.
## Known facts for this footprint

Team facts for `observability/test/lib.sh`, `docker-compose.yml`, `frontend/vite.config.ts`, `frontend/package.json`, `backend/tests/test_064_prompt_budget.py`, `comp:compose`, `comp:grafana` (`python3 .claude/team/facts.py for ...`). Trust them, but re-check one marked STALE before relying on it; record a new lesson with `facts.py add`.

- **config-read-at-start-restart** (direct: comp:grafana; verified 32010a6 2026-11-05): Alloy, Mimir, Loki, Tempo and Grafana read their config at start. docker compose up -d --build leaves them on the old config, so a live check after a config change must first run docker compose restart for those services. Twice a check read stale config and gave a wrong verdict.
- **docker-socket-proxy-not-safe** (direct: file:docker-compose.yml; verified 32010a6 2026-11-05): A "GET-only" Docker socket proxy (tecnativa, POST=0) still serves container archive/export and `/containers/*/json`, which includes every container's env (DSNs). Since 058, Alloy has no Docker access at all (the Postgres log comes from the `pglog` volume). Keep it that way: Alloy parses browser (Faro) payloads. Mounting a socket `:ro` restricts nothing.
- **grafana-headless-render-height** (direct: comp:grafana; verified 32010a6 2026-11-05): Grafana leaves the uPlot canvases blank for panels outside the browser window. A headless screenshot with a window shorter than the page therefore shows empty time series: legends, no lines, no axes. Use a window taller than the page (D7 needs about 2800 px at 1600 px wide), or screenshot each panel.
- **grafana-servicemap-browser** (direct: comp:grafana; verified 32010a6 2026-11-05): Grafana runs the Tempo `serviceMap` query in the browser, and `/api/ds/query` refuses it, so a stack test can't run the panel the way Grafana does. Instead, run its Prometheus queries (`traces_service_graph_*`, by the fixed names Grafana uses) through the Mimir datasource, as `provisioning.sh` does.
- **ratio-panels-min-max** (direct: comp:grafana; verified aa03150 2026-11-05): Give every `percentunit` time-series panel `min: 0` and `max: 1`. An all-zero ratio series otherwise auto-scales to 0..100, which reads as 10000%. Every dashboard follows this since sc-508; `test_team_dashboards.py` (build) and `test_telemetry_metrics_dashboards.py` (runtime) enforce it.
- **stack-env-same-bash-call** (direct: comp:compose; verified 32010a6 2026-11-05): Each Bash tool call starts a fresh shell, so the env you exported in one call is gone in the next. A stack script then silently falls back to `lib.sh` defaults: project `wcl-obs-test` on the 24xxx ports, which belong to team-lead. Keep your stack env (`COMPOSE_PROJECT=wcl-obs-<name>` and your port block) in a scratch file and source it in the same call as the script.
- **stack-scripts-faro-pyroscope-ports** (direct: file:observability/test/lib.sh; verified 32010a6 2026-11-05): `observability/test/lib.sh` is bash (`BASH_SOURCE`, `[[ ]]`): run the scripts with bash. It moves only the OTLP, UI and Grafana ports (24xxx). `ALLOY_FARO_PORT` and `PYROSCOPE_PORT` keep compose's 12347 and 4040 unless the script sets them (faro, frontend, redaction-e2e and build-runtime set the Faro port; provisioning sets the Pyroscope port), so a second stack's Alloy fails to bind. Set both with your port block (Nils: 27347/27040).
- **tsbuildinfo-tracked** (direct: file:frontend/package.json; verified b9cf9a3 2026-11-05): `npm run build` (`tsc -b`) rewrites `frontend/tsconfig.tsbuildinfo`, which is tracked in git. Run `git checkout frontend/tsconfig.tsbuildinfo` before every commit so it doesn't ride along.
- **vitest-no-jest-dom** (direct: file:frontend/package.json; verified 1ee750a 2026-11-05): The frontend's Vitest setup has no `@testing-library/jest-dom`, so matchers like `toBeInTheDocument` don't exist. Assert on `textContent`, `toBeTruthy()` and plain values.
- **faro-loki-line-shape** (file: file:observability/grafana/dashboards/runtime/frontend.json is part of comp:grafana; verified b9cf9a3 2026-11-05): Faro lines in Loki are logfmt (`| logfmt`): `kind=` (measurement, event, exception, log), `view_name` (the route template), `value_<vital>` (`value_lcp`, `value_inp`, `value_cls`, ...), `event_name` and `event_data_<attr>` (`event_data_ttft_ms`). `session_id` is masked by the redaction rules. Find the session id as `session.id` on spans in Tempo. Probe real line shapes on your own stack before designing queries.
- **pg-tests-shared-db** (file: file:backend/tests/ contains backend/tests/test_064_prompt_budget.py; verified 32010a6 2026-11-05): The Postgres tests (`*_pg.py`, `test_rls.py`, via `TEST_DATABASE_URL`) share one long-lived database with no reset between tests. Use unique test data (fresh UUIDs and report codes), and never assert exact result lists over global tables (`raw_fetches`, `kb_chunks`, `spec_guides`): other tests' rows are there too.
- **runtime-dashboards-test-glob** (file: file:observability/grafana/dashboards/runtime/ is part of comp:grafana; verified 32010a6 2026-11-05): `test_telemetry_metrics_dashboards.py` globs every `*.json` in `dashboards/runtime/` (except `frontend.json`) and requires each Mimir query to use only the aliases in `runtime.yaml` or the contracted aliases. A new dashboard file there falls under that test (in 060 one broke two tests). Either place it elsewhere or ask for the one-line grant on the test at specify time.

(8 more: `facts.py brief --all ...`)
