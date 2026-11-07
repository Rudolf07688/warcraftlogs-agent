# Brief 066-test-tools-facts (Tomas, seat dev-2)

- **Feature / branch:** `066-test-tools-facts`, tier **S**, opus medium. Not security-core.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b` (detached at `9ff8602`). Base: `9ff8602`.
- **In parallel:** Vera (065, agent files: she documents your CLI from `contract:check-cli` and
  `contract:facts-cli`), Nils (067), Ansel (068).
- **Stories:** sc-530 (3), sc-529 (2), and the `check.py` receipt-by-area part of sc-526 (Vera
  moves sc-526).

## Footprint (yours alone)

- `.claude/team/check.py`, `.claude/team/mutate.py`, `.claude/team/facts.py`
- `backend/tests/test_team_facts.py`, new `backend/tests/test_team_check.py`, new `backend/tests/test_team_mutate.py`
- `.claude/team/facts/tool-docstring-is-prompt*` (the fact file edit for sc-529)
- Ansel adds the Grafana source-map fact (sc-529 item) himself in his stream; you don't.

## Acceptance criteria (verbatim from the stories)

**sc-530 Test tools.**
- `mutate.py` supports vitest (Tomas, his first priority: on 063 he hand-reverted code to check frontend tests).
- `check.py` runs `npm ci` when a fresh worktree has no node_modules (Tomas).
- `check.py` receipt by touched area: frontend-only → vitest + build; backend → pytest; config-only → the named targeted tests. Tomas ran 2344 backend tests for a frontend-only story (supports the testing shape story).

**sc-529 Briefs carry facts for the paths a developer runs.** Ansel's brief missed `stack-scripts-faro-pyroscope-ports` because `observability/test/lib.sh` wasn't in his footprint, and his first stack start collided on port 12347.
- `facts.py brief` takes the paths a developer will run as well (stack scripts, test libs, files they source/import in tests), e.g. `--runs <paths>` or derived from the brief's verification commands; the PO passes them.
- Add facts: the Grafana plugin source-map recipe (Ansel; in his stream); the pinning test files on `tool-docstring-is-prompt` (Vera: pins sit in five test files, some across line breaks; find them by grep).
- Fix the remaining stale gap: a directory anchor `file:.claude/team/` would still go stale on a fact edit (Tomas).

**sc-526, receipt part (D21 layer 1-2):** the hand-off receipt is one suite for the touched part;
the PO checks receipts per branch, merges all disjoint streams and runs one full suite at the tip.

## Contracts you implement (posted by Maren; refine with a superseding `decision` on the same key)

- `contract:check-cli` and `contract:facts-cli`. Read them on the board (`board.py current`).

## Notes from Maren

- Evidence seen today from the main checkout: `facts.py brief ... comp:team` marks
  `qa-reports-gitignored`, `shortcut-sync-iteration-sweep` and `uv-virtualenv-owner-venv` STALE
  (all verified 32010a6), and lists comp:postgres facts under comp:team via "shares paths". Check
  whether the STALE marks are the same directory-anchor gap; the "shares paths" noise and the
  "GitNexus unavailable (no JSON in the cypher output)" line are out of scope unless they share the
  root cause: post `backlog:` notices otherwise.
- Receipts must stay honest: only a committed clean tree, and the receipt records which area and
  which commands ran, so a frontend receipt never reads as a backend pass.
- `mutate.py` for vitest: same guarantees as for pytest (baseline must pass, restore byte for byte
  even on kill, a collection/compile error is not a bite).
- `npm ci` only when the frontend area runs and `frontend/node_modules` is missing.

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

Team facts for `.claude/team/check.py`, `.claude/team/mutate.py`, `.claude/team/facts.py`, `backend/tests/test_team_facts.py`, `frontend/package.json` (`python3 .claude/team/facts.py for ...`). Trust them, but re-check one marked STALE before relying on it; record a new lesson with `facts.py add`.

- **tsbuildinfo-tracked** (direct: file:frontend/package.json; verified b9cf9a3 2026-11-05): `npm run build` (`tsc -b`) rewrites `frontend/tsconfig.tsbuildinfo`, which is tracked in git. Run `git checkout frontend/tsconfig.tsbuildinfo` before every commit so it doesn't ride along.
- **vitest-no-jest-dom** (direct: file:frontend/package.json; verified 1ee750a 2026-11-05): The frontend's Vitest setup has no `@testing-library/jest-dom`, so matchers like `toBeInTheDocument` don't exist. Assert on `textContent`, `toBeTruthy()` and plain values.
- **pg-tests-shared-db** (file: file:backend/tests/ contains backend/tests/test_team_facts.py; verified 32010a6 2026-11-05): The Postgres tests (`*_pg.py`, `test_rls.py`, via `TEST_DATABASE_URL`) share one long-lived database with no reset between tests. Use unique test data (fresh UUIDs and report codes), and never assert exact result lists over global tables (`raw_fetches`, `kb_chunks`, `spec_guides`): other tests' rows are there too.
- **qa-reports-gitignored** **STALE** (component: comp:team covers .claude/team/check.py; verified 32010a6 2026-11-05): `qa-reports/` is gitignored, so QA reports exist only in the worktree where they were written, usually the sprint worktree: P7 reviews in `qa-reports/<date>/`, the end sweep in `qa-reports/<date>-sweep/`. They never reach main. Cite them by worktree path, and copy anything that must last into a committed sprint file (for example `qa-triage.md`).
- **shortcut-sync-iteration-sweep** **STALE** (component: comp:team covers .claude/team/check.py; verified 32010a6 2026-11-05): shortcut-sync's tidy step assigns the active iteration to every Shortlist, In Progress or Under Review story that lacks one. During a sprint that puts the sprint iteration on unrelated Shortlist stories, such as next-sprint candidates. After each sync, check the iteration and remove it from stories that aren't sprint work.
- **uv-virtualenv-owner-venv** **STALE** (component: comp:team covers .claude/team/check.py; verified 32010a6 2026-11-05): Agent shells carry `VIRTUAL_ENV=/home/rudolf/dev/warcraftlogs-agent/.venv`, the owner's checkout. So `uv pip ...` run in a worktree changes the owner's venv, and `uv run`/`uv sync` warn. For lockfile and dependency work in a worktree, use `env -u VIRTUAL_ENV uv lock` and `env -u VIRTUAL_ENV uv sync`.
