# Implementation Plan: Capability Summary and Profile Proposal Tools

**Branch**: `029-agent-profile-proposals` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/029-agent-profile-proposals/spec.md`

**Design (binding, cited)**: `documentation/designs/self-aware-agent/capabilities-and-tools.html`
(C1–C14, `#proposal-contract`, `#files`, `#tests`). Sprint decisions D4–D13
(`sprints/2026-10-26/decisions.md`). Research: [research.md](research.md).

## Summary

sc-204: the hand-written `<TOOLS>` list in `wcl_agent/agent.py` is replaced by a summary that
`build_agent` renders from the exact tool groups it registers (`wcl_agent/capabilities.py`).
The summary adds the can-change, cannot and app-facts lines (D13) and has a tested
4,000-character budget.

sc-205: one backend agent tool, `propose_profile_changes`. It validates the changes and
stores a tenant-, user- and conversation-bound proposal in a new `profile_proposals` table
(migration 0016, RLS), then returns the proposal. It never writes the profile. The proposal
service (create, list, get, execute, cancel) applies an approved proposal exactly once, item
by item, through a new shared `profile_service` that the REST profile routes also use. D8
adds a 50-friend cap in `repo.add_character`. C12 makes the shared identity check compare
realm slugs.

## Technical Context

**Language/Version**: Python 3.14 (backend, `wcl_agent`); TypeScript/React (one message string)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, Google ADK 2.10. No new dependency.

**Storage**: PostgreSQL (new table `profile_proposals`, RLS); SQLite in tests

**Testing**: pytest (+ pytest-asyncio), SQLite in-memory. Postgres-only tests are skipped
without `TEST_DATABASE_URL` (run manually on port 15429).

**Target Platform**: Linux server (Docker), web frontend

**Project Type**: web application (backend + frontend) with an embedded agent package (`wcl_agent`)

**Performance Goals**: the summary is static per runner, in the cacheable instruction
prefix (PERF-003). Proposal creation costs one profile read and one insert, with no WCL calls.

**Constraints**: the summary is ≤ 4,000 characters, ≤ 160 per line. 1–30 items per proposal.
TTL 30 minutes. No frames or routes (031). In ws.py, only the `current_identity` line and
its import.

**Scale/Scope**: ≤ 30 items per proposal, ≤ 10 own characters, ≤ 50 friends per tenant

## Constitution Check

*GATE: passed before Phase 0, re-checked after Phase 1. No unjustified violations.*

| Principle | Check | Status |
|---|---|---|
| I. DRY / reuse | The summary is read from ADK's own `FunctionTool` name/description (one source with the declaration). One write path (`profile_service`) for REST and proposals. Validation reuses `CharacterIn` and `server_slug`. The cap lives only in `repo.add_character`. The friend-limit UI message carries no duplicated number. | Pass |
| II. Step-wise | Tasks are grouped by story (US1 summary → US4 shared path → US2 propose → US3 execute), and each slice is verified with pytest before the next. | Pass |
| III. Simplicity | One tool, not six. One table with a JSON item list. No sweeper job (expiry computed). No idempotency-key table (row lock + status). One new table, justified below. | Pass, 1 entry in Complexity Tracking |
| IV. Typed contracts | `ProfileChangeIn`, `ProfileProposalOut` and friends are Pydantic models. `ToolGroup`, `CharacterNotFound` and `ProposalError` are dataclass/typed exceptions. Public functions are type-hinted. | Pass |
| V. Async FastAPI | Every DB call is async. The service opens its own `tenant_scope`. REST handlers are unchanged and async. | Pass |
| VI. GitNexus | Impact was run on every edited symbol (below). It runs again before each edit, and detect-changes runs before each commit. | Pass |
| VII. shadcn | No component is built or restyled: the only frontend change is one `case` string in `CharactersTab.tsx`'s existing error mapper. There is nothing to search the registry for. | Pass (N/A) |
| VIII. Backlog sync | sc-204/sc-205 are In Progress. `todo.md` is the scrum master's; 029 adds no bullets. | Pass |

### GitNexus upstream impact (shared index, base = 1da8bca code)

| Symbol | Risk | Direct callers (d=1) | Processes / notes |
|---|---|---|---|
| `wcl_agent/agent.py::build_agent` | **HIGH** | `backend/app/agent_runner.py::_get_runner`, module-level `root_agent` (CLI); tests `test_prompt_contract.py`, `test_tool_concurrency.py` | 14 impacted, 3 processes (chat via `stream_response`, greeting, guild-summary/guide flows that run the agent). The new parameter is keyword-only with a default, so existing calls are unchanged. |
| `backend/app/agent_runner.py::_get_runner` | **HIGH** | `_run_turn` → `stream_response` (chat, greeting, guides) | Only change: passes `extra_groups=(PROFILE_TOOLS,)`. Every backend runner gains the profile tool, and it fails closed outside an authenticated chat turn (greeting, guide jobs) (C7). |
| `wcl_agent/agent.py::build_instruction` | LOW | `build_agent` (provider); module `INSTRUCTION`; `test_prompt_contract.py` | The new keyword-only `capabilities=""` is backward compatible. |
| `wcl_agent/agent.py::TOOLS` | UNKNOWN, resolved by text search | `build_agent`, `backend/tests/test_tool_concurrency.py`, `backend/tests/test_prompt_contract.py` | Kept as the flattened `TOOL_GROUPS`, so the importers are unaffected. |
| `backend/app/api/profile.py::_add` | LOW | `add_own_character`, `add_friend` | REST surface unchanged (AC 4). |
| `backend/app/api/profile.py::_patch` | LOW | `patch_own_character`, `patch_friend` | same |
| `backend/app/api/profile.py::_delete` | LOW | `delete_own_character`, `delete_friend` | same |
| `backend/app/db/repository.py::add_character` | LOW | `profile.py::_add` (plus tests) | Adds the `friend_limit` check (D8). |
| `backend/app/db/repository.py::find_character_identity` | LOW | `add_character` | Realm-slug compare (C12). The case-insensitive tests still hold. |
| `backend/app/api/ws.py::_handle_turn` | LOW | `chat` | One statement plus its import (R2). |

**HIGH items raised to the scrum master** (the brief expected them): `build_agent` and
`_get_runner`. The mitigation is keyword-only additive parameters, the full
`test_prompt_contract.py` suite plus the new summary tests, and a test that builds the
backend runner's agent and finds `propose_profile_changes` in both its tools and its
summary.

## Project Structure

### Documentation (this feature)

```text
specs/029-agent-profile-proposals/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/capability-summary.md
├── contracts/proposal-tool-and-service.md
├── checklists/requirements.md
├── checkpoint.md         # written after /speckit-tasks
└── tasks.md              # /speckit-tasks
```

### Source code: exact file list (ownership request)

| # | Path | New / Modified | Change |
|---|---|---|---|
| 1 | `wcl_agent/capabilities.py` | **New** | `ToolGroup`, `render_capability_summary`, budget constants (C1–C4, D13) |
| 2 | `wcl_agent/agent.py` | Modified | `TOOL_GROUPS` (+ `TOOLS` derived), `<TOOLS>` body → `@@CAPABILITIES@@`, `build_instruction(…, capabilities=)`, `build_agent(…, extra_groups=())`, `INSTRUCTION` snapshot after `root_agent` |
| 3 | `wcl_agent/tools/tools.py` | Modified (docstrings only) | `get_selected_encounter` ("may be none in the web app"), `compare_specs` (sample_scope; top_parses are leads) |
| 4 | `wcl_agent/tools/report_tools.py` | Modified (docstrings only) | `run_wcl_graphql` ("validate the response") |
| 5 | `backend/app/agent_runner.py` | Modified | `_get_runner` passes `extra_groups=(PROFILE_TOOLS,)` |
| 6 | `backend/app/agent_tools/__init__.py` | **New** | package marker |
| 7 | `backend/app/agent_tools/profile_tools.py` | **New** | `propose_profile_changes`, `PROFILE_TOOLS` |
| 8 | `backend/app/services/profile_service.py` | **New** | shared write path (C8), `CharacterNotFound` |
| 9 | `backend/app/services/profile_proposals.py` | **New** | validator, create/list/get/execute/cancel, `ProposalError`, `PROPOSAL_TTL`, `MAX_PROPOSAL_ITEMS` |
| 10 | `backend/app/repositories/profile_proposals.py` | **New** | row helpers: insert / get (for_update) / list, tenant+user scoped (R7) |
| 11 | `backend/app/api/profile.py` | Modified | `_add`/`_patch`/`_delete` bodies call the service; routes unchanged |
| 12 | `backend/app/api/ws.py` | Modified (**2 lines**) | `current_identity.set(identity)` next to `set_refresh_actor`, and `current_identity` added to the existing `..tenancy.context` import (line 28) |
| 13 | `backend/app/tenancy/context.py` | Modified | `current_identity` ContextVar |
| 14 | `backend/app/schemas.py` | Modified | `ProfileChangeIn`, `ProposalValidation`, `ProposalItemResult`, `ProposalItemOut`, `ProfileProposalOut`, `ValidationCode` |
| 15 | `backend/app/db/models.py` | Modified | `ProfileProposal` ORM model |
| 16 | `backend/app/db/repository.py` | Modified | `MAX_FRIENDS = 50` + `friend_limit` in `add_character`; slug compare in `find_character_identity`; `CharacterConflict` docstring |
| 17 | `backend/migrations/versions/0016_profile_proposals.py` | **New** | revision `"0016_profile_proposals"`, down_revision `"0015_rescan_mplus_runs"`; table, index, RLS (Postgres) |
| 18 | `frontend/src/components/profile/CharactersTab.tsx` | Modified | `case "friend_limit"` message (D8) |
| 19 | `backend/tests/test_capabilities.py` | **New** | US1 tests |
| 20 | `backend/tests/test_prompt_contract.py` | Modified | the 4 tests listed in research R4; all other clauses unchanged |
| 21 | `backend/tests/test_profile_tools.py` | **New** | tool, declarations, fail-closed, scripted agent turn, backend agent registers the tool |
| 22 | `backend/tests/test_profile_proposals.py` | **New** | validator, service, idempotency, tenancy, expiry, per-item, guides-after-commit, REST friend_limit + slug duplicate, migration up/down (SQLite), RLS (Postgres-only) |
| 23 | `specs/029-agent-profile-proposals/**` | New | feature docs |

**Sequencing (SM, 2026-10-26)**: rows 2, 12 and 20 (`agent.py`, `ws.py`,
`test_prompt_contract.py`) are granted effective after 030 merges. Rebase onto the sprint tip
first (tasks T000). `get_report_participants` joins the "Report deep-dive" group, and 030's
`<RUN_RESOLUTION>` block stays (it names no tool).

There are no dependency or lockfile changes. Migration 0016 is the only migration (already
reserved for 029). `backend/tests/test_profile.py` is **not** touched (AC 4).

**Structure Decision**: this follows the design's `#files` list. The only choice the design
left open, proposal row helpers in `repository.py` or a new repositories module, goes to the
new `backend/app/repositories/profile_proposals.py` (R7).

## Phase outline (detail in tasks.md)

1. **US1 (sc-204)**: `capabilities.py` → `agent.py` wiring → docstring moves → tests.
2. **US4 foundation (sc-205)**: `profile_service.py` → `profile.py` on top of it → D8 cap and
   C12 slug compare in `repository.py` → `CharactersTab.tsx` message → REST tests. Then
   `test_profile.py` passes unchanged.
3. **Storage**: `ProfileProposal` model + migration 0016 + `repositories/profile_proposals.py`
   + migration test.
4. **US2**: schemas → validator + `create_proposal`/`get`/`list` → `current_identity` +
   ws.py line → tool + `PROFILE_TOOLS` + `_get_runner` registration → tool tests and the
   scripted agent turn.
5. **US3**: `execute_proposal`/`cancel_proposal` → tenancy, expiry, idempotency, per-item and
   guide-ordering tests → Postgres RLS test + manual 15429 run.
6. **Polish**: full suite vs the baseline (1066 passed / 3 skipped / 1 deselected),
   `npm run build`, GitNexus `analyze --force` + detect-changes, ownership diff check.

## Sub-agent split (proposal; approval at the tasks gate)

- **Sub-agent S1 (US1 / sc-204)**, model **sonnet**, effort **high**. Files, exclusively:
  `wcl_agent/capabilities.py`, `wcl_agent/agent.py`, `wcl_agent/tools/tools.py`,
  `wcl_agent/tools/report_tools.py`, `backend/tests/test_capabilities.py`,
  `backend/tests/test_prompt_contract.py`. It is self-contained against
  `contracts/capability-summary.md`. The `extra_groups` parameter is its deliverable.
- **Me (dev-a-029)**: every other file (sc-205, rows 5–18, 21–22), including
  `agent_runner.py`, which consumes S1's `extra_groups`. I review S1's diff, run the tests
  and commit. Sub-agents don't commit.
- Why it is safe: there is no file overlap, and the only interface is `ToolGroup` +
  `build_agent(extra_groups=)`, frozen in the contract. Why it's worth it: US1 is
  independent of the DB work and runs in parallel with phases 2–5.

## Complexity Tracking

| Addition | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| New table `profile_proposals` + migration 0016 (RLS) | Proposals must survive a reload or a restart (031 AC 4) and support a row lock for exactly-once execution, and they are tenant data (029 AC 5, 7). The row is also the audit record of agent-initiated changes (design C9). | In-process dict: lost on restart, so the card breaks after a deploy. Redis TTL: not a hard dependency (circuit breaker, LRU eviction), and no RLS. ADK session state: append-only events, no approval outside a turn, no RLS, no row lock. |
| New `backend/app/agent_tools/` package | The profile tool needs the DB and the service, so it can't live in `wcl_agent`, which must not import the backend (C6). | A tool under `wcl_agent/tools/` importing the backend: it breaks the CLI's independence and creates an import cycle through `agent_runner`. A plug-in registry: more machinery than one keyword argument. |
