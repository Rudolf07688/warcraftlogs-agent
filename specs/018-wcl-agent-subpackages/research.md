# Research: `wcl_agent` sub-packages

## R1. Which modules stay at the top level

- **Decision**: `__init__.py`, `agent.py`, `cli.py`, `menu.py` stay.
- **Rationale**: ADK discovers an agent package by `__init__.py` importing `agent` and
  `agent.root_agent`; moving it breaks that convention. `cli.py` backs
  `wcl = "wcl_agent.cli:run"` and `main.py`, so keeping it leaves `pyproject.toml` and
  `main.py` untouched. `menu.py` is the CLI's encounter menu.
- **Alternatives**: an `app/` or `cli/` package for `cli.py` + `menu.py` (rejected: edits
  the console-script entry for no navigation gain with two files).

## R2. Package names

- **Decision**: `client`, `cache`, `tools`, `guides`, `llm`, `game` (scrum master Q1).
- **Rationale**: the story's five areas, with `llm` for "models" (avoids
  `wcl_agent.models.models` and confusion with `cache_models`) and `game` for WoW
  reference data (`constants`, `roster`, `patch`). No package shares a name with a module
  left at the same level.

## R3. Keep file basenames

- **Decision**: keep them (Q2), accepting `wcl_agent.cache.cache` and
  `wcl_agent.tools.tools`.
- **Rationale**: every `cache.get_or_load(...)` / `tools.x` attribute use stays as it is,
  so the diff is import lines only (AC 8). The risk that a stale
  `from wcl_agent import cache` now binds the package silently is closed by the AST check
  (R6).
- **Alternatives**: renames (`cache/store.py`, `tools/leaderboard.py`) go to the backlog.

## R4. Rewrite method

- **Decision**: one throwaway script (scratchpad, not committed) driven by the mapping
  table, then a hand review of the whole diff.
  - Absolute dotted references `wcl_agent.<m>` → `wcl_agent.<pkg>.<m>` and path
    references `wcl_agent/<m>.py` → `wcl_agent/<pkg>/<m>.py`, in Python, Markdown and the
    one TS comment. The regex matches only flat paths (`wcl_agent.` directly followed by a
    moved name), so it cannot apply twice.
  - `from wcl_agent import a, b as c` → one `from wcl_agent.<pkg> import ...` line per
    package, in place.
  - Relative imports inside `wcl_agent/**` are recomputed from the importing file's new
    package: same package `.m`, sibling package `..pkg.m`, top-level module `..m`; from a
    top-level module `.pkg.m`.
- **Rationale**: 90+ files with a fixed mapping; a script is exact and repeatable, and the
  checks verify it. Hand edits or sub-agents would add error surface for no gain.
- **Alternatives**: sub-agents per test-file set (suggested in the brief; not needed, see
  tasks.md), `rope`/IDE move refactoring (does not cover strings, docs and logger names).

## R5. Logger names

- **Decision**: no code change; names follow `__name__`.
- **Findings**: only the parent `wcl_agent` logger is configured
  (`backend/app/main.py` sets INFO on `backend.app` and `wcl_agent`). No child logger is
  named in app code, `.env.example`, `docker-compose.yml`, Alembic config or the
  Dockerfile. The six `caplog.at_level(logger="wcl_agent.<m>")` strings in tests are
  rewritten by R4. Accepted as no behaviour change (Q3).

## R6. Proof of no behaviour change

- **Decision**: three gates, all run after slice 3 and again before hand-off.
  1. Full suite counts equal the baseline (926 / 3 skipped / 1 deselected).
  2. `checks/import_smoke.py`: `pkgutil.walk_packages` over `wcl_agent`, import each, plus
     `backend.app.main`; any exception fails.
  3. `checks/ast_refs.py`: parse every `.py` in `wcl_agent/**`, `backend/**`, `main.py`;
     resolve each `import wcl_agent...` / `from wcl_agent... import n` (absolute and
     relative) to a module or an existing attribute; resolve each string literal that
     starts with `wcl_agent.` the same way (longest importable module prefix, then
     `getattr` chain); flag any import that binds the `wcl_agent.cache` or
     `wcl_agent.tools` package object. Zero findings required.
- Plus a text search for the old flat paths (SC-002) and `git log --follow` on each moved
  file (SC-004).

## R7. Container and boot

- **Decision**: the Dockerfile copies `wcl_agent` as a directory, so it needs no change;
  build the backend image with `docker build -f backend/Dockerfile .` (Docker 29 is
  available on this host) and boot the app with `uv run uvicorn backend.app.main:app` on a
  port assigned by the scrum master, then poll `/api/health` for ready.
