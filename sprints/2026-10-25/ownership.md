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
| backend/root `*.py` that reference `wcl_agent` at base (70 files: `grep -rl wcl_agent --include=*.py backend main.py`), import lines and patch strings only; includes `backend/app/config.py`, `backend/app/main.py` | dev-a-018 | 018 | tentative | 2026-10-25 |
| `pyproject.toml` (dependency-manifest token) | dev-a-018 | 018 | tentative | 2026-10-25 |
| `README.md`, `documentation/ai_guide.md`, `documentation/live_model_probe.md` | dev-a-018 | 018 | tentative | 2026-10-25 |
| `frontend/src/components/StreamMarkdown.tsx`, `frontend/nginx.conf`, `frontend/vite.config.ts`, new frontend test for SEC-003 | dev-b-019 | 019 | tentative | 2026-10-25 |
| `backend/app/api/auth.py`, `backend/app/services/auth_service.py`, `backend/app/auth/rate_limit.py` | dev-b-019 | 019 | tentative | 2026-10-25 |
| `backend/Dockerfile`, `docker-compose.yml`, `.env.example` | dev-b-019 | 019 | tentative | 2026-10-25 |
| `backend/tests/test_auth_login.py`, `backend/tests/test_rate_limit.py`, new auth/proxy test file | dev-b-019 | 019 | tentative | 2026-10-25 |

Conflict note (2026-10-25): F4's plan footprint lists `backend/app/config.py`, which 018
also needs (it imports `wcl_agent`). 018 holds it. 019 should avoid it (uvicorn
`--proxy-headers` with `FORWARDED_ALLOW_IPS`) or get it after 018 merges.
