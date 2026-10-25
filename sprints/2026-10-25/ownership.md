# File ownership ledger — sprint 2026-10-25

Single source of truth for who may edit what (scrum-master role §2). A path is granted
to at most one owner at a time. Status: tentative (from brief footprint) → granted
(after `/speckit-plan` file list) → released (feature merged).

Sprint branch: `sprint-2026-10-25` (base `4923785`). Worktrees: track A
`/home/rudolf/dev/wcl-worktrees/dev-a`, track B `/home/rudolf/dev/wcl-worktrees/dev-b`.

## Standing ownership

| Path or glob | Owner | Feature | Status | Since |
|---|---|---|---|---|
| `CLAUDE.md` | scrum-master | — | granted | 2026-10-25 |
| `AGENTS.md` | scrum-master | — | granted | 2026-10-25 |
| `todo.md` | scrum-master | — | granted | 2026-10-25 |
| `.specify/memory/constitution.md` | scrum-master | — | granted | 2026-10-25 |
| `.specify/feature.json` | scrum-master | — | granted | 2026-10-25 |
| `sprints/2026-10-25/ownership.md`, `log.md`, `briefs/**` | scrum-master | — | granted | 2026-10-25 |
| `sprints/2026-10-25/plan.md`, `decisions.md` | product-owner | — | granted | 2026-10-25 |
| `pyproject.toml`, `uv.lock` | (one dev at a time; ask) | — | unassigned | 2026-10-25 |
| `frontend/package.json`, `frontend/package-lock.json` | (one dev at a time; ask) | — | unassigned | 2026-10-25 |
| new `backend/migrations/versions/*` | (scrum master assigns revision; next is `0012_*`, down_revision `"0011_guide_content_types"`) | — | unassigned | 2026-10-25 |

## Feature grants

| Path or glob | Owner | Feature | Status | Since |
|---|---|---|---|---|
| `wcl_agent/**` | dev-a-018 | 018 | tentative | 2026-10-25 |
| backend/root `*.py` that reference `wcl_agent` at base (70 files: `grep -rl wcl_agent --include=*.py backend main.py`), import lines and patch strings only. Includes `backend/app/config.py`, `backend/app/main.py`, `backend/app/schemas.py`, `backend/app/api/ws.py`, `backend/app/agent_runner.py`, `backend/tests/test_tenant_isolation.py` | dev-a-018 | 018 | tentative | 2026-10-25 |
| `pyproject.toml` (dependency-manifest token) | dev-a-018 | 018 | tentative | 2026-10-25 |
| `README.md`, `documentation/ai_guide.md`, `documentation/live_model_probe.md` | dev-a-018 | 018 | tentative | 2026-10-25 |
| `frontend/src/components/Sidebar.tsx`, `frontend/src/App.tsx`, `frontend/src/types.ts`, `frontend/src/api/restClient.ts`, new frontend components and shadcn `ui/*` adds (to be listed) | dev-b-019-v2 | 019 | tentative | 2026-10-25 |
| `backend/app/api/conversations.py`, `backend/app/db/models.py`, `backend/app/db/repository.py` | dev-b-019-v2 | 019 | tentative | 2026-10-25 |
| `backend/migrations/versions/0012_*.py` (down_revision `0011_guide_content_types`) | dev-b-019-v2 | 019 | tentative | 2026-10-25 |
| new `backend/tests/test_conversation_*.py`, new `backend/app/services/<title service>.py` | dev-b-019-v2 | 019 | tentative | 2026-10-25 |
| phase 2: `backend/app/schemas.py`, `backend/app/api/ws.py` or `backend/app/agent_runner.py` | dev-b-019-v2 | 019 | queued: after 018 merges | 2026-10-25 |
| next in line: `backend/app/agent_runner.py`, `backend/app/api/ws.py`, `wcl_agent` model_retry/models | F4 / 021 | 021 | queued: after 019 sc-155 merges | 2026-10-25 |
| next in line: `wcl_agent` WCL client/queries/cache | F3 / 020 then F5 / 022 | 020, 022 | queued: after 018 (F3), after 020 (F5) | 2026-10-25 |
| migration slots | 0012 → 019, 0013 → 020, 0014 → 022 (only if needed) | — | assigned | 2026-10-25 |

## Withdrawn

| Path or glob | Owner | Feature | Status | Since |
|---|---|---|---|---|
| F4-security footprint (StreamMarkdown, nginx.conf, vite.config.ts, auth.py, auth_service.py, rate_limit.py, Dockerfile, docker-compose.yml, .env.example, auth tests) | dev-b-019 | 019-security (withdrawn) | released | 2026-10-25 |

Note: plan revision 2 (decision 8) took sc-157 and sc-158 out of the sprint. The
security brief moved to `briefs/withdrawn/`.
