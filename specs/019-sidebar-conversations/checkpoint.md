# Checkpoint: feature 019 (dev-b-019-v2)

Resume from here after a context reset.

## Where things stand (2026-10-25)

- Worktree `/home/rudolf/dev/wcl-worktrees/dev-b`, branch `019-sidebar-conversations`,
  base `4227a86` (the sprint-2026-10-25 tip). Never push.
- Done: spec (`e28e571`), plan and artifacts (`8f5d143`), tasks.md.
- Gates:
  - Spec sign-off: the scrum master approved the spec and the technical design. The
    product owner's answers to Q1–Q5 are pending; I recommended all A's and the plan is
    drafted on them.
  - Phase 1 file grant: requested, **waiting**. Also asked: whether `schemas.py` hunks may
    go in phase 1.
- Shortcut: sc-154 is In Progress. sc-165 and sc-155 are in Shortlist on iteration 161.
  Move sc-165 at T009 and sc-155 at phase B start.
- Baseline (T002): backend `926 passed, 3 skipped, 1 deselected`; frontend build green.

## Decisions (see research.md R1–R10)

- `pinned_at timestamptz NULL`. PATCH `/api/conversations/{id}` with `{pinned: bool}`,
  using require_csrf and get_tenant_db; 404 for a foreign or missing id; `updated_at`
  untouched.
- `title_source` takes the values auto, explicit, generated, legacy. Existing rows are
  backfilled to legacy (server default 'legacy' on add, then 'auto').
  `create_conversation` sets explicit iff a title is given.
- Once-only means a conditional UPDATE claim auto→generated before the model call; a
  failed attempt is never retried.
- Title job: `background.spawn` (key `("conversation-title", conv_id)`). It catches and
  logs everything itself, runs `asyncio.timeout(15)` around `generate_with_retry` with
  `RetryPolicy(2, 2, 5, 8)`, uses the suggestions model and client via
  `from .. import suggestions`, and resets `current_turn` to None.
- Client update: a `conversation_title` WS frame sent via `_send` on the `_TurnSocket`
  (best effort); the client then calls `refreshConversations()`.
- UI: the existing shadcn `Toggle` with `LuPin`. The Pinned group label is hand-built (the
  `@shadcn/sidebar` system would be a rewrite). No new deps, no CSS file changes.

## Files (phase A: tentative grant; phase B: after 018 merges)

- Phase A:
  - `backend/migrations/versions/0012_conversation_pin_title.py`
  - `backend/app/db/models.py`, `backend/app/db/repository.py`, `backend/app/api/conversations.py`
  - `backend/tests/test_conversation_pinning.py`, `test_conversation_migration.py`, `test_conversation_titles.py` (T020 part)
  - `frontend/src/components/Sidebar.tsx`, `App.tsx`, `types.ts`, `api/restClient.ts`
  - `backend/app/schemas.py` (requested)
- Phase B:
  - `backend/app/services/conversation_titles.py`, `backend/app/api/ws.py`, `backend/app/schemas.py`
  - `backend/tests/conftest.py`, `frontend/src/api/wsClient.ts`, `App.tsx`
  - `documentation/ai_guide.md`

## Open questions

- The product owner's answers to Q1–Q5 (if any differ from A, revise spec, plan and tasks).
- The `schemas.py` phase-1 grant.

## Where implementation starts

T003 (migration) → T004 → T005/T006, then T007 (US1). See tasks.md.
