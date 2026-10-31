# Brief 041: QA fixes for the raw store (039), one round

- **Branch:** `041-qa-store-fixes` from the sprint tip:
  `git -C /home/rudolf/dev/wcl-worktrees/dev-a switch -c 041-qa-store-fixes sprint-2026-10-31c`
  (tip `5550997`, which already has 039 and 040 merged).
- **Tier:** S (a short plan, then implement). Seat `dev-1` (Ansel), the author of 039.
- **Reports:** `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-10-31c/` (README, then
  `bugs.md`, `security.md`, `spec-conformance.md`, `performance.md`).
- **Footprint:** the same as 039 (`owner:039`). No new migration unless a fix truly needs one;
  if so, use `0019_<name>` with down_revision `0018_raw_store_visibility` and say why.
- **Parallel:** Tomas fixes 040's two findings in dev-b (`ws.py`, `MessageList.tsx`, restClient).
- **Tests:** `env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q`, plus the Postgres
  files on your throwaway container (port 15439). Stop it when done.

This is the one rework round. Fix exactly these; anything else you notice goes on the board
as `backlog:<topic>`.

## Fix 1: gone detection must not delete a report that still exists
Findings: BUG-001 (High), BUG-002, BUG-003, BUG-007, SEC-002, SPEC-003, and Maren's note #40.

Acceptance criteria:
1. A report's stored rows and Redis keys are deleted only when WCL really says the report is
   gone. That means our own known report query (the same "our own query texts" rule you used
   for status), answered with `reportData.report: null`. With `errors`, only when the error is
   at the `report` path itself, not a subfield, or when it reads as not-found/permission. Your
   call; post the rule.
2. None of these deletes anything: a null that propagated up from a subfield error; an aliased
   `reportData` response key; a padded code literal (`"ABC "`); a hand-written
   `run_wcl_graphql` query.
3. Tests for each case in AC2, plus the positive case (our summary query returning null still
   deletes).

## Fix 2: grants come from what WCL returned, not from the query text
Findings: SEC-001 (High), SPEC-001, BUG-005.

Acceptance criteria:
1. A tenant gets a grant for a code only when the response actually contains that report
   (non-null), from a query whose codes the strict parser resolves. Or grant only from our own
   known queries, if that's simpler; post which.
2. None of these earns a grant: a code in a field skipped by `@skip`/`@include`; a code inside a
   GraphQL string literal; a code answered `null` in a batch or aliased query without errors;
   a null single-report response over the 4 KB gone-scan limit.
3. Tests for each case in AC2.

## Fix 3: the writer's batch timeout
Findings: BUG-004, PERF-003, SPEC-004, SEC-003, PERF-008.

Acceptance criteria:
1. A batch that times out doesn't drop all of its items: they get the same one-by-one retry that
   other errors get. A `ReportGone` item in particular is not lost to a batch timeout.
2. Batches are capped by bytes as well as by count.
3. The Redis eviction for gone reports runs outside the timed DB part.
4. Tests for 1–3.

## Not in this round (deferred to Backlog by Maren)
PERF-001 (store-read timeout and breaker), PERF-002/004/005/006/007/009, SPEC-005 (docs and
`.env.example`), and the two "suspicious" races in `bugs.md`. Don't fix them. If one turns out
to be trivial and inside a function you're already changing, post it before doing it.

## Done means
- All ACs met, both suites green (SQLite in a clean env, and the Postgres files on your
  container), GitNexus impact before each edit, `detect-changes` before each commit. Commits end
  with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Make one bypass attempt on fixes 1 and 2, and describe it in the hand-off.
- Don't move tickets: sc-178/177/129 stay Under Review. Never push or merge.
- Hand-off: branch, commits, files, test counts, an AC mapping per fix, and the bypass attempt.
