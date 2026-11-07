# Brief 077-team-cli-bugs (reserve, P15)

- Feature **077**, branch `077-team-cli-bugs`, tier **S** (short plan, then implement; no Spec
  Kit). Model sonnet, effort high. Stream type: **team tooling**.
- Seat **dev-2** (Tomas; fresh run). Worktree `/home/rudolf/dev/wcl-worktrees/dev-b` (073 is
  merged; create your branch there from the base). Base ref **d4d875d** (sprint tip).
- Security-core: no. Parallel: Nils (072), Edda (074), Ansel (075), Vera (076): none touch
  `.claude/team/`.

## Story
sc-541 (2) "QA SWEEP-1107-D: small CLI bugs in the team tools" (verbatim):
- BUG-012: a weaker run on the same tree overwrites a stronger receipt (full -> area, pg=yes ->
  pg=no) (.claude/team/check.py).
- BUG-013: `npm ci` runs only when frontend/node_modules is missing; a stale or partial install
  is reused.
- BUG-008: `tokens.py --history=FILE` crashes with ValueError.
- BUG-009: indiff.py reports every finding as unresolved when run from a subdirectory.
- BUG-014: `facts.py brief --runs` swallows the written targets that follow it (argparse nargs).

Acceptance: each bug has a test that fails before and passes after (excerpt of the original
reports: `sprints/2026-11-07/qa-triage.md`). No other behaviour change.

## File footprint
`.claude/team/check.py`, `.claude/team/tokens.py`, `.claude/team/indiff.py`,
`.claude/team/facts.py`, `backend/tests/test_team_check.py`, `backend/tests/test_team_tokens.py`,
`backend/tests/test_team_indiff.py`, `backend/tests/test_team_facts.py`.

## Hostile inputs (rule 10: check.py produces receipts other agents trust)
- A forged or hand-edited receipt file (wrong tree hash, area "full" claimed by an area run,
  pg=yes without a pg run) must not be kept as the stronger one: the "keep the stronger
  receipt" rule compares what was actually run on that tree.
- Two runs on the same tree: the stronger (full over area, pg=yes over pg=no) survives in
  either order; a failing run never replaces a passing one silently (decide and state which
  wins as `scope:077:receipt-order`).
- For BUG-013: decide a cheap staleness signal (e.g. lockfile hash stamp) instead of `npm ci`
  every run; a partial `node_modules` (no stamp) triggers `npm ci`.
- Never run `board.py init`/`close`; test tools in temp dirs.

## Common rules
Never push or merge; footprint only; receipt with
`python3 .claude/team/check.py run --as tomas --base d4d875d` on your committed head. Live
checks: none expected. Hand-off as in `developer.md` with a `Retro:` line.
## Known facts for this footprint

Team facts for `.claude/team/check.py`, `.claude/team/tokens.py`, `.claude/team/indiff.py`, `.claude/team/facts.py`, `backend/tests/test_team_check.py`, `backend/tests/test_team_tokens.py`, `backend/tests/test_team_indiff.py`, `backend/tests/test_team_facts.py` (`python3 .claude/team/facts.py for ...`). Trust them, but re-check one marked STALE before relying on it; record a new lesson with `facts.py add`.

> GitNexus unavailable (no JSON in the cypher output); file and component matches only

- **pg-tests-shared-db** (file: file:backend/tests/ contains backend/tests/test_team_check.py; verified d4ccc69 2026-11-07): The Postgres tests (`*_pg.py`, `test_rls.py`, via `TEST_DATABASE_URL`) share one long-lived database with no reset between tests. Use unique test data (fresh UUIDs and report codes), and never assert exact result lists over global tables (`raw_fetches`, `kb_chunks`, `spec_guides`): other tests' rows are there too.
