# Brief: architecture docs current at the sprint tip (close-out step 5)

- **Branch:** `archdocs-2026-11-04`, from the sprint tip: `cd /home/rudolf/dev/wcl-worktrees/dev-a && git checkout -b archdocs-2026-11-04 sprint-2026-11-04` (tip `1dce358`).
- **Tier:** S (short plan, then do it). Seat `dev-2` (Tomas). No other developer is running.
- **Security-core:** no. No ticket moves.
- **Procedure:** `documentation/architecture/pages/maintaining.html` (read it first), tool `python3 .claude/team/archdocs.py` (`changed`, `stamp`, `check`).

## What moved this sprint (from `archdocs.py changed` at 1dce358)
- backend-api.html: `backend/app/main.py` (telemetry bootstrap before the ADK import, OTLP log handler), new package `backend/app/telemetry/` (config, policy, redaction, setup), `pyproject.toml` (OpenTelemetry deps).
- deployment.html: `docker-compose.yml` (always-on Alloy, the `observability` profile with Loki, Tempo, Mimir, Grafana, named volumes, backend telemetry env), `.env.example` (telemetry and Grafana vars), `bin/01_start_app.sh` (WCL_GIT_SHA), new `bin/claude-otel`.
- database.html: `docker-compose.yml` (check only whether anything on the page changed; probably just the stamp).
- models.html: `wcl_agent/llm/generation.py` (one GenAI span around one-shot calls).
- streaming.html: `backend/app/api/ws.py` (each chat turn is the root of its own trace: `chat_turn_span`).
- Unmapped: `observability/**` (Alloy config and OTTL rules, Loki/Tempo/Mimir config, Grafana provisioning and entrypoint, test scripts, README).

## Do
1. Re-verify each listed page's affected sections **against the code at the tip**, not the specs: add the new components, correct anything now wrong, remove nothing that still exists.
2. Decide where `observability/**` and `backend/app/telemetry/**` belong. The recommended choice: a new topic page `pages/observability.html` (from `_template.html`). It covers the telemetry pipeline end to end: build layer (`bin/claude-otel`), runtime layer (backend bootstrap, what's instrumented, content policy per environment, the two redaction layers), Alloy (disk queue, redaction, content-stream routing), the backends and retention, Grafana. The other pages then link to it rather than repeat it. Add the paths to `PAGE_PATHS` in `.claude/team/archdocs.py` (that list only), and add the page to `index.html` (layer table and system diagram).
3. `archdocs.py stamp`, then `archdocs.py check` must pass.
4. Screenshot each changed or new page (light, 1280 px; `google-chrome --headless=new --screenshot=… --window-size=1280,2400 file://…`) into `/tmp/claude-1000/-home-rudolf-dev-warcraftlogs-agent/abba4d56-cb4a-4e79-8339-ee7e30c342ab/scratchpad/archdocs/`, and look at them: nothing broken or overlapping.

## Footprint
`documentation/architecture/**`, `.claude/team/archdocs.py` (`PAGE_PATHS` only). Nothing else. No Python tests change, but run `check.py run --as tomas` on the committed tree for the receipt (it should be a formality).

## Hand-off
Board `handoff` with key `status:archdocs`, and the final result: branch, commit, pages changed or added, the `archdocs.py check` output, screenshot paths, and anything in the code you found surprising.
