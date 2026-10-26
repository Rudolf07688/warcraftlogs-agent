# File ownership ledger — sprint 2026-10-26

Single source of truth for who may edit what (scrum-master role §2). A path is granted
to at most one owner at a time. Status: tentative (from brief footprint) → granted
(after `/speckit-plan` file list) → released (feature merged).

Sprint branch: `sprint-2026-10-26` (base `cf370e8`). Worktrees: track A
`/home/rudolf/dev/wcl-worktrees/dev-a`, track B `/home/rudolf/dev/wcl-worktrees/dev-b`.
Feature numbers start at **027** (026 was used by the architecture-docs branch).

## Standing ownership

| Path or glob | Owner | Feature | Status | Since |
|---|---|---|---|---|
| `CLAUDE.md` | scrum-master | — | granted | 2026-10-26 |
| `AGENTS.md` | scrum-master | — | granted | 2026-10-26 |
| `todo.md` | scrum-master | — | granted | 2026-10-26 |
| `.specify/memory/constitution.md` | scrum-master | — | granted | 2026-10-26 |
| `.specify/feature.json` | scrum-master | — | granted | 2026-10-26 |
| `sprints/2026-10-26/ownership.md`, `log.md`, `briefs/**` | scrum-master | — | granted | 2026-10-26 |
| `sprints/2026-10-26/plan.md`, `decisions.md` | product-owner | — | granted | 2026-10-26 |
| `pyproject.toml`, `uv.lock` | (one dev at a time; ask) | — | unassigned | 2026-10-26 |
| `frontend/package.json`, `frontend/package-lock.json` | (one dev at a time; ask) | — | unassigned | 2026-10-26 |
| new `backend/migrations/versions/*` | (scrum master assigns revision; next is `0016_*`, down_revision `"0015_rescan_mplus_runs"`) | — | unassigned | 2026-10-26 |
| branch `parked/sc-157-158-security-spec` | — | — | never merge | 2026-10-26 |

## Feature grants

| Path or glob | Owner | Feature | Status | Since |
|---|---|---|---|---|
| `documentation/designs/self-aware-agent/index.html` | dev-a-027 | 027 | released (merged 3a698b0) | 2026-10-26 |
| `documentation/designs/self-aware-agent/capabilities-and-tools.html` (incl. the proposal-contract table, single definition) | dev-a-027 | 027 | released (merged 3a698b0) | 2026-10-26 |
| `documentation/designs/self-aware-agent/participants-and-confirmation.html` | dev-b-028 | 028 | released (merged de66579) | 2026-10-26 |
| `backend/app/api/ws.py` — **one line** in `_handle_turn` setting `current_identity` (no frames) | dev-a-029 | 029 | tentative | 2026-10-26 |
| `backend/app/api/ws.py` — 030 preamble change only if needed (`_build_turn_preamble`) | dev-b-030 | 030 | tentative, after 029 merges | 2026-10-26 |
| `backend/app/api/ws.py` — proposal frame + message_seq assignment | dev-b-031 (future) | 031 | tentative, **after 029 and 030 merge** | 2026-10-26 |
| `frontend/package.json`, `frontend/package-lock.json` (vitest, @testing-library/react, jsdom dev deps) | dev-b-031 (future) | 031 | tentative | 2026-10-26 |
| `backend/migrations/versions/0016_*` (profile_proposals, down_revision `0015_rescan_mplus_runs`) | dev-a-029 | 029 | tentative | 2026-10-26 |
