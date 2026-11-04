# Brief 055: build telemetry (board into Loki, RED from traces, D1/D2, pricing)

- **Feature / branch:** 055, `055-build-telemetry`
- **Tier:** M (one Spec Kit pass: specify → plan → tasks → implement, no gates; answer your own clarify questions and record them on the board)
- **Seat:** `dev-1` (Ansel). Parallel developers: Nils (dev-3) on 056 runtime metrics, Tomas (dev-2) on 057 browser telemetry. Read the board's `contract:*` and `owner:*` keys first: they bind you.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a` (detached at the base). Base ref: sprint branch tip `sprint-2026-11-04b` = `3262948`. Create your branch there.
- **Security-core:** no. But the board tail must pass Alloy's redaction chain (see below); prove it with the redaction script.
- **Migration:** none.
- **Read first:** `specs/telemetry_spec.md` §4.2, §5, §6.5, §8.2, §8.3, §9, §14 (decisions binding). The stories below win where they differ. The PO's comments on 408 and 410 are part of the AC.

## Stories, in this order (AC verbatim from Shortcut)

### Team board into Loki with trace links (sc-407, 2)
- `.claude/team/board.py` records the `TRACEPARENT` that Claude Code passes to Bash on each entry.
- Alloy tails `.git/team-board/*.jsonl` into Loki (indexed labels from the §9.2 allowlist only).
- From a handoff entry you can open its author's trace; after a Loki restart the board backfills from the file.
- Session transcripts are NOT tailed (usage.py reads them on demand).

PO notes:
- Store the **full** traceparent (trace id and span id) on each entry. Team-lead verified: the trace id is the lead session's current turn and is shared by every sub-agent launched in that turn, and it changes each lead turn. So the trace id alone does not identify the author; the span id points at the author's own tool span, and seat identity stays `--as`. Entries without `TRACEPARENT` (plain shell) still post. Older entries without the field must still read, wait and render.
- The board lives under the git common dir (`board.py` `git rev-parse --git-common-dir`). In a worktree `./.git` is a file, so the Alloy mount comes from `${TEAM_BOARD_DIR:-./.git/team-board}` (contract:compose).
- Route the tail through the redaction chain (e.g. `loki.source.file` → `otelcol.receiver.loki` → the existing chain), never straight to `loki.write`. Decide and record whether board entries land in the content stream or the 30-day stream (board text is agent prose, not prompts; the board must survive a Loki restart via backfill either way).
- Fix the wrong comment in `bin/claude-otel` (decision:otel-env): `OTEL_*` do not reach the session's Bash tool; only `CLAUDE_CODE_ENABLE_TELEMETRY`, `..._BETA` and `TRACEPARENT` do. A backend run from a session exports only if its endpoint is set explicitly (the compose backend has it).

### RED metrics from traces: spanmetrics and service graph (sc-409, 2)
- Alloy `spanmetrics` and `servicegraph` connectors run before sampling, with the extra dimensions from §4.2 and exemplars on; no IDs or raw URLs as dimensions.
- RED per `http.route` is queryable with exemplars; the SSE chat route is excluded from latency panels and alerts.

PO notes: the chat route is the WebSocket `/ws/chat` (root span "chat turn", `http.route=/ws/chat`), plus streaming guide generation (`.*/generate`): both excluded from latency aliases. `session.id` is never a dimension (contract:session-id). Define the RED aliases exactly as contract:red-aliases says; if a label must differ, supersede that key early, since Nils builds D6 on it.

### Build dashboards: Claude Code overview and agent team (D1, D2) (sc-408, 3)
- D1 (overview) and D2 (agent team) are provisioned as JSON under version control.
- Cost is shown by model, `agent.name` and board seat; every cost panel is labelled "estimated, list price".
- Panels query recording-rule aliases (`cc:*`), not raw metric names.

PO notes (decision:dashboards, comment on 408): D1 extends `observability/grafana/dashboards/build/claude-code-overview.json` (keep its uid). D2 is a new `agent-team.json`, with links to and from "Agent Team: Improvement" (D13). Seat cost is per sprint, pushed by `.claude/team/teamstats.py` at wrap-up (extend it from what `usage.txt`/the board already give; if per-seat cost can't be derived honestly, show per-role and say so on the board). D13 must keep working.

### LLM pricing table and cost recording rules (sc-410, 3), drop first if it slips
- `observability/pricing/pricing.yaml` (model × token_type) is exposed as `llm_price_usd_per_token`; a Mimir recording rule computes `genai:cost_usd:rate5m` by model and agent.
- Cost per hour for one chat turn matches the token × price arithmetic, for Claude and for Gemini.
- Price changes are a config commit; historical cost stays correct.

PO notes (comment on 410): backend token usage is a **native (exponential) histogram** (`backend/app/telemetry/setup.py` `metric_exporter`), so there is no `_sum` series: use `histogram_sum(rate(gen_ai_client_token_usage[5m]))`. Labels are `gen_ai_request_model`, `gen_ai_token_type`, `gen_ai_agent_name` (see the T1 query in `observability/grafana/dashboards/runtime/app-api-llm.json`). Output labels per contract:cost-alias. A generated rules file from `pricing.yaml` (vector constants) is fine if it beats a tiny exporter; pick the simplest that keeps history correct and say why. Model ids: take them from `wcl_agent/llm/` (provider ids actually emitted), Claude and Gemini both.

## Foundation first: Mimir recording rules (contract:recording-rules)
No rules exist yet: `mimir.yaml` has only `ruler_storage: storage_prefix: ruler`, and compose mounts only `mimir.yaml`. Your first commit enables the ruler with local storage and mounts `observability/mimir/rules/<tenant>/` read-only; verify the local-storage layout and tenant dir against the pinned Mimir version's docs, then post the final path on `contract:recording-rules` (supersede it). Files: `build.yaml`, `red.yaml`, `cost.yaml` are yours; `runtime.yaml` is Nils's.

## File footprint (stay inside it; board `owner:stream-a` plus the shared keys)
- `.claude/team/board.py`, `.claude/team/teamstats.py`, `bin/claude-otel`
- `observability/mimir/**` (except `rules/*/runtime.yaml`), `observability/pricing/**`, `observability/grafana/dashboards/build/**`, `observability/test/**` (except `faro*`), `observability/README.md` (Tomas appends a Faro section at the end)
- `observability/alloy/config.alloy`: the existing sections plus your new ones; Tomas appends one Faro section at the end (contract:alloy-config)
- `docker-compose.yml`: alloy volumes + mimir volumes only (contract:compose)
- new `backend/tests/test_team_*.py`; `specs/055-build-telemetry/**`
- Nothing else. Need something: ask on the board with key `owner:<path>`.

## Docker (explicit grant; overrides the developer file's "no docker compose")
- Only through the `observability/test` scripts or `docker compose -p wcl-obs-ansel --profile observability ...`, observability services only, on 25xxx host ports via the env overrides (contract:test-stacks). Never touch the `warcraftlogs-agent` project: it is live and observes this session. `down -v` after each run and before hand-off.
- `mimirtool`/`promtool` via a pinned docker image are fine for rule linting.
- Every proof that needs the stack is a script under `observability/test/` that team-lead can re-run on the merged tip.

## Tests and proof
- `check.py run --as ansel` on your committed tree (receipt matters). board.py changes get unit tests (traceparent stored, absent, old entries still read).
- Scripts prove: board entry in Loki with its traceparent and only allowlisted labels, backfill after a Loki restart, seeded secret in a board entry arrives masked; spanmetrics/servicegraph series with exemplars and no id dimensions; rules load and evaluate (`cc:*`, `app:http_*`, `genai:cost_usd:rate5m` against synthetic token data for one Claude and one Gemini model, arithmetic checked); dashboards provision and every panel expr uses an alias.
- Live checks (team-lead runs them on the merged tip): post each as a board `question` with key `live-check:055` and exact steps (e.g. handoff entry → trace in Tempo; D1/D2 panels populated from this session).

## Hand-off
Stories to Under Review, a board `handoff`, and your final result: branch, commits, files, the `check.py` RESULT and RECEIPT lines, your script results, risks, and an AC-by-AC mapping. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
