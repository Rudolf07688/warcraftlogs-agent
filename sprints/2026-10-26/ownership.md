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
| `frontend/package.json`, `frontend/package-lock.json` | dev-b-031 (vitest, @testing-library/react, @testing-library/dom, jsdom dev deps + `test` script) | 031 | granted | 2026-10-26 |
| new `backend/migrations/versions/*` | (scrum master assigns revision; next is `0016_*`, down_revision `"0015_rescan_mplus_runs"`) | — | unassigned | 2026-10-26 |
| branch `parked/sc-157-158-security-spec` | — | — | never merge | 2026-10-26 |

## Feature grants

| Path or glob | Owner | Feature | Status | Since |
|---|---|---|---|---|
| `documentation/designs/self-aware-agent/index.html` | dev-a-027 | 027 | released (merged 3a698b0) | 2026-10-26 |
| `documentation/designs/self-aware-agent/capabilities-and-tools.html` (incl. the proposal-contract table, single definition) | dev-a-027 | 027 | released (merged 3a698b0) | 2026-10-26 |
| `documentation/designs/self-aware-agent/participants-and-confirmation.html` | dev-b-028 | 028 | released (merged de66579) | 2026-10-26 |
| `backend/app/api/ws.py` — **two lines**: `current_identity.set(identity)` in `_handle_turn` + the name added to the existing `..tenancy.context` import (no frames) | dev-a-029 | 029 | released (merged a7d550b) | 2026-10-26 |
| `backend/app/api/ws.py` — `_build_turn_preamble` (two reads + kwargs) | dev-b-030 | 030 | released (merged 1685bd5) | 2026-10-26 |
| `backend/migrations/versions/0016_profile_proposals.py` (revision `0016_profile_proposals`, down_revision `0015_rescan_mplus_runs`) | dev-a-029 | 029 | released (merged a7d550b) | 2026-10-26 |
| `wcl_agent/tools/participants.py` (new), `backend/app/services/profile_context.py`, `backend/app/services/raids.py`, `frontend/src/toolLabels.ts`, `frontend/src/lib/spells.ts`, `backend/tests/test_participants_tool.py` (new), `backend/tests/test_profile_context.py`, `specs/030-participant-resolution/**` | dev-b-030 | 030 | released (merged 1685bd5) | 2026-10-26 |
| `wcl_agent/agent.py` (one TOOLS entry + `<RUN_RESOLUTION>`, no tool names), `backend/tests/test_prompt_contract.py` | dev-b-030 | 030 | released (merged 1685bd5) | 2026-10-26 |
| `wcl_agent/capabilities.py` (new), `wcl_agent/tools/tools.py` + `wcl_agent/tools/report_tools.py` (docstrings only), `backend/app/agent_runner.py`, `backend/app/agent_tools/{__init__,profile_tools}.py` (new), `backend/app/services/profile_service.py` (new), `backend/app/services/profile_proposals.py` (new), `backend/app/repositories/profile_proposals.py` (new), `backend/app/api/profile.py` (`_add`/`_patch`/`_delete` bodies), `backend/app/tenancy/context.py`, `backend/app/schemas.py`, `backend/app/db/models.py`, `backend/app/db/repository.py` (D8 + C12 only), `frontend/src/components/profile/CharactersTab.tsx` (one `friend_limit` case), `backend/tests/test_{capabilities,profile_tools,profile_proposals}.py` (new), `specs/029-agent-profile-proposals/**` | dev-a-029 | 029 | released (merged a7d550b) | 2026-10-26 |
| `wcl_agent/agent.py`, `backend/tests/test_prompt_contract.py` | dev-a-029 | 029 | released (merged a7d550b) | 2026-10-26 |
| sub-agent files: `wcl_agent/capabilities.py`, `wcl_agent/agent.py`, `wcl_agent/tools/tools.py`, `wcl_agent/tools/report_tools.py` (docstrings), `backend/tests/test_capabilities.py`, `backend/tests/test_prompt_contract.py` (T009–T015) | dev-a-029/sub-1 (sonnet/high) | 029 | released (merged a7d550b) | 2026-10-26 |
| `frontend/vitest.config.ts` (new), `frontend/src/styles.css`, `frontend/src/types.ts`, `frontend/src/api/wsClient.ts`, `frontend/src/api/restClient.ts`, `frontend/src/lib/profileEvents.ts` (new), `frontend/src/components/ProposalCard.tsx` + `ProposalCard.test.tsx` (new), `frontend/src/components/MessageList.tsx`, `frontend/src/App.tsx`, `frontend/src/components/WelcomePanel.tsx`, `specs/031-confirmation-card/**` | dev-b-031 | 031 | granted | 2026-10-26 |
| `backend/app/api/ws.py` (`_handle_tool_end` frame, `_handle_turn` link at done), `backend/app/schemas.py` (ProposalFrame, ProposalDecisionOut, ConversationDetail.proposals), `backend/app/api/proposals.py` (new), `backend/app/main.py` (one include_router), `backend/app/api/conversations.py`, `backend/app/repositories/profile_proposals.py` (one `set_message_seq` helper), `frontend/src/components/profile/CharactersTab.tsx` (subscribe + export ClassAvatar), `backend/tests/test_proposal_{ws,routes}.py` (new) | dev-b-031 | 031 | granted (029 merged a7d550b; editable after rebase) | 2026-10-26 |
| `backend/app/db/timestamps.py` (new, `as_utc`; D15) | dev-a-029 | 029 | released (merged a7d550b) | 2026-10-26 |
| `frontend/src/components/profile/ClassAvatar.tsx` (new; ClassAvatar moved out of CharactersTab so the chat bundle doesn't pull in the lazy profile page) | dev-b-031 | 031 | granted | 2026-10-26 |
