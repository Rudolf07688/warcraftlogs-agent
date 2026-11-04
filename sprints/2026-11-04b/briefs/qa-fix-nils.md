# Brief: QA fix round, runtime metrics (056), tier S

- **Seat:** `dev-3` (Nils). Fresh run: the report below is your source. In parallel: Ansel (dev-1) fixes 055 in `dev-a`, Tomas (dev-2) updates docs in `dev-c`. Disjoint files.
- **Tier S:** a short plan, then implement. No Spec Kit. Record decisions on the board (key `scope:056-fix:*`).
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b`. Base: sprint tip `sprint-2026-11-04b` = `1c7a931`. Branch `056-qa-fix` from it.
- **Report:** `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-04b-sweep/bugs.md` (BUG-001, BUG-003, BUG-005).

## Fix these (and nothing else). Test first: write the failing test, then fix.
1. **BUG-001 (High): time-to-first-token uses the wrong start, and can crash the turn.** In `backend/app/agent_runner.py` `_run_turn`, the turn start `started` (~302) is overwritten by the per-tool timer `started = pending_started.pop(call_id, None)` (~377). On any turn that calls a tool before answering, TTFT is measured from the last tool call; if a tool response has no matching call id, `started` is `None` and `_record_ttft` raises a TypeError after the tools ran. Give the turn start its own name. Tests: TTFT value is measured from the turn start across a tool call (assert the value, with a controllable clock); a tool response without a matching call id doesn't break the turn. Mutation must bite.
2. **BUG-003 (Low, this sprint's regression): `app.cache.requests` counts some lookups twice** (`wcl_agent/cache/cache.py` ~375): a corrupt entry counts as error and miss; a batch of N keys with Redis down gives N+1 misses. Exactly one count per key lookup. Tests for both.
3. **BUG-005 (Low): a KB search scoped by `report_code` is labelled index "all"** though it only searches WCL chunks (`backend/app/kb/search.py`). Label it by what is actually searched. Test.

4. **Live pass findings (board #68, team-lead on 1c7a931), yours:**
   - (b) **D7 "App: Agents and LLM": every time-series panel is empty** at 3h and 30m (agent run duration, TTFT, tokens/min, cost/hour, model latency, tool calls, tool latency), while its stat row shows data and the same aliases render in D8. Suspect the D7 panel queries/intervals/datasource refs; find the cause, don't guess.
   - (c) **D8 "Hit ratio by family" y-axis goes to 10000 %**: percent unit on a value already ×100.
   - (d) **Counts shown as fractions** (D7 "Tool calls in range" 3.33/1.04, D8 lookups 1.03): counts over a range must use `increase()` on the raw counter (or a counter-total alias), not `sum_over_time(rate alias) * 60`. Check every D6/D7/D8 count stat for the same pattern.
   - Note: alias panels start when the ruler started (no backfill); expected. The embedding timeout (keyword_only strategy on D8) is pre-sprint and ticketed separately (sc-455): not yours.
   - **Proof:** a headless screenshot (google-chrome or Grafana's render) of each fixed panel populated, on your own observability stack fed with synthetic data (Docker grant: `docker compose -p wcl-obs-nils --profile observability ...`, 27xxx host ports via the env overrides in `observability/test/lib.sh`, observability services only, never the `warcraftlogs-agent` project, `down -v` after), plus a test in `test_telemetry_metrics_dashboards.py` that bites (e.g. a time-series panel must have a query the datasource can run; count stats must not use `sum_over_time(...rate...)`; no ×100 with a percent unit). Name the screenshot paths in your hand-off (scratch files, not committed). Team-lead re-checks on the tip afterwards.

Not in this round: anything else in the reports.

## Footprint
`observability/grafana/dashboards/runtime/**`, `observability/mimir/rules/anonymous/runtime.yaml`, `backend/tests/test_telemetry_metrics_dashboards.py`, `backend/app/agent_runner.py`, `wcl_agent/cache/cache.py`, `backend/app/kb/search.py`, `backend/app/telemetry/metrics.py`, `backend/tests/test_telemetry_metrics*.py` (and a runner test file only if the TTFT test fits better there: `backend/tests/test_agent_runner*.py`), `specs/056-runtime-metrics/**`.

## Hand-off
Commit, `check.py run --as nils` (receipt), board `handoff` with key `status:056-fix` naming each bug and its proof, and return branch, head, RESULT/RECEIPT lines, per-bug proof. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
