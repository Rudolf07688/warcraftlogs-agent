# Implementation Plan: Restructure `wcl_agent` into sub-packages

**Branch**: `018-wcl-agent-subpackages` | **Date**: 2026-10-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/018-wcl-agent-subpackages/spec.md` (signed
off by the scrum master 2026-10-25, changes 1–4 applied).

## Summary

Move 22 of the 25 flat `wcl_agent/*.py` modules into six sub-packages (`client`, `cache`,
`tools`, `guides`, `llm`, `game`) with `git mv`, keeping every file name. `agent.py`,
`cli.py`, `menu.py` and `__init__.py` stay. Then rewrite every reference to a moved
module (relative imports inside `wcl_agent`, absolute imports, lazy imports, dotted patch
strings, logger names, path checks, comments and docs) with one deterministic rewrite
script driven by the mapping table, review the diff by hand, and prove "no behaviour
change" with the baseline test counts, an import smoke check and an AST resolution check.

## Technical Context

**Language/Version**: Python 3.14 (`requires-python >=3.14`).

**Primary Dependencies**: none touched. google-adk (agent discovery convention
`wcl_agent/__init__.py` → `agent.root_agent`), hatchling (`packages = ["wcl_agent",
"backend"]` picks up sub-packages), FastAPI app `backend.app.main:app`.

**Storage**: N/A.

**Testing**: `uv run --extra test pytest -q` (baseline 926 passed / 3 skipped /
1 deselected), plus two one-off checks kept in `specs/018-wcl-agent-subpackages/checks/`:
`import_smoke.py` (FR-006) and `ast_refs.py` (FR-012). They are not pytest tests, so the
suite's counts stay comparable (AC 4).

**Target Platform**: Linux, local `uv run` and the backend container image.

**Project Type**: Web service + CLI; this feature changes code layout only.

**Performance Goals / Constraints**: no runtime change. Constraint: the diff is moves,
reference edits, empty `__init__.py` files and doc path edits only (FR-010).

**Scale/Scope**: 22 `git mv`, 6 new `__init__.py`, 25 `wcl_agent` modules with import
edits, 66 backend files (24 app/evals + 42 tests), 3 living docs, 1 frontend comment line.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. DRY & reuse | ✅ | No shims or re-exports (decision 2): each module has exactly one path. The rewrite is driven by one mapping table (`contracts/module-map.md`), used by the rewrite script and both checks. |
| II. Step-wise delivery | ✅ | Slices: (1) `git mv` + `__init__.py` + `wcl_agent` internal imports → `wcl_agent` imports cleanly; (2) backend app/evals → app imports; (3) tests → full suite count match; (4) checks + docs + CLI/container/boot. Each slice is verified before the next. |
| III. Simplicity | ✅ | Keep file names (no renames); empty `__init__.py`; one throwaway rewrite script in the scratchpad instead of hand-editing 90 files or fanning out sub-agents. |
| IV. Typed contracts | N/A | No data crosses a new boundary. |
| V. Async backend | N/A | No runtime change. |
| VI. GitNexus | ✅ | File-level upstream `impact` run on the moved modules: `wcl_client.py` HIGH (21 direct, 84 total), `cache.py` HIGH (20 / 98), `model_retry.py` MEDIUM (11), `patch.py` MEDIUM (13). Reported to and accepted by the scrum master (inherent to moving hub files; mitigated by count match, import smoke, AST check). `detect-changes` on the re-indexed worktree before each commit. |
| VII. shadcn UI | N/A | The only frontend edit is one comment line. |
| VIII. Backlog sync | ✅ | `todo.md` line 31 is this story's bullet; the scrum master strikes it after Done. Rename ideas go to the hand-off backlog list. |

**Result**: PASS. Nothing goes under Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/018-wcl-agent-subpackages/
├── spec.md
├── plan.md               # this file
├── research.md           # decisions R1–R7
├── data-model.md         # the layout as entities (package → modules)
├── contracts/
│   └── module-map.md     # old → new import paths (the importer contract)
├── quickstart.md         # how to verify every AC
├── checks/
│   ├── import_smoke.py   # FR-006 one-off
│   └── ast_refs.py       # FR-012 one-off
├── checkpoint.md         # resume notes (written before implement)
└── tasks.md              # /speckit-tasks
```

### Source Code (repository root)

```text
wcl_agent/
├── __init__.py        # unchanged: from . import agent (ADK convention)
├── agent.py           # unchanged location
├── cli.py             # unchanged location (wcl = "wcl_agent.cli:run")
├── menu.py            # unchanged location
├── client/   __init__.py wcl_client.py queries.py aio.py
├── cache/    __init__.py cache.py cache_models.py normalize.py
├── tools/    __init__.py tools.py report_tools.py benchmark.py cooldowns.py fight_time.py provenance.py
├── guides/   __init__.py guide_meta.py guides_tool.py
├── llm/      __init__.py models.py model_retry.py vertex.py genai_compat.py context_trim.py
└── game/     __init__.py constants.py roster.py patch.py
```

**Structure Decision**: as above; full mapping in `contracts/module-map.md`.

## Files touched (the grant request)

- `wcl_agent/**`: 22 `git mv`, 6 new `__init__.py` (one-line docstring each), import and
  docstring-path edits in all moved modules plus `agent.py`, `cli.py`, `menu.py`.
- Backend app and evals (24, import/reference lines only):
  `backend/app/agent_runner.py`, `api/cache_stats.py`, `api/guides.py`, `api/reports.py`,
  `api/ws.py`, `config.py`, `main.py`, `model_state.py`, `schemas.py`,
  `services/guide.py`, `services/guide_pipeline/{briefing,checks,datasheet,llm,research}.py`,
  `services/profile_context.py`, `services/raids.py`, `services/recent_raids.py`,
  `services/report_synthesis.py`, `suggestions.py`,
  `backend/evals/guides/{__main__,adversarial,coaching,scoring}.py`.
- Backend tests (42, import/patch-string/logger/path lines only), all in `backend/tests/`:
  `conftest.py`, `wcl_fakes.py`, `test_artifacts`, `test_benchmark`,
  `test_cache_families`, `test_cache_stats`, `test_charts`, `test_coaching_brief`,
  `test_context_injection`, `test_context_trim`, `test_cooldowns`, `test_eval_scoring`,
  `test_fight_time`, `test_genai_compat`, `test_greeting`, `test_guide_meta`,
  `test_guide_pipeline_briefing`, `test_guide_pipeline_datasheet`, `test_guides_and_boot`,
  `test_guides_tool`, `test_message_report`, `test_model_discovery`, `test_model_retry`,
  `test_models`, `test_profile_context`, `test_profile`, `test_provenance`,
  `test_recent_raids`, `test_report_rankings`, `test_report_synthesis`, `test_roles`,
  `test_roster`, `test_runner_retry`, `test_spec_guides`, `test_stale_scan`,
  `test_tenant_isolation`, `test_tool_concurrency`, `test_vertex`, `test_wcl_async`,
  `test_wcl_cache`, `test_wcl_loop_lag`, `test_ws_rate_limit` (`.py` each).
- Docs: `README.md`, `documentation/ai_guide.md`, `documentation/live_model_probe.md`.
- `frontend/src/lib/classColors.ts`: the line-2 comment only.
- `specs/018-wcl-agent-subpackages/**`.
- **Not changed** (checked): `main.py` (names `wcl_agent.cli`, which stays),
  `pyproject.toml` (script entry and `packages` still right), `uv.lock`,
  `backend/Dockerfile`, `.env.example`, `docker-compose.yml`, Alembic config,
  `backend/tests/test_grounding.py`, `test_prompt_contract.py`, `test_startup.py`
  (they name only `wcl_agent.agent` or the parent logger).

## Complexity Tracking

None.
