# Quickstart: verify feature 018

All commands run from the repo root (worktree `/home/rudolf/dev/wcl-worktrees/dev-a`).

| AC | Check | Expected |
|---|---|---|
| 1 | `find wcl_agent -name '*.py' -not -path '*/__pycache__/*' \| sort` | the layout in `contracts/module-map.md` |
| 2 | `git log --follow --oneline wcl_agent/client/wcl_client.py \| tail -3` (any moved file) | commits from before the move |
| 3 | `uv run python specs/018-wcl-agent-subpackages/checks/ast_refs.py` | `0 findings` |
| 3 | `git grep -nE 'wcl_agent[./](wcl_client\|queries\|aio\|cache_models\|normalize\|report_tools\|benchmark\|cooldowns\|fight_time\|provenance\|guide_meta\|guides_tool\|models\|model_retry\|vertex\|genai_compat\|context_trim\|constants\|roster\|patch)\b' -- ':!specs' ':!sprints' ':!documentation/designs' ':!documentation/delivery' ':!documentation/wow_guide_grounding_plan_v2.md' ':!todo.md'` | no hits (`wcl_agent.cache.` / `wcl_agent.tools.` are covered by the AST check) |
| 4 | `uv run --extra test pytest -q` | `926 passed, 3 skipped, 1 deselected` |
| 5 | `uv run python specs/018-wcl-agent-subpackages/checks/import_smoke.py` | every module `ok`, `backend.app.main ok` |
| 6 | `uv run wcl --help`; `uv run python main.py --help` | same output as at base |
| 6 | `docker build -f backend/Dockerfile -t wcl-backend:018 .` | build succeeds |
| 6 | `uv run uvicorn backend.app.main:app --port <assigned>`; `curl localhost:<assigned>/api/health` | status `ready` |
| 7 | the grep above over `README.md`, `documentation/ai_guide.md`, `documentation/live_model_probe.md`, `frontend/src/lib/classColors.ts` | no hits |
| 8 | `git diff --stat <base>...HEAD` and review | only moves, import/reference lines, empty `__init__.py`, doc paths |
| — | `git diff --name-only <base>...HEAD -- uv.lock pyproject.toml` | empty |
