# Brief 018 — Restructure `wcl_agent` into sub-packages (plan F1)

| Field | Value |
|---|---|
| Feature number | 018 |
| Branch | `018-wcl-agent-subpackages` (set `GIT_BRANCH_NAME=018-wcl-agent-subpackages` for `/speckit-specify`) |
| Spec dir | `specs/018-wcl-agent-subpackages/` |
| Worktree | `/home/rudolf/dev/wcl-worktrees/dev-a` (track A) |
| Base ref | `sprint-2026-10-25` tip (see `git -C /home/rudolf/dev/wcl-worktrees/sprint rev-parse sprint-2026-10-25`; the worktree is detached there) |
| Model / effort | opus / high |
| Shortcut stories | sc-150 (5) |
| Peer developer | `dev-b-019` (track B, security hardening; no shared files) |
| Scrum master | `scrum-master` (your only channel upward) |
| Plan | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/plan.md` (section F1) |
| Ownership ledger | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/ownership.md` |
| Decisions | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/decisions.md` (entries 1 and 2 apply) |

## Merge priority

**This feature merges into the sprint branch first**, as soon as the product owner
accepts it. Every other branch rebases on it. It blocks F3, F5 and every later agent
story, so speed matters, but not at the cost of AC 4 (identical test counts).

## Plan section (verbatim)

## F1 — Restructure `wcl_agent/*.py` into sub-packages (Track A, first)

- **Stories:** sc-150 (5) Restructure wcl_agent/*.py into sub-packages.
- **Complexity:** medium. The work is mechanical, but the blast radius is wide: 25
  modules (7 kLOC), 69 backend files import from `wcl_agent` (45 of them tests), and
  about 10 tests patch dotted `"wcl_agent.x.y"` strings.
- **Footprint:** `wcl_agent/**`, the import lines of `backend/**` (app and tests),
  `main.py`, `pyproject.toml` (the `wcl` script entry, if `cli` moves), and
  `documentation/ai_guide.md` (module map).
- **Depends on:** nothing. **Blocks:** F3, F5, and every future agent story.
- **Acceptance criteria:**
  1. The modules are grouped into sub-packages along the story's lines (client, tools,
     guides, cache, models; the developer picks the final names and records the
     old-to-new mapping table in the spec). Package names must not shadow each other
     or the existing module names: for example, a `cache/` package can't sit next to
     `cache.py`.
  2. Files are moved with `git mv`, so `git log --follow` keeps their history.
  3. **No compatibility shims** are left at the old paths (constitution I, one
     authoritative implementation). Every importer is updated, including the dotted
     strings that `monkeypatch`/`mock.patch` use, and lazy imports inside functions.
  4. There is no behaviour change. The full backend test suite gives the same
     pass/fail/skip counts as at base `4923785` (record the baseline first).
  5. Every module imports cleanly. A smoke test (or a one-off script whose output goes
     in the PR notes) imports every `wcl_agent` submodule and `backend.app.main`, and
     reports no errors.
  6. `uv run wcl --help` (the console script) and `python main.py --help` still work.
     The backend container image builds, and the app boots locally to `ready` on
     `/api/health`.
  7. `documentation/ai_guide.md` and any other module map or path reference in
     docs/README match the new layout. Historical `specs/0xx` files are left alone.
  8. The diff contains moves and import edits only, with no opportunistic refactors.
     Anything worth changing gets noted for the backlog instead.

## Tentative footprint (becomes a grant after `/speckit-plan`)

- `wcl_agent/**` (all moves via `git mv`, plus new `__init__.py` files).
- Import lines and dotted patch strings **only** in the backend/root Python files that
  reference `wcl_agent` at base. There were 70 at base; list them with
  `grep -rl wcl_agent --include=*.py backend main.py`. That includes `backend/app/config.py`
  (an import plus path comments) and `backend/app/main.py`.
- `pyproject.toml` (the `wcl = "wcl_agent.cli:run"` script entry and `packages`, if
  needed). You hold the dependency-manifest token for this feature, but no dependency
  changes are expected. Say so if `uv.lock` changes.
- `README.md` and `documentation/**` path references: `ai_guide.md` and
  `live_model_probe.md`. For `documentation/designs/*` and `documentation/delivery/*`,
  propose in your file list whether they are historical (leave them alone) or living
  docs.
- **Not yours:** `CLAUDE.md`, `AGENTS.md` and `todo.md` belong to the scrum master. If
  they need path updates (`todo.md` mentions `wcl_agent`), send me the exact lines and I
  will make the change. `specs/0xx` historical files are left alone (AC 7).
- **Off limits (track B, feature 019):** `frontend/**`, `backend/app/api/auth.py`,
  `backend/app/services/auth_service.py`, `backend/app/auth/rate_limit.py`,
  `backend/Dockerfile`, `docker-compose.yml`, `.env.example`, and the auth and
  rate-limit tests. None of them import `wcl_agent` at base. If one must change for
  your feature, ask me first.

## Notes from the scrum master

- Record the baseline first: run `uv run --extra test pytest -q` at the base and save
  the pass/fail/skip counts in the spec or checkpoint.
- Check the non-Python references too: the Dockerfile `COPY wcl_agent ./wcl_agent`
  (should still work unchanged), the ADK and Alembic config, `pyproject` `packages`,
  and string paths in docs and skills.
- Good fit for sub-agents: the import rewrite over disjoint sets of test files, at
  `sonnet`/`medium`. Propose the split (task IDs → exact files → model/effort) after
  `/speckit-tasks`, and wait for my approval.
- For AC 6 "boots locally to ready", don't use the default ports. Ask me for a port.
  If the container build can't run on this host (no Docker access), report that
  instead of skipping it silently.
- GitNexus: run `impact` on the modules you move (their upstream importers are the blast
  radius). Before hand-off, re-index **your worktree** and run `detect-changes`.
