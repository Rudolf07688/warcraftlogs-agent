# Implementation Plan: Sidebar & conversations: order, pinning, generated names

**Branch**: `019-sidebar-conversations` | **Date**: 2026-10-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/019-sidebar-conversations/spec.md`. Shortcut
stories sc-154, sc-165, sc-155. Sprint 2026-10-25, plan section F2 / 019, track B.

## Summary

- **sc-154**: `Sidebar.tsx` renders the Conversations section before the Raids section.
  Nothing else moves.
- **sc-165**: migration `0012` adds `conversations.pinned_at` (nullable timestamptz).
  `PATCH /api/conversations/{id}` with `{pinned: bool}` sets or clears it through the
  existing tenant-scoped session (`require_csrf` + `get_tenant_db`, a foreign or missing id
  gives 404), without touching `updated_at`. `ConversationOut` gains `pinned_at`. The sidebar
  splits the list into a "Pinned" group (most recently pinned first) and the rest (server
  order, last activity first). A pin toggle sits on each sidebar entry and in the chat
  header. Both use the existing shadcn `Toggle` and the `react-icons/lu` pin icons.
- **sc-155**: the same migration adds `conversations.title_source`
  (`auto` | `explicit` | `generated` | `legacy`). `repo.create_conversation` records
  `explicit` when a title is passed (raid investigations, recent-raid kickoffs). Existing
  rows are backfilled to `legacy`, so they are never renamed. After `done`, `_handle_turn`
  schedules a background job (`services/background.spawn`) only when the turn's
  conversation is still `auto`. The job claims the conversation with a conditional UPDATE
  `auto → generated` (DB-enforced, at most once). It then calls the cheap suggestions model
  through `generate_with_retry` with a small policy, inside its own timeout. It cleans the
  reply into a plain title of at most 60 characters, writes it, and sends a best-effort
  `conversation_title` frame on the socket. The client refetches the list on that frame.
  Any failure leaves the excerpt title and is logged, never surfaced.

Implementation runs in two phases (brief): phase 1 (sc-154, sc-165) now, phase 2 (sc-155)
after feature 018 merges, because it imports `wcl_agent.model_retry` (whose path 018
changes) and edits `ws.py`, which 018 holds.

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript + React 19 (frontend).

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2,
google-genai (title call, via the existing suggestions client), React, Tailwind v4,
shadcn/ui (`Toggle`, `Button`, already installed), `react-icons/lu`. **No new dependency.**

**Storage**: PostgreSQL (RLS on `conversations`, unchanged). Migration
`0012_conversation_pin_title` (down_revision `0011_guide_content_types`) adds two columns.
Tests use SQLite in memory (`metadata.create_all`).

**Testing**: pytest (`uv run --extra test pytest -q`) with new files
`test_conversation_pinning.py`, `test_conversation_migration.py` (phase 1) and
`test_conversation_titles.py` (phase 2). The model is faked and there is no network.
Frontend: `npm run build` (tsc + vite).

**Target Platform**: Linux containers and the local dev host; browser SPA.

**Project Type**: Web application (FastAPI backend + React frontend).

**Performance Goals**: The pin round-trip reflects in the sidebar in under 1 s (SC-002).
Title generation adds 0 ms before `done` and before the next turn (SC-006). The title
appears within 10 s of `done` (SC-005); the job's hard timeout is 15 s.

**Constraints**:
- Tenant scoping on every query (`tenant_id` predicate plus RLS).
- No change to `wcl_agent` (F4 owns `model_retry`; we only import it).
- No change to `background.py`, `MessageList.tsx`, `StreamMarkdown.tsx` or `pdf_report.py`.
- The title job never raises into the event loop.

**Scale/Scope**: Per tenant, tens to hundreds of conversations. The list query is
unchanged (one indexed query per tenant), so no new index is needed.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. DRY & reuse | ✅ | Reuses the tenant-scoped session path (`get_tenant_db`, `tenant_scope`), `require_csrf`, the repository's id+tenant predicate pattern and the targeted-UPDATE style of `add_message`. The title job reuses `services/background.spawn`, the suggestions model id and client (`suggestions._SUGGEST_MODEL`, `suggestions._get_client`, imported as module attributes, not copied), `generate_with_retry` and `RetryPolicy`, and the existing socket send path (`_send` on the `_TurnSocket`). The frontend reuses `Toggle`, `Button`, `ConfirmDialog` and `refreshConversations`. There is no second title rule: the excerpt rule in `add_message` stays as is. |
| II. Step-wise delivery | ✅ | Slices: (1) sc-154 reorder, then build; (2) migration, model and repository pin functions with their tests; (3) PATCH endpoint and schema with tenancy tests; (4) frontend pin UI, then build; (5, phase 2) the title service with unit tests; (6) the `ws.py` hook, the frame and the frontend refetch. Each slice ends green. |
| III. Simplicity | ✅ | Two columns and one endpoint. No per-user pin table (Q2) and no manual ordering (Q1). One status column covers both the explicit-title rule and the once-only claim, instead of two booleans. The client groups the pinned chats, so the list query is unchanged. No new service layer: one module of plain functions. |
| IV. Typed contracts | ✅ | The `ConversationUpdate` request model, `ConversationOut.pinned_at`, the `ConversationTitleFrame` WS frame (Pydantic), the `Conversation` TS type and the `conversation_title` frame type in `wsClient.ts`. `title_source` is a `Literal` in Python. |
| V. Async backend | ✅ | The PATCH handler is `async def`. The title job is an asyncio task off the request path, with an async genai call and `asyncio.timeout`. |
| VI. GitNexus | ✅ (with HIGH flags) | Upstream `impact`: `create_conversation` is **HIGH** (3 direct callers, in 3 flows: POST /api/conversations, the WS `chat`, `investigate_raid`). The change is additive (it sets `title_source` and keeps its signature), and tests cover all three callers. `Conversation` (model) is **HIGH** (19 direct, mostly tests): two defaulted or nullable columns, no rename. `ConversationOut` is **HIGH** (16 direct): one optional field added. `add_message` is **LOW** (unchanged in this plan). `_handle_turn` is **LOW** (1 caller, `chat`). `SidebarImpl` is **UNKNOWN** (wrapped by `memo`); a text search confirms the only consumer is `App.tsx:452`. All HIGH items are additive. They were reported to the scrum master before any edit. Re-run `impact` before each edit, and `detect-changes --scope all` before each commit. |
| VII. shadcn UI | ✅ | Searched the registry through the MCP (`toggle`, `sidebar`, `dropdown menu`, `pin`). **Used**: `@shadcn/toggle` (already in `ui/toggle.tsx`) for both pin controls, and `Button` for the rest. **Not used**: `@shadcn/sidebar`, because its `SidebarGroup`/`SidebarGroupLabel`/`SidebarMenuAction` require `SidebarProvider` and its own layout and CSS variables. That would rewrite the resizable custom sidebar, well beyond these stories. `@shadcn/dropdown-menu` is not used (Q4 picked inline buttons). **Hand-built**: the small "Pinned" group label, a `<div>` with Tailwind utilities that matches the existing section label style. No registry item fits outside the sidebar system. The audit checklist runs after the UI slice. |
| VIII. Backlog sync | ✅ | sc-154 is In Progress. sc-165 moves to In Progress at its first implementation task, and sc-155 at phase 2 (product owner rule). All stay on iteration 161. Under Review only on the scrum master's word. |

**Result**: PASS. There are no violations, so Complexity Tracking is empty.

**Post-design re-check (after Phase 1)**: PASS. The design adds one module
(`services/conversation_titles.py`) and one WS frame type, both required by FR-015 and
FR-019. The `legacy` backfill value is the simplest way to satisfy FR-020 without a
per-turn message count.

## Project Structure

### Documentation (this feature)

```text
specs/019-sidebar-conversations/
├── plan.md              # This file
├── research.md          # Phase 0: decisions R1–R9
├── data-model.md        # Phase 1: Conversation columns, title_source states
├── quickstart.md        # Phase 1: how to verify each acceptance criterion
├── contracts/
│   ├── rest-conversations.md   # PATCH /api/conversations/{id}, ConversationOut.pinned_at
│   └── ws-conversation-title.md # the conversation_title frame
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── migrations/versions/0012_conversation_pin_title.py   # new (phase 1)
├── app/
│   ├── db/models.py              # Conversation: pinned_at, title_source (phase 1)
│   ├── db/repository.py          # create_conversation(title_source), set_conversation_pinned,
│   │                             # claim_title_generation, set_generated_title (phase 1)
│   ├── api/conversations.py      # PATCH /{conv_id} (phase 1)
│   ├── schemas.py                # ConversationOut.pinned_at, ConversationUpdate (phase 1 if granted,
│   │                             # else phase 2); ConversationTitleFrame (phase 2)
│   ├── services/conversation_titles.py   # new: clean_title, generate_title, retitle, schedule (phase 2)
│   └── api/ws.py                 # schedule the title job after `done` (phase 2)
└── tests/
    ├── conftest.py               # autouse: title model stubbed, never a real call (phase 2)
    ├── test_conversation_pinning.py      # new (phase 1)
    ├── test_conversation_migration.py    # new (phase 1)
    └── test_conversation_titles.py       # new (phase 2)

frontend/src/
├── components/Sidebar.tsx        # section order, Pinned group, per-entry pin toggle (phase 1)
├── App.tsx                       # togglePin, header pin toggle (phase 1); conversation_title frame (phase 2)
├── types.ts                      # Conversation.pinned_at (phase 1)
├── api/restClient.ts             # updateConversation (phase 1)
└── api/wsClient.ts               # conversation_title frame type (phase 2)

documentation/ai_guide.md         # one line each: PATCH endpoint, title frame (phase 2, after 018 releases it)
```

**Structure Decision**: The existing web-app layout. No new directories. One new backend
service module, one migration, three new test files.

## Phase 2 hook: design notes the scrum master asked for

- **(a) Task ownership.** `background.spawn` keeps a strong reference (`_bg_tasks`) until
  the task is done, and dedups by key (`("conversation-title", conv_id)`). It does **not**
  log exceptions (its done-callback only discards). So `retitle_conversation` itself wraps
  its whole body in `try/except Exception` and logs with
  `logger.warning(..., exc_info=True)`. No exception ever reaches the task, so nothing is
  lost silently, and asyncio never warns "exception was never retrieved". `background.py`
  is not edited.
- **(b) Timeout.** The model call runs under `asyncio.timeout(TITLE_TIMEOUT_S = 15.0)`,
  around the whole `generate_with_retry` loop, with
  `RetryPolicy(attempts=2, initial_s=2, max_s=5, budget_s=8)`. So a 429 retries once,
  inside the timeout. The DB writes are short single statements outside the timeout.
- **(c) Send path.** The job gets a `notify(title)` callback from `_handle_turn` that calls
  the existing `_send(ws, ConversationTitleFrame(...))`. `ws` there is the `_TurnSocket`,
  so the send goes through its lock and is serialized with the next turn's frames. A
  closed socket raises inside `notify`; the job catches that and logs at debug level,
  making the send a no-op. The title is already saved, so the next list load shows it.
- **Turn-context isolation.** `generate_with_retry` reads the `current_turn` ContextVar.
  `stream_response` resets it before `done`, and the task copies the context at creation,
  so the job sees `None`. It also sets `current_turn` to `None` itself at the start, so a
  title retry can never emit `model_retry` frames into a chat turn.
- **The next turn doesn't cancel the job.** It is not the suggestions task, and
  `_start_turn` cancels only `sock.suggestions`.

## Complexity Tracking

No violations.
