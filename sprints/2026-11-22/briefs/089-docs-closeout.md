# Brief 089: architecture docs and team facts close-out

- **Branch:** `089-docs-closeout`. **Tier S.** **Seat:** dev-2 (Tomas). **Model:** sonnet high.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a` (another branch is checked out there: create yours from `sprint-2026-11-22` at 78d5c5a and use 78d5c5a as `--base`).
- **Nobody else runs** in parallel; the sprint is merged (features 084-088).

## Goal
Bring `documentation/architecture/` to the sprint tip in one pass, following
`documentation/architecture/pages/maintaining.html`, and re-verify the stale team facts.
Docs describe the code as it is; specs, briefs and board are context only, the code wins.

## Pages to re-verify (`python3 .claude/team/archdocs.py changed`)
- agent.html: agent_runner.py (re-runs counted as rounds, turn-stats fields budget_retries/empty_retries/time_cuts, answer_shown, heading rule in the status line), mechanics.py (notes lint at import, boss-in-text lookup, miss names the owning boss), benchmark.py (realm compare), report_tools.py (shorter damage_fields note, whole-report rankings by fight-id list)
- backend-api.html: raid_summary.py (rankings keys by fight-id prefix, newest row, null fallback)
- database.html: repository.get_main_selection
- deployment.html: bin/00_init_migrate_db.sh (check what changed; it may be nothing this sprint: then only the stamp)
- frontend.html: statusStore, statusText, TurnNotice, drop rechecks (2..150 s, 8 min), memoised PlotlyArtifact
- knowledge-base.html: mechanic notes (Nymrissa, Method sources, allowed hosts)
- models.html: 180 s Claude call bound and cut line, Gemini empty-STOP re-run, cache layout (time block leads the turn message, history and lagging breakpoints, max 4)
- streaming.html: ws.py interim order, drop placeholder, retry frame numbers, WebSocketDisconnected
- index.html: layer table and system diagram only if a layer changed
- open-points.html: the Claude history cache open point is now done (QA SPEC-005 named models.html:349-353, agent.html:149,436, open-points.html:69, wcl-data.html:311)
Then `archdocs.py stamp` and `archdocs.py check`, and a screenshot of each changed page (`browse.py`) to check it renders.

## Team facts (same pass)
`python3 .claude/team/facts.py stale` lists them. Skip a fact its author edited and verified this sprint (raid-summary-tool-keys, claude-prompt-cache-layout, model-call-one-rerun, chat-drop-ends-turn-locally, live-status-in-status-store, ws-drop-after-retraction-placeholder, mechanics-notes-per-tier, wcl-time-window-args, runner-interim-retraction if re-stamped). Re-check the rest against the code: `facts.py verify <id>` if it holds, edit then verify if partly, `facts.py retire <id> --why "..."` if not. `facts.py lint` must be clean.

## Footprint
`documentation/architecture/**`, `.claude/team/facts/**`. Commit on your branch; no code changes. Hand-off: list the pages you changed, the facts verified/edited/retired, and the `archdocs.py check` output. No test suite needed (docs only); state that.
