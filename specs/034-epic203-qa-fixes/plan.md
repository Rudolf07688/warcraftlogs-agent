# Implementation Plan: Crucial epic-203 QA fixes (profile proposals)

**Branch**: `034-epic203-qa-fixes` | **Date**: 2026-10-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/034-epic203-qa-fixes/spec.md` (signed off 2026-10-31)

## Summary

Three fixes to one flow (propose → card → approve), each at its root cause:

- **sc-241**: ADK 2.10 converts `list[ProfileChangeIn]` one item at a time and passes an item
  that fails conversion through as a raw `dict` (verified: realm `None` and played_role
  "Healer" both arrive as dicts). The proposal service now validates each item itself, whether
  it arrives as a model or a raw value: blank or missing realm/region → `invalid_realm` /
  `invalid_region`, anything else unparseable → `invalid_item`, each as its own skipped row.
  Roles are lower-cased before validation (an unknown `played_role` is dropped). The tool keeps
  its declared schema and gains a catch-all that returns a plain `{"status": "error"}`.
- **sc-242**: `execute_proposal` / `cancel_proposal` take an optional in-transaction hook that
  only the call that moves the proposal out of `pending` runs, under the row's `FOR UPDATE`
  lock. The approve/cancel route uses it to save the follow-up line in that same transaction
  and stops reading the proposal before the lock.
- **sc-243**: `App.tsx` records the turn's conversation id from the `meta` frame and attaches a
  turn's proposals (on `done`) or loose cards (on `error`) only when that conversation is the
  open chat, replacing a loose copy loaded by a mid-turn reopen. `toolLabels.ts` and
  `lib/spells.ts` get a `propose_profile_changes` entry.

No contract change for the frontend, no migration, no new dependency.

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript 5.5 + React 19 (frontend)

**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy async, google-adk 2.10 (existing). No
new dependency.

**Storage**: Postgres in production (`profile_proposals`, `messages`); SQLite in the default test
suite. No migration.

**Testing**: pytest (`uv run --extra test pytest -q`); one Postgres-only concurrency test that
self-skips without `TEST_DATABASE_URL` (run on a throwaway Postgres on port 15434); vitest +
jsdom for the frontend (`npm test`, `npm run build` in `frontend/`).

**Target Platform**: Linux server (Docker) + evergreen browsers.

**Project Type**: Web application (`backend/` + `frontend/`).

**Performance Goals**: No change. The route drops one read transaction per decision.

**Constraints**: The model-facing tool declaration must not change (FR-002; the existing
declaration test pins it). The proposal contract (`ProfileProposalOut`, item rows, codes, the
decision response) stays as 029/031 defined it (FR-011). Fakes only; no live model or WCL.

**Scale/Scope**: ≤ 30 items per proposal (unchanged). Five source files, four test files plus two
new ones.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. DRY / reuse | Pass | Reuses `_check`, `_validate`, `_MESSAGES`, `_CLIP`, `repo.add_message`, `follow_up_text`, the existing loose-card state. One blank check (`_blank`) serves both the model and the raw-dict path. No parallel validator. |
| II. Small verified steps | Pass | Three independent slices (US1 backend, US2 backend, US3 frontend), each with its own tests run before the next. |
| III. Simplicity | Pass | No new layer: a parse step in front of the existing validator, one optional keyword argument (hook) on two service functions, one ref in `App.tsx`. Rejected heavier options in research.md. |
| IV. Typed contracts | Pass | Raw tool input is validated at the edge (the service's per-item parse) into `ProfileChangeIn`; internal code keeps trusting typed models. The hook is a typed `Callable`. |
| V. Async FastAPI | Pass | All DB work stays async inside `tenant_scope`. |
| VI. GitNexus | Pass | Impact run on every symbol to edit (below). `ProfileChangeIn` is flagged HIGH/CRITICAL by import fan-out; real users are confirmed by text search. |
| VII. shadcn | N/A | No component built or restyled; `App.tsx` state logic and two data tables (labels, spells) only. |
| VIII. Backlog sync | Pass | Stories sc-241/242/243 In Progress; the scrum master moves them. No `todo.md` edit (scrum master's file). |

### GitNexus impact (upstream, index of base b963463)

| Symbol | Risk | Callers / notes |
|---|---|---|
| `propose_profile_changes` | UNKNOWN → confirmed by text search | Registered as a value in `PROFILE_TOOLS` (`profile_tools.py:59`) → `agent_runner._get_runner` (`extra_groups`); `ws.py:213` matches its name to send the `proposal` frame (keys on `status == "success"`, unchanged). |
| `create_proposal` | LOW | 1 direct: the tool; tests. |
| `_validate` / `_check` | LOW | `create_proposal`, `_apply` (re-validation at execute, always typed models); tests. |
| `execute_proposal`, `cancel_proposal` | UNKNOWN → confirmed by text search | Passed as values to `_decide` (`api/proposals.py:151,159`); 19 test call sites keep working (the new parameter is keyword-only and optional; return type unchanged). |
| `_decide` (route) | LOW | `approve`, `cancel` routes (12 auth processes each, all upstream of the change). |
| `ProfileChangeIn` | **HIGH / CRITICAL (flagged)** | The score counts every importer of `schemas.py` (30 files). Text search: the class is used only in `services/profile_proposals.py` and `agent_tools/profile_tools.py` (+ 3 test files). The change is a `mode="before"` validator on the two role fields: it widens accepted input (case) and drops an unknown `played_role`; the JSON schema and every currently valid input are unchanged (pinned by `test_declaration_has_no_identity_parameters_for_gemini_and_claude`). |
| `handleFrame` (App.tsx) | UNKNOWN → confirmed by text search | Passed to `new ChatSocket(handleFrame, …)` (`App.tsx:323`) only. |
| `toolLabel` | LOW | `handleFrame` only. |
| `spellFor` | LOW | `MessageList` spell cards (data-only addition). |
| `repo.add_message` | not edited | Called from the hook inside the locked transaction; `db/repository.py` is not touched. |

## Project Structure

### Documentation (this feature)

```text
specs/034-epic203-qa-fixes/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1 (incl. the Postgres race-test recipe)
├── contracts/
│   └── internal-interfaces.md   # tool input tolerance, service hook, frame guard
├── checklists/requirements.md
├── checkpoint.md        # before /speckit-implement
└── tasks.md             # /speckit-tasks
```

### Source Code (files this feature edits or creates)

```text
backend/app/schemas.py                         # ProfileChangeIn: role before-validator (only this class)
backend/app/services/profile_proposals.py      # per-item parse, blank realm/region codes, on_transition hook
backend/app/agent_tools/profile_tools.py       # catch-all → {"status": "error"}; note on raw items
backend/app/api/proposals.py                   # _decide: hook saves the line in the locked transaction
frontend/src/App.tsx                           # turn conversation ref; guard done/error; dedupe loose
frontend/src/toolLabels.ts                     # "Preparing profile changes"
frontend/src/lib/spells.ts                     # propose_profile_changes spell entry
backend/tests/test_profile_tools.py            # AC 1 via FunctionTool.run_async; AC 2 catch-all
backend/tests/test_profile_proposals.py        # blank realm/region codes, roles, raw items
backend/tests/test_proposal_routes.py          # only the transitioning call saves the line (SQLite)
backend/tests/test_proposal_race_pg.py         # NEW: Postgres overlap test (approve x2, cancel x2)
frontend/src/App.test.tsx                      # NEW: mid-turn switch / new chat / reopen; status label
```

Not touched: `backend/app/db/repository.py` (the hook calls `add_message` unchanged),
`backend/app/api/ws.py`, `frontend/src/api/wsClient.ts`, anything under `wcl_agent/`.

**Structure Decision**: Existing web-application layout; no new modules except the two test files.

## Complexity Tracking

No constitution violations. One judgement call recorded for review:

| Choice | Why | Simpler alternative rejected because |
|---|---|---|
| Optional `on_transition` hook on `execute_proposal` / `cancel_proposal` | The follow-up line must be saved by the call that made the transition, in the same transaction (FR-009); the line's text is API-layer copy (`follow_up_text`, mirrors the card's labels). | Returning a "transitioned" flag can't put the insert in the same transaction; moving `follow_up_text` into the service would move API copy into the service layer and churn 031's tests. |
| `App.test.tsx` mocks App's child components | Verifies the real ref/handler wiring for the mid-turn switch (AC 4) without rendering Plotly/Streamdown in jsdom. | A pure helper module tested alone would not prove the `done`/`error`/`selectConversation` wiring. |
