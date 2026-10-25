# Feature Specification: Restructure `wcl_agent` into sub-packages

**Feature Branch**: `018-wcl-agent-subpackages`

**Created**: 2026-10-25

**Status**: Draft

**Input**: User description: "Restructure the flat wcl_agent/*.py package (25 modules, ~7 kLOC) into sub-packages along the story's lines (client, tools, guides, cache, models/llm), sc-150. Files moved with git mv to keep history; no compatibility shims at old paths; every importer updated (backend app, tests, evals, main.py, dotted monkeypatch strings, lazy imports, caplog logger names); no behaviour change (same pytest pass/fail/skip counts as base 4923785: 926 passed, 3 skipped, 1 deselected); every module imports cleanly; `uv run wcl --help` and `python main.py --help` work; container builds and app boots to ready; docs module maps (README, documentation/ai_guide.md, documentation/live_model_probe.md) updated; moves and import edits only."

Shortcut: sc-150 (5 points). Sprint plan section F1. Decisions 1 and 2 (no shims).

## Clarifications

### Session 2026-10-25

Answered by the scrum master (technical questions; spec signed off on condition of
changes 1–4, which are applied below).

- Q: Package layout? → A: `client/`, `cache/`, `tools/`, `guides/`, `llm/`, `game/`;
  `agent.py`, `cli.py`, `menu.py`, `__init__.py` stay at the top level.
- Q: Keep module basenames (`wcl_agent.cache.cache`, `wcl_agent.tools.tools`) or rename? →
  A: Keep basenames; renames go on the backlog list.
- Q: Logger names that follow `__name__` change; is that a behaviour change? → A: No,
  accepted. Every logger-name string anywhere is updated (FR-004).
- Q: Frontend comment naming `wcl_agent/constants.py`? → A: Granted to this feature:
  `frontend/src/lib/classColors.ts`, the line-2 comment only.
- Q: Which docs are living? → A: `README.md`, `documentation/ai_guide.md`,
  `documentation/live_model_probe.md`. Everything else listed is historical. The scrum
  master strikes `todo.md` line 31 when sc-150 is done.
- Change 1: `wcl_agent.cache` and `wcl_agent.tools` become packages, so a stale import of
  those two names still succeeds; an AST check guards it (FR-012, SC-006).
- Change 2–4: FR-004 covers every logger-name string, `backend/evals/**`, non-Python
  references, and the `classColors.ts` comment.

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are the developers (human and agent) who change the agent code,
and the owner who runs the app. The owner must notice nothing; developers must find code
by area instead of scanning 25 flat files.

### User Story 1 - Find agent code by area (Priority: P1)

A developer who needs to change the Warcraft Logs client, a tool, the cache, the guide
loader or the model layer opens `wcl_agent/` and sees one folder per area, with the
modules of that area inside. The history of every moved file is intact.

**Why this priority**: This is the point of the story. Every later agent feature lands in
the new layout, so it must exist first (it blocks F3, F4 and F5).

**Independent Test**: List `wcl_agent/`; check each module sits in the package the
mapping table below names; run `git log --follow` on a moved file and see its pre-move
commits.

**Acceptance Scenarios**:

1. **Given** the restructured tree, **When** a developer lists `wcl_agent/`, **Then** it
   holds only `__init__.py`, `agent.py`, `cli.py`, `menu.py` and the six sub-packages of
   the mapping table, each with an `__init__.py`.
2. **Given** any moved module, **When** `git log --follow` runs on its new path, **Then**
   the commits from before the move are listed.
3. **Given** the old flat paths, **When** anything tries to import one of the 20 moved
   modules whose name is not reused (e.g. `wcl_agent.wcl_client`), **Then** the import
   fails: no module or re-export is left at an old path.
4. **Given** `wcl_agent.cache` and `wcl_agent.tools`, which now name packages, **When**
   code uses an old attribute path such as `wcl_agent.cache.get_or_load` or
   `wcl_agent.tools.find_encounter`, **Then** it fails (the packages export
   nothing), and the AST check of FR-012 reports zero imports that bind either package as
   a module object.

---

### User Story 2 - Nothing changes for the owner (Priority: P1)

The owner runs the web app, the `wcl` console command and `python main.py` exactly as
before, and every feature behaves the same.

**Why this priority**: A refactor that changes behaviour is a defect (AC 4, AC 8). Equal
to US1 because the move is only acceptable if it is invisible.

**Independent Test**: Run the full backend test suite and compare counts with the
baseline; run the import smoke check; run both CLI help commands; build the backend image
and boot the app to ready.

**Acceptance Scenarios**:

1. **Given** the restructured tree, **When** the full backend suite runs, **Then** it
   reports exactly 926 passed, 3 skipped, 1 deselected, 0 failed (baseline at base
   `4923785` / sprint tip `4f748c3`).
2. **Given** the restructured tree, **When** a one-off check imports every `wcl_agent`
   module and `backend.app.main`, **Then** every import succeeds.
3. **Given** the restructured tree, **When** `uv run wcl --help` and
   `python main.py --help` run, **Then** both behave as at base.
4. **Given** the restructured tree, **When** the backend image is built and the app is
   started on an assigned non-default port, **Then** `/api/health` reports ready.

---

### User Story 3 - Docs match the code (Priority: P2)

A developer or agent reading `documentation/ai_guide.md`, `README.md` or
`documentation/live_model_probe.md` finds the new paths, including the file map.

**Why this priority**: Stale module maps send agents to files that no longer exist, but
the code works without them.

**Independent Test**: Search the living docs for every old flat path
(`wcl_agent/<module>.py`, `wcl_agent.<module>`) of a moved module; none remain.

**Acceptance Scenarios**:

1. **Given** the living docs, **When** they are searched for old paths of moved modules,
   **Then** there are no hits; historical `specs/0xx` and the docs classed as historical
   below are untouched.

---

### Edge Cases

- **Name collisions**: a package must not share a name with a module at the same level
  (no `cache/` next to `cache.py`). Every moved module leaves the top level, so no package
  sits next to a same-named module.
- **Dotted patch strings**: tests that patch `"wcl_agent.model_retry.random.uniform"`,
  `"wcl_agent.vertex.genai_client"` and `"wcl_agent.report_tools.get_character_zone_rankings"`
  must point at the new dotted path, or they silently patch nothing (or fail to resolve).
- **Lazy imports inside functions** (`cli.py`, `constants.py`, `roster.py`, test helpers,
  `backend/evals/guides/*`) are only exercised when the function runs; the import smoke
  check alone does not catch them, so they are found by text search.
- **Logger names** follow `__name__`, so `wcl_agent.models` becomes
  `wcl_agent.llm.models` and so on. The app configures the parent `wcl_agent` logger,
  which still covers every child. Tests using `caplog.at_level(logger="wcl_agent.<m>")`
  must use the new names.
- **File-path checks in tests**: `test_vertex.py` scans `wcl_agent/` and exempts
  `wcl_agent/vertex.py` by path; the exemption must follow the move.
- **Mixed imports**: lines like `from wcl_agent import patch, report_tools` name modules
  that now live in different packages and must be split.
- **Import cycles**: the modules already import each other (e.g. `constants` ↔ `roster`
  lazily, `benchmark` → `report_tools`). Sub-package `__init__.py` files stay empty, so no
  new import edges and no new cycles are introduced.
- **ADK convention**: `wcl_agent/__init__.py` does `from . import agent` and `agent.py`
  exposes `root_agent`; both stay where they are so ADK tooling still finds the agent.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The modules MUST be grouped exactly as the mapping table below states.
  Module file names are kept; only their directory changes.
- **FR-002**: Every move MUST be a `git mv`, so `git log --follow` keeps history.
- **FR-003**: No compatibility shim, alias module or re-export MAY remain at an old path,
  and new sub-package `__init__.py` files MUST NOT re-export anything (a one-line package
  docstring is allowed).
- **FR-004**: Every reference to a moved module MUST be updated: absolute and relative
  imports in `wcl_agent/**`, imports in `backend/**` (app, tests, `backend/evals/**`) and
  `main.py`, lazy imports inside functions, dotted strings passed to
  `monkeypatch.setattr` / `mock.patch`, every logger-name string (`caplog` logger names,
  `getLogger("wcl_agent.<m>")`, `setLevel` targets, logging config, `.env.example`,
  `docker-compose.yml`, docs), file-path checks in tests, non-Python references
  (`python -m wcl_agent.<m>` in docs or scripts, Alembic and ADK config), and
  comments/docstrings that name an old module path (`wcl_agent.x` or `wcl_agent/x.py`),
  including the line-2 comment of `frontend/src/lib/classColors.ts`.
  Findings at base (2026-10-25): the only logger configured in code is the parent
  `wcl_agent` (`backend/app/main.py` sets INFO on `backend.app` and `wcl_agent`); no
  child logger is named in app code, `.env.example`, `docker-compose.yml`, Alembic
  config or the Dockerfile; no `python -m wcl_agent.<m>` invocation exists; the only
  child logger names are six `caplog.at_level(logger=...)` strings in tests. So no
  level changes for any logger after the move.
- **FR-005**: There MUST be no behaviour change: the full backend suite gives the same
  pass/fail/skip/deselect counts as the baseline (926 / 0 / 3 / 1).
- **FR-006**: Every `wcl_agent` module and `backend.app.main` MUST import without error;
  the check's output goes in the hand-off notes.
- **FR-007**: The `wcl` console script (`pyproject.toml`) and `python main.py` MUST keep
  working; `--help` output is unchanged.
- **FR-008**: The backend container image MUST build (the Dockerfile copies `wcl_agent/`
  as a directory and needs no change), and the app MUST boot to ready on `/api/health`.
- **FR-009**: `README.md`, `documentation/ai_guide.md` (including the §4 file map) and
  `documentation/live_model_probe.md` MUST name the new paths, as must the line-2
  comment of `frontend/src/lib/classColors.ts`. Historical files
  (`specs/0xx`, `documentation/designs/*`, `documentation/delivery/*`,
  `documentation/wow_guide_grounding_plan_v2.md`) are left alone.
- **FR-010**: The diff MUST contain only moves, import/reference edits, the new empty
  `__init__.py` files and doc path edits. Improvements spotted on the way go to the
  backlog list in the hand-off, not into the diff.
- **FR-011**: No dependency changes: `uv.lock` MUST be unchanged.
- **FR-012**: A one-off AST check MUST walk `wcl_agent/**`, `backend/**` and `main.py`,
  resolve every `from wcl_agent... import name` / `import wcl_agent...` against the new
  tree (the name must be a module or an attribute that exists), resolve every dotted
  `wcl_agent.x.y` string literal the same way, and report zero imports that bind the
  `wcl_agent.cache` or `wcl_agent.tools` package as a module object. Its output goes in
  the hand-off notes. This guard is what makes keeping those two names safe.

### Module mapping (old → new)

Rule: an area with several modules becomes a package; the three top-level entry points
(ADK agent, console entry, interactive menu) stay put.

| Old path | New path | Package purpose |
|---|---|---|
| `wcl_agent/__init__.py` | unchanged | ADK convention (`from . import agent`) |
| `wcl_agent/agent.py` | unchanged | ADK `root_agent` |
| `wcl_agent/cli.py` | unchanged | `wcl` console entry point |
| `wcl_agent/menu.py` | unchanged | CLI encounter menu (+ `load_world_zones`) |
| `wcl_agent/wcl_client.py` | `wcl_agent/client/wcl_client.py` | **client**: Warcraft Logs API access |
| `wcl_agent/queries.py` | `wcl_agent/client/queries.py` | client |
| `wcl_agent/aio.py` | `wcl_agent/client/aio.py` | client |
| `wcl_agent/cache.py` | `wcl_agent/cache/cache.py` | **cache**: shared Redis WCL cache |
| `wcl_agent/cache_models.py` | `wcl_agent/cache/cache_models.py` | cache |
| `wcl_agent/normalize.py` | `wcl_agent/cache/normalize.py` | cache (key/finality helpers) |
| `wcl_agent/tools.py` | `wcl_agent/tools/tools.py` | **tools**: ADK function tools over WCL |
| `wcl_agent/report_tools.py` | `wcl_agent/tools/report_tools.py` | tools |
| `wcl_agent/benchmark.py` | `wcl_agent/tools/benchmark.py` | tools |
| `wcl_agent/cooldowns.py` | `wcl_agent/tools/cooldowns.py` | tools |
| `wcl_agent/fight_time.py` | `wcl_agent/tools/fight_time.py` | tools |
| `wcl_agent/provenance.py` | `wcl_agent/tools/provenance.py` | tools (result envelope) |
| `wcl_agent/guide_meta.py` | `wcl_agent/guides/guide_meta.py` | **guides**: coaching briefs |
| `wcl_agent/guides_tool.py` | `wcl_agent/guides/guides_tool.py` | guides |
| `wcl_agent/models.py` | `wcl_agent/llm/models.py` | **llm**: chat models (story's "models") |
| `wcl_agent/model_retry.py` | `wcl_agent/llm/model_retry.py` | llm |
| `wcl_agent/vertex.py` | `wcl_agent/llm/vertex.py` | llm |
| `wcl_agent/genai_compat.py` | `wcl_agent/llm/genai_compat.py` | llm |
| `wcl_agent/context_trim.py` | `wcl_agent/llm/context_trim.py` | llm |
| `wcl_agent/constants.py` | `wcl_agent/game/constants.py` | **game**: WoW reference data |
| `wcl_agent/roster.py` | `wcl_agent/game/roster.py` | game |
| `wcl_agent/patch.py` | `wcl_agent/game/patch.py` | game |

Names: the story's "models" package is named `llm`, because a `models` package holding
`models.py` (model discovery) would read as `wcl_agent.models.models` and be easy to
confuse with the cache's Pydantic value models. `game` is added for the static and live
WoW reference data, which fits none of the story's five areas.

### Key Entities

- **Sub-package**: a folder under `wcl_agent/` with an empty `__init__.py`, grouping the
  modules of one area.
- **Importer**: any file that names a moved module (import, lazy import, dotted patch
  string, logger name, path check, doc path).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The backend suite reports 926 passed, 3 skipped, 1 deselected, 0 failed,
  identical to the baseline.
- **SC-002**: 0 references to an old flat module path remain in `wcl_agent/**`,
  `backend/**`, `main.py`, `pyproject.toml`, the living docs and the `classColors.ts`
  comment (text search).
- **SC-003**: 100% of `wcl_agent` modules plus `backend.app.main` import without error.
- **SC-004**: All 22 moved files show their pre-move history under `git log --follow`.
- **SC-005**: `wcl --help`, `python main.py --help`, the image build and the boot to
  ready all succeed (or, where the host can't run one, the hand-off says so explicitly).
- **SC-006**: The FR-012 AST check reports 0 unresolved imports, 0 unresolved dotted
  strings and 0 module-object imports of `wcl_agent.cache` / `wcl_agent.tools`.

## Assumptions

- Baseline (recorded 2026-10-25 at sprint tip `4f748c3`, code identical to `4923785`):
  `uv run --extra test pytest -q` → **926 passed, 3 skipped, 1 deselected, 3 warnings**.
  The one deselected test is the `perf`-marked
  `test_wcl_loop_lag.py::test_loop_lag_while_four_turns_pull_large_payloads`, which also
  fails at base when run with `-m perf` (timing-sensitive; not part of the comparison).
- Log record names change with the module paths (e.g. `wcl_agent.llm.models`). This is not
  a behaviour change: the app configures the parent `wcl_agent` logger, so levels and
  handlers apply as before. Only the logger name printed in each line differs.
- Frontend comments that name `wcl_agent/constants.py` and `wcl_agent/agent.py`
  (`frontend/src/lib/classColors.ts`, `frontend/src/lib/spells.ts`) sit in track B's
  area. `agent.py` does not move, so `spells.ts` needs nothing; the `classColors.ts`
  line-2 comment is granted to this feature (comment only).
- `todo.md` line "Unstructured directory `./wcl_agent/*.py`" is this story's source
  bullet; it is the scrum master's to strike after Done, not a path to rewrite.
- The Dockerfile `COPY wcl_agent ./wcl_agent` and `pyproject.toml`
  (`packages = ["wcl_agent", "backend"]`, `wcl = "wcl_agent.cli:run"`) need no change,
  because `cli.py` stays and hatchling includes sub-packages.
