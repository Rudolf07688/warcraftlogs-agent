# Brief 067-board-relevance-tools (Nils, seat dev-3)

- **Feature / branch:** `067-board-relevance-tools`, tier **S**, opus medium. Not security-core
  (no tenant data), but the hook reaches every agent's context: a filter that hides a blocker or an
  answer is the failure to design against.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-c` (detached at `9ff8602`). Base: `9ff8602`.
- **In parallel:** Vera (065, documents `--to` from `contract:board-to`), Tomas (066), Ansel (068).
- **Stories:** sc-531 (3; Vera writes its agent-file part, you move the ticket), sc-537 (2).

## Footprint (yours alone)

- `.claude/team/board.py`, `backend/tests/test_team_board.py`
- new `.claude/team/obsq.py`, new `.claude/team/indiff.py`, new `backend/tests/test_team_obsq.py`,
  new `backend/tests/test_team_indiff.py`
- `.claude/settings.json` only if the hook command itself must change (post a decision first).
- `.claude/team/usage.py` read-only (for the measurement).

## Acceptance criteria (verbatim from the stories)

**sc-531 (your part).** Board hook: today every entry reaches every agent after each tool call (Ansel, Maren). Deliver only what concerns the reader: its own keys and files, steer, decisions addressed to all, answers to its questions.
Measure board entries read per agent before and after (usage.py --context).
(The other bullets, no ritual notices, leaner agent files and a lighter hand-off, are Vera's.)

**sc-537.**
4. Read-only Tempo/Loki query helper (Nils hand-rolled curl through the Grafana proxy).
5. "Is this finding in this sprint's diff or in older code?" for triage (Maren).

## Contracts you implement

- `contract:board-to` (read it with `board.py current`). Refine with a superseding `decision` on
  the same key if your design differs; Vera documents the latest entry.
- `contract:tool-names`: `obsq.py`, `indiff.py`.

## Notes from Maren

- **Measure offline:** replay the 2026-11-05b and 2026-11-07 board logs (the jsonl files under the
  git common dir's `team-board/`, read-only) through the old and the new delivery rule, and report
  entries delivered per reader. "After" in real sessions is measured next sprint.
- The PO, SM and team-lead keep the full feed; a developer must still get every entry addressed to
  it, the `steer`, `contract:*`, and replies on keys it posted on. `board.py wait` is unchanged.
- The hook runs after every tool call with a 5 s timeout: keep it cheap, and keep cursors correct
  (an entry filtered out must not reappear later as "new").
- Test only in a temporary git repo (see the common rules). The change takes effect after the
  merge to main, because the hook runs `$CLAUDE_PROJECT_DIR/.claude/team/board.py`.
- `obsq.py`: GET only, enforced in code; queries through a Grafana datasource proxy given by URL
  and credentials from the environment of the developer's own test stack (`observability/test/lib.sh`
  style, or Ansel's `stack.py` env file); never reads `.env`, never prints a secret. Running it
  against the owner's stack is team-lead's (`live-check:` question).
- `indiff.py`: given `path:line` (one or many, e.g. lines copied from a QA report) and a base
  (default: merge base with the sprint branch), say whether that line was added or changed in
  `base...HEAD` or is older code (with the commit and date that last touched it).

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

Team facts for `.claude/team/board.py`, `backend/tests/test_team_board.py`, `observability/test/lib.sh`, `comp:tempo`, `comp:loki`, `comp:grafana` (`python3 .claude/team/facts.py for ...`). Trust them, but re-check one marked STALE before relying on it; record a new lesson with `facts.py add`.

- **adk-content-event-semconv** (direct: comp:loki; verified b9cf9a3 2026-11-05): With `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` (set by `policy.py`), ADK 2.10 emits prompt and response content as the log event `gen_ai.client.inference.operation.details` (with `gen_ai.input.messages`, `output.messages`, `system_instructions` and `tool.definitions`) and on `generate_content` spans. The stable semconv would emit `gen_ai.user.message`/`gen_ai.choice` instead. Alloy routes any `^gen_ai\.` event to the content stream, so both land there.
- **config-read-at-start-restart** (direct: comp:grafana; verified 32010a6 2026-11-05): Alloy, Mimir, Loki, Tempo and Grafana read their config at start. docker compose up -d --build leaves them on the old config, so a live check after a config change must first run docker compose restart for those services. Twice a check read stale config and gave a wrong verdict.
- **faro-loki-line-shape** (direct: comp:loki; verified b9cf9a3 2026-11-05): Faro lines in Loki are logfmt (`| logfmt`): `kind=` (measurement, event, exception, log), `view_name` (the route template), `value_<vital>` (`value_lcp`, `value_inp`, `value_cls`, ...), `event_name` and `event_data_<attr>` (`event_data_ttft_ms`). `session_id` is masked by the redaction rules. Find the session id as `session.id` on spans in Tempo. Probe real line shapes on your own stack before designing queries.
- **grafana-headless-render-height** (direct: comp:grafana; verified 32010a6 2026-11-05): Grafana leaves the uPlot canvases blank for panels outside the browser window. A headless screenshot with a window shorter than the page therefore shows empty time series: legends, no lines, no axes. Use a window taller than the page (D7 needs about 2800 px at 1600 px wide), or screenshot each panel.
- **grafana-servicemap-browser** (direct: comp:grafana; verified 32010a6 2026-11-05): Grafana runs the Tempo `serviceMap` query in the browser, and `/api/ds/query` refuses it, so a stack test can't run the panel the way Grafana does. Instead, run its Prometheus queries (`traces_service_graph_*`, by the fixed names Grafana uses) through the Mimir datasource, as `provisioning.sh` does.
- **loki-rejects-old-entries** (direct: comp:loki; verified b9cf9a3 2026-11-05): Loki refuses an entry more than about an hour older than its stream's newest entry with a 400, a permanent failure. Replaying or seeding old log data into an existing stream fails this way; use a new stream label or fresh timestamps. Details: observability/README.md.
- **loki-structured-metadata-64k** (direct: comp:loki; verified b9cf9a3 2026-11-05): Loki refuses a record whose structured metadata is over 64 KiB (400 "structured metadata too large"), and OTLP log attributes become structured metadata. So the backend cuts dev content records to `CONTENT_RECORD_BUDGET` (32,000 chars) before scrubbing and marks them `app.content.truncated="true"`. Any new log path that carries big attributes needs a similar bound.
- **ratio-panels-min-max** (direct: comp:grafana; verified aa03150 2026-11-05): Give every `percentunit` time-series panel `min: 0` and `max: 1`. An all-zero ratio series otherwise auto-scales to 0..100, which reads as 10000%. Every dashboard follows this since sc-508; `test_team_dashboards.py` (build) and `test_telemetry_metrics_dashboards.py` (runtime) enforce it.
- **stack-scripts-faro-pyroscope-ports** (direct: file:observability/test/lib.sh; verified 32010a6 2026-11-05): `observability/test/lib.sh` is bash (`BASH_SOURCE`, `[[ ]]`): run the scripts with bash. It moves only the OTLP, UI and Grafana ports (24xxx). `ALLOY_FARO_PORT` and `PYROSCOPE_PORT` keep compose's 12347 and 4040 unless the script sets them (faro, frontend, redaction-e2e and build-runtime set the Faro port; provisioning sets the Pyroscope port), so a second stack's Alloy fails to bind. Set both with your port block (Nils: 27347/27040).
- **pg-tests-shared-db** (file: file:backend/tests/ contains backend/tests/test_team_board.py; verified 32010a6 2026-11-05): The Postgres tests (`*_pg.py`, `test_rls.py`, via `TEST_DATABASE_URL`) share one long-lived database with no reset between tests. Use unique test data (fresh UUIDs and report codes), and never assert exact result lists over global tables (`raw_fetches`, `kb_chunks`, `spec_guides`): other tests' rows are there too.
- **runtime-dashboards-test-glob** (file: file:observability/grafana/dashboards/runtime/ is part of comp:grafana; verified 32010a6 2026-11-05): `test_telemetry_metrics_dashboards.py` globs every `*.json` in `dashboards/runtime/` (except `frontend.json`) and requires each Mimir query to use only the aliases in `runtime.yaml` or the contracted aliases. A new dashboard file there falls under that test (in 060 one broke two tests). Either place it elsewhere or ask for the one-line grant on the test at specify time.
- **stack-env-same-bash-call** (file: file:observability/test/ contains observability/test/lib.sh; verified 32010a6 2026-11-05): Each Bash tool call starts a fresh shell, so the env you exported in one call is gone in the next. A stack script then silently falls back to `lib.sh` defaults: project `wcl-obs-test` on the 24xxx ports, which belong to team-lead. Keep your stack env (`COMPOSE_PROJECT=wcl-obs-<name>` and your port block) in a scratch file and source it in the same call as the script.

(10 more: `facts.py brief --all ...`)
