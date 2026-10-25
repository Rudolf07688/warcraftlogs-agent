---
description: "Task list for feature 019: sidebar order, pinning, generated names"
---

# Tasks: Sidebar & conversations: order, pinning, generated names

**Input**: Design documents from `specs/019-sidebar-conversations/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Requested by the spec (FR-021) and the sprint plan (AC 3, AC 8). Backend tests
come before or with each implementation slice.

**Delivery phases (brief)**: **Phase A** = T001–T020 (sc-154, sc-165 and the sc-155 DB
groundwork), which runs now. **Phase B** = T021–T034 (sc-155), which runs only after
feature 018 merges and the phase 2 files are granted. Tasks marked ⧗schemas need the
`backend/app/schemas.py` grant, which the scrum master deferred to phase B (one owner per
file). They are the **first** tasks of phase B. Until then, the PATCH route tests
(T010) are `xfail(strict=True)`, and T012 removes the marker.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 = sc-154, US2 = sc-165, US3 = sc-155

---

## Phase 1: Setup

- [X] T001 Move sc-154 to In Progress (done at kickoff) and confirm sc-165 and sc-155 are in Shortlist on iteration 161 (Shortcut)
- [X] T002 Record the baseline: run `uv run --extra test pytest -q` and `npm run build` in `frontend/` at the branch base, and note the pass/fail/skip counts in `specs/019-sidebar-conversations/checkpoint.md`

---

## Phase 2: Foundational (blocks US2 and US3)

**Purpose**: the schema change both later stories rely on (`pinned_at`, `title_source`).

- [X] T003 Write migration `backend/migrations/versions/0012_conversation_pin_title.py`. It sets revision `0012_conversation_pin_title` and down_revision `0011_guide_content_types`. `upgrade()` adds `pinned_at` (timestamptz, nullable) and `title_source` (`String(10)`, not null, server_default `'auto'`), then runs `UPDATE conversations SET title_source='legacy'` for the existing rows (portable, no ALTER COLUMN). `downgrade()` drops both columns. The docstring follows the 0011 style (research R4)
- [X] T004 Add `pinned_at: Mapped[datetime | None]` (`DateTime(timezone=True)`, nullable) and `title_source: Mapped[str]` (`String(10)`, `default="auto"`, `server_default="auto"`) to `Conversation` in `backend/app/db/models.py`, each with a one-line comment citing feature 019 (run GitNexus `impact` on `Conversation` first: HIGH, additive)
- [X] T005 [P] Write `backend/tests/test_conversation_migration.py`. It builds a pre-0012 `conversations` table in SQLite with 2 existing rows, loads the 0012 module via importlib, runs `upgrade()` under `alembic.operations.Operations` with a `MigrationContext`, and asserts that existing rows are `legacy` with a NULL `pinned_at` and that a new insert defaults to `auto`. It then runs `downgrade()` and asserts both columns are gone and the 2 rows are intact (research R10)
- [X] T006 Change `create_conversation` in `backend/app/db/repository.py` to set `title_source="explicit"` when `title` is truthy, else `"auto"`, keeping the signature (run `impact` first: HIGH, 3 callers, additive)

**Checkpoint**: `pytest -q` is green, and the migration test passes.

---

## Phase 3: User Story 1 - Conversations first in the sidebar (P1, sc-154) 🎯 MVP

**Goal**: the Conversations section renders above Raids. Both toggles and counts stay.

**Independent Test**: quickstart manual check 1, and `npm run build` is green.

- [X] T007 [US1] Move the Conversations section label and list block above the Raids section label and list in `frontend/src/components/Sidebar.tsx`, keeping `convsOpen` and `raidsOpen`, the counts and the empty texts unchanged (`impact` on `SidebarImpl` is UNKNOWN; the only consumer is `App.tsx:452`, confirmed by text search)
- [X] T008 [US1] Run `npm run build` in `frontend/` and commit the US1 slice

**Checkpoint**: US1 is shippable on its own.

---

## Phase 4: User Story 2 - Pin important chats (P2, sc-165)

**Goal**: pin and unpin from the sidebar entry and the chat header, stored server side
per workspace, with a Pinned group at the top.

**Independent Test**: quickstart manual check 2, plus `test_conversation_pinning.py`.

Before T009: move sc-165 to In Progress (Shortcut).

### Tests for User Story 2

- [X] T009 [P] [US2] Write repository tests in `backend/tests/test_conversation_pinning.py`:
  - pin sets `pinned_at`, unpin clears it;
  - a repeated pin keeps the first `pinned_at`;
  - `updated_at` is unchanged by pin and unpin;
  - a foreign tenant id or a missing id returns `None` and changes nothing;
  - `create_conversation` sets the explicit/auto `title_source`.
- [X] T010 [P] [US2] Add API tests, marked `pytest.mark.xfail(strict=True, reason="PATCH needs ConversationUpdate in schemas.py (phase B)")` until T012/T013 land, to `backend/tests/test_conversation_pinning.py` (`as_user`, plus a `tenant_b` fixture via `make_authed_client`, as in `test_tenant_isolation.py`):
  - PATCH `{pinned:true}` returns 200 with `pinned_at` set, and the GET list shows it;
  - PATCH `{pinned:false}` clears it;
  - PATCH on tenant B's conversation is 404, and B's row is unchanged;
  - PATCH on a random uuid is 404;
  - a missing CSRF header is refused (401/403);
  - a body without `pinned` or with extra keys is 422;
  - deleting a pinned conversation works.
- [ ] T010a [P] [US2] Add explicit-at-creation tests (FR-018, one per naming caller) to `backend/tests/test_conversation_titles.py` (or to `test_conversation_pinning.py` if that file isn't granted in phase A). Each checks `title_source` in the DB:
  - `POST /api/conversations` with a title gives `explicit`, and without a title gives `auto`;
  - `POST /api/raids/{code}/investigate` on a tracked raid gives `explicit`;
  - the same endpoint on a recent raid from the welcome page gives `explicit`;
  - a WS-created conversation (`repo.create_conversation` without a title) gives `auto`.

### Implementation for User Story 2

- [X] T011 [US2] Add `set_conversation_pinned(session, conv_id, pinned, *, tenant_id) -> Conversation | None` to `backend/app/db/repository.py`. It is one UPDATE scoped by id and tenant, with `pinned_at = coalesce(pinned_at, now_utc)` or `None` and `updated_at = Conversation.updated_at`. On 0 rows it returns `None`; otherwise it returns the row via a `populate_existing` select (data-model.md)
- [ ] T012 [US2] ⧗schemas (phase B, first): add `pinned_at: datetime | None = None` to `ConversationOut`, and a new `ConversationUpdate(pinned: bool)` with `extra="forbid"`, in `backend/app/schemas.py` (run `impact` on `ConversationOut` first: HIGH, additive; coordinate the hunk with dev-a-018)
- [ ] T013 [US2] ⧗schemas (phase B, first): add `PATCH /api/conversations/{conv_id}` (`require_csrf`, `get_tenant_db`, 404 `not_found` on `None`, returns `ConversationOut`) to `backend/app/api/conversations.py`, and update the module docstring's verb list
- [X] T014 [US2] Run `uv run --extra test pytest -q` until T009, T010a and the whole suite are green, with T010 xfailing strictly (in phase B, after T012/T013: T010 passing with the marker removed)
- [X] T015 [P] [US2] Add `pinned_at?: string | null` (optional until the phase B schema returns it) to `Conversation` in `frontend/src/types.ts`, and `updateConversation(id, body: { pinned: boolean }): Promise<Conversation>` (PATCH, `csrf: true`) to `frontend/src/api/restClient.ts`
- [X] T016 [US2] In `frontend/src/components/Sidebar.tsx`:
  - add an `onTogglePin(id, pinned)` prop;
  - split `conversations` into the pinned ones (sorted by `pinned_at` desc) and the rest (server order);
  - render a "Pinned" group label and its items first, only when at least one chat is pinned;
  - add a per-entry `Toggle` (`ui/toggle`, `size="sm"`, `LuPin`, `aria-label` "Pin chat" or "Unpin chat", `pressed={!!c.pinned_at}`, so Radix sets `aria-pressed`) beside delete. It is hidden until hover or `focus-visible` unless pressed, keyboard reachable (FR-004a), with `stopPropagation` on click and keydown so the row's select doesn't fire;
  - pull the entry rendering into one local function shared by both groups (no duplicated markup).
- [X] T017 [US2] In `frontend/src/App.tsx`:
  - add `togglePin(id, pinned)`, which calls `updateConversation`, replaces that conversation in `conversations` state, and calls `refreshConversations()` on error;
  - pass it to `<Sidebar onTogglePin>`;
  - add a header `Toggle` (`LuPin`, `aria-label` and `title` "Pin chat" or "Unpin chat", `aria-pressed` via `pressed`, FR-004a) next to the PDF button, shown when the `activeId` conversation is in the list, with `pressed` derived from its `pinned_at`.
- [X] T018 [US2] Run `npm run build` in `frontend/`, then run the shadcn MCP audit checklist (`get_audit_checklist`) and fix what it flags
- [X] T019 [US2] Commit the US2 slice after GitNexus `detect-changes --scope all` in the worktree, and check ownership

**Checkpoint**: US1 and US2 both work. The pin state survives a reload and a re-login.

---

## Phase 5: User Story 3 groundwork (phase A, no `wcl_agent` import)

- [ ] T020 [US3] Add `claim_title_generation(session, conv_id, *, tenant_id) -> bool` (UPDATE `auto→generated`, `updated_at` unchanged) and `set_generated_title(session, conv_id, title, *, tenant_id) -> bool` (UPDATE title WHERE `title_source='generated'`, `updated_at` unchanged) to `backend/app/db/repository.py`, with tests in `backend/tests/test_conversation_titles.py`:
  - a claim succeeds once, and a second claim is False;
  - `explicit` and `legacy` conversations are never claimed;
  - another tenant's id gives False;
  - `set_generated_title` doesn't write without a claim;
  - `updated_at` is unchanged.

**Phase A ends here.** Write `checkpoint.md`, hand off phase A to the scrum master, and
wait for 018 to merge.

---

## Phase 6: User Story 3 - Chats name themselves (P3, sc-155), phase B

**Goal**: after the first complete reply, a default-named chat gets a short generated
title once, off the chat path, and the sidebar updates without a reload.

**Independent Test**: quickstart manual check 3, plus `test_conversation_titles.py`.

Before T021: rebase on the sprint tip after 018, re-index GitNexus in the worktree, get
the phase 2 grant, and move sc-155 to In Progress.

### Tests for User Story 3

- [ ] T021 [P] [US3] Add `clean_title` unit tests to `backend/tests/test_conversation_titles.py`:
  - quotes, curly quotes and backticks are stripped;
  - `**bold**` and `# heading` markers are removed;
  - a `Title:` prefix is removed;
  - only the first non-empty line is kept;
  - whitespace is collapsed;
  - a cut at 60 falls on a word boundary, and a hard cut is used when there is no space;
  - empty or punctuation-only input gives "".
- [ ] T022 [P] [US3] Add `retitle_conversation` tests to `backend/tests/test_conversation_titles.py`, with the model faked by monkeypatching `suggestions._get_client` (or `conversation_titles.generate_title`):
  - success: the title is saved and `notify` is called once with it;
  - once-only: a second call makes no model call;
  - explicit: a conversation created via `POST /api/raids/{code}/investigate` is never claimed or renamed;
  - failure: an exception, `ModelRateLimited` or a timeout keeps the excerpt title, raises nothing and doesn't call `notify`;
  - an empty cleaned result keeps the excerpt title;
  - a conversation deleted after the claim gives no error and no notify;
  - a `notify` that raises (closed socket) is swallowed;
  - `generate_with_retry` receives the small `RetryPolicy`.
- [ ] T023 [P] [US3] Add a turn-path test to `backend/tests/test_conversation_titles.py` (`_FakeSocket` style from `test_turn_path.py`):
  - `_handle_turn` on a new conversation sends `done` before any `conversation_title`;
  - the title job runs after `done` and sends `{"type":"conversation_title", "conversation_id", "title"}`;
  - a second turn on the same conversation schedules nothing;
  - a turn on a raid-investigation conversation schedules nothing.

### Implementation for User Story 3

- [ ] T024 [US3] Add an autouse fixture to `backend/tests/conftest.py` that monkeypatches `conversation_titles.generate_title` to return `""`, so no test makes a real title call or gets an extra frame; the US3 tests override it
- [ ] T025 [US3] Create `backend/app/services/conversation_titles.py`:
  - constants `TITLE_MAX_LEN=60`, `TITLE_TIMEOUT_S=15.0` and `_POLICY=RetryPolicy(attempts=2, initial_s=2.0, max_s=5.0, budget_s=8.0)`, plus `_PROMPT`;
  - `clean_title(raw) -> str`;
  - `async generate_title(question, answer) -> str`: suggestions model and client via `from .. import suggestions`, `generate_with_retry`, thinking off, `max_output_tokens=32`;
  - `async retitle_conversation(conv_id, identity, question, answer, notify)`: claim in its own `tenant_scope`, reset `current_turn` to None, `asyncio.timeout`, `set_generated_title`, best-effort `notify`; everything is caught and logged;
  - `schedule_title(...)`: calls `background.spawn` with key `("conversation-title", conv_id)`.
- [ ] T026 [US3] Add `ConversationTitleFrame(type: Literal["conversation_title"], conversation_id: uuid.UUID, title: str)` with a docstring to `backend/app/schemas.py`
- [ ] T027 [US3] In `backend/app/api/ws.py` `_handle_turn` (run `impact` first: LOW): keep `title_eligible = conv.title_source == "auto"` from the setup transaction; after `DoneFrame`, when eligible, call `conversation_titles.schedule_title(conv_id, identity, turn.content, final_text, notify)`, where `notify` sends `ConversationTitleFrame` via `_send(ws, …)`
- [ ] T028 [US3] Run `uv run --extra test pytest -q` until it is green (all of T020–T023, plus `test_turn_path.py` and `test_ws_rate_limit.py` unchanged)
- [ ] T029 [P] [US3] Add `| { type: "conversation_title"; conversation_id: string; title: string }` to the frame union in `frontend/src/api/wsClient.ts`
- [ ] T030 [US3] Handle `case "conversation_title":` in `handleFrame` in `frontend/src/App.tsx` with `void refreshConversations()`
- [ ] T031 [US3] Run `npm run build` in `frontend/`

---

## Phase 7: Polish & Cross-Cutting

- [ ] T032 [P] Add one line each for the PATCH endpoint and the `conversation_title` frame to `documentation/ai_guide.md` (after 018 releases the file)
- [ ] T033 Run quickstart manual checks 1–3 on a scrum-master-assigned port, and check 4 (Postgres migration up, down, up) if a local db is available; record the results in `checkpoint.md`
- [ ] T034 Run final verification: re-index the worktree (`node /home/rudolf/dev/warcraftlogs-agent/.gitnexus/run.cjs analyze --index-only`), run `detect-changes --scope all` (not partial or truncated), check ownership with `git diff --name-only <base>...HEAD`, restore `CLAUDE.md` and `.specify/feature.json`, make the full suite and the build green, then hand off to the scrum master

---

## Dependencies & Execution Order

- Setup (T001–T002), then Foundational (T003–T006), which blocks US2 and US3.
- **US1** (T007–T008) depends on nothing, and can go first or in parallel with Foundational.
- **US2** (T009–T019) depends on Foundational. T012 and T013 depend on the schemas.py grant.
- **US3 groundwork** (T020) depends on Foundational.
- **US3** (T021–T031) depends on T020, on 018 being merged and on the phase 2 grant.
  T025 comes before T027, and T026 comes before T027.
- Polish (T032–T034) comes last.

## Parallel Opportunities

- T005 (migration test) can run alongside T006.
- T009 and T010 are written together in one file; T015 (frontend types/client) runs
  alongside the backend T011–T014.
- T021, T022, T023 and T029 run in parallel within phase B.
- No sub-agents are planned: the slices are small and sequential, and most tasks share
  `repository.py`, `Sidebar.tsx` or `App.tsx`.

## Implementation Strategy

1. MVP = US1 (T007–T008): one block moved, shippable on its own.
2. Then Foundational and US2: the pin feature, demoable end to end once schemas.py is granted.
3. T020 lays the US3 DB groundwork without `wcl_agent`.
4. After 018 merges: US3 (T021–T031), then Polish.
