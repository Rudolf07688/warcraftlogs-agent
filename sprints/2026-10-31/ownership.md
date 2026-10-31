# File ownership ledger — sprint 2026-10-31

Single source of truth for who may edit what (scrum-master role §2). A path is granted
to at most one owner at a time. Status: tentative (from brief footprint) → granted
(after `/speckit-plan` file list) → released (feature merged).

Sprint branch: `sprint-2026-10-31` (base `b963463`). Worktrees: track A
`/home/rudolf/dev/wcl-worktrees/dev-a`, track B `/home/rudolf/dev/wcl-worktrees/dev-b`.
Feature numbers start at **032**.

## Standing ownership

| Path or glob | Owner | Feature | Status | Since |
|---|---|---|---|---|
| `CLAUDE.md` | scrum-master | — | granted | 2026-10-31 |
| `AGENTS.md` | scrum-master | — | granted | 2026-10-31 |
| `todo.md` | scrum-master | — | granted | 2026-10-31 |
| `.specify/memory/constitution.md` | scrum-master | — | granted | 2026-10-31 |
| `.specify/feature.json` | scrum-master | — | granted | 2026-10-31 |
| `sprints/2026-10-31/ownership.md`, `log.md`, `briefs/**` | scrum-master | — | granted | 2026-10-31 |
| `sprints/2026-10-31/plan.md`, `decisions.md` | product-owner | — | granted | 2026-10-31 |
| `pyproject.toml`, `uv.lock` | (one dev at a time; ask) | — | unassigned | 2026-10-31 |
| `frontend/package.json`, `frontend/package-lock.json` | (one dev at a time; ask) | — | unassigned | 2026-10-31 |
| new `backend/migrations/versions/*` | (scrum master assigns revision; next is `0017_*`, down_revision `"0016_profile_proposals"`) | — | unassigned | 2026-10-31 |
| branch `parked/sc-157-158-security-spec` | — | — | never merge | 2026-10-31 |

## Feature grants

| Path or glob | Owner | Feature | Status | Since |
|---|---|---|---|---|
| `specs/032-llm-provider-switch/**` | dev-a-032 | 032 | granted | 2026-10-31 |
| `specs/034-epic203-qa-fixes/**` | dev-b-034 | 034 | released (merged 6e5cef7) | 2026-10-31 |
| `backend/app/schemas.py` (`ProfileChangeIn` class only; 033 later `ModelsResponse`) | dev-b-034 | 034 | released (merged 6e5cef7) | 2026-10-31 |
| `backend/app/services/profile_proposals.py` | dev-b-034 | 034 | released (merged 6e5cef7) | 2026-10-31 |
| `backend/app/agent_tools/profile_tools.py` | dev-b-034 | 034 | released (merged 6e5cef7) | 2026-10-31 |
| `backend/app/api/proposals.py` | dev-b-034 | 034 | released (merged 6e5cef7) | 2026-10-31 |
| `frontend/src/App.tsx` | dev-b-034 | 034 | released (merged 6e5cef7) | 2026-10-31 |
| `frontend/src/toolLabels.ts`, `frontend/src/lib/spells.ts` | dev-b-034 | 034 | released (merged 6e5cef7) | 2026-10-31 |
| `backend/tests/test_profile_tools.py`, `test_profile_proposals.py`, `test_proposal_routes.py` | dev-b-034 | 034 | released (merged 6e5cef7) | 2026-10-31 |
| `backend/tests/test_proposal_race_pg.py` (new), `frontend/src/App.test.tsx` (new) | dev-b-034 | 034 | released (merged 6e5cef7) | 2026-10-31 |
| ~~`backend/app/db/repository.py`~~ | — | 034 | released (not needed) | 2026-10-31 |
| `frontend/src/App.tsx`, `toolLabels.ts`, `lib/spells.ts`, `App.test.tsx` (within dev-b-034's grant) | dev-b-034/sub-1 (sonnet/high, T014–T018) | 034 | released (merged 6e5cef7) | 2026-10-31 |
| `wcl_agent/llm/provider.py` (new) | dev-a-032 | 032 | granted | 2026-10-31 |
| `wcl_agent/llm/vertex.py` (builders move out; forwarders) | dev-a-032 (033/035 delete forwarder use after merge) | 032 | granted | 2026-10-31 |
| `wcl_agent/llm/model_retry.py` (`RetryingClaude` only) | dev-a-032 (then 033) | 032 | granted | 2026-10-31 |
| `wcl_agent/agent.py` | dev-a-032 | 032 | granted | 2026-10-31 |
| `backend/app/config.py` | dev-a-032 (then 033) | 032 | granted | 2026-10-31 |
| `backend/app/greeting.py` | dev-a-032 | 032 | granted | 2026-10-31 |
| `backend/app/main.py` (`_boot` only; `_load_models` is 033's) | dev-a-032 | 032 | granted | 2026-10-31 |
| `backend/app/model_state.py` | dev-a-032 | 032 | granted | 2026-10-31 |
| `backend/app/api/ws.py` (`chat()` invalid_model branch only) | dev-a-032 | 032 | granted | 2026-10-31 |
| `backend/tests/test_llm_provider.py`, `test_llm_provider_agent.py`, `test_llm_provider_app.py` (new), `backend/tests/test_vertex.py` | dev-a-032 | 032 | granted | 2026-10-31 |
| `frontend/src/App.modelFallback.test.tsx` (new) | dev-a-032 | 032 | granted | 2026-10-31 |
| `.env.example`, `README.md` (provider section) | dev-a-032 (then 033/035 lines) | 032 | granted | 2026-10-31 |
