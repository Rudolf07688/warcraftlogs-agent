# Research: Sidebar & conversations (feature 019)

No open NEEDS CLARIFICATION items remain. The clarify answers (Q1–Q5) are drafted on
the all-A assumption, pending the product owner's reply. Each decision below gives the
choice, the reason, and the alternatives.

## R1: Where the pin state lives

- **Decision**: a nullable `pinned_at timestamptz` on `conversations`. `NULL` means not
  pinned. The value orders the Pinned group (Q1-A: most recently pinned first).
- **Rationale**: one column answers both "is it pinned" and "in which order". Pins are per
  workspace (Q2-A), like the conversation row itself, so RLS and the `tenant_id` predicate
  cover them with no new policy.
- **Alternatives**: a boolean plus a separate order column (two columns for one fact); a
  `conversation_pins (user_id, conversation_id)` table for per-user pins (rejected by
  Q2-A, more scope and a new RLS policy).

## R2: Pin API shape and tenancy

- **Decision**: `PATCH /api/conversations/{conv_id}` with the body `ConversationUpdate
  {pinned: bool}` (extra keys forbidden). It returns the updated `ConversationOut`. It uses
  `require_csrf` (like DELETE) and `get_tenant_db`. The repository does a single
  `UPDATE … WHERE id = :id AND tenant_id = :tid`, and 0 rows gives `None`, which the
  handler turns into 404 `not_found`. There is never a fetch-then-authorize step.
- **Idempotency**: pinning keeps an existing `pinned_at`
  (`coalesce(pinned_at, :now)`), so a repeated pin does not reorder the group. Unpinning
  sets `NULL`.
- **`updated_at`**: the UPDATE sets `updated_at = conversations.updated_at` explicitly,
  so the column's `onupdate=func.now()` doesn't fire (FR-009). A test asserts it.
- **`now`**: computed in Python as `datetime.now(timezone.utc)`, as `_apply_raid_update`
  does, so ordering is deterministic in SQLite tests.
- **Alternatives**: `POST /pin` and `DELETE /pin` sub-resources (two endpoints for one
  flag); PUT of the whole conversation (overwrites fields we don't edit).

## R3: Telling explicit titles from default titles, and "at most once"

- **Decision**: one column, `title_source varchar(10) NOT NULL DEFAULT 'auto'`, with these
  states:
  - `auto`: the default name ("New chat" or the first-message excerpt), eligible for
    generation;
  - `explicit`: named by its creator, never replaced;
  - `generated`: generation was claimed (and maybe succeeded), never again;
  - `legacy`: the row predates this feature, never replaced (Q5-A).
- `repo.create_conversation` sets `explicit` when a non-empty `title` is passed. Its two
  explicit callers are `POST /api/conversations` with a title (none in the app today, but
  the API allows it) and `raids.investigate_raid` (raid investigations and recent-raid
  kickoffs, which both go through `/investigate`). Otherwise it sets `auto`.
- **Once-only (FR-016)**: `claim_title_generation` runs
  `UPDATE conversations SET title_source='generated', updated_at=updated_at WHERE id=:id
  AND tenant_id=:tid AND title_source='auto'`. Only the caller that sees `rowcount == 1`
  calls the model. It is one statement, so it is atomic across tasks, processes and
  instances. A failed attempt is not retried (FR-017, accepted by the scrum master).
- **Alternatives**:
  - two booleans (`title_explicit`, `title_generated_at`): two columns for one state
    machine;
  - comparing the title text with the first message's excerpt: fragile, and wrong for an
    explicit title that happens to equal the excerpt;
  - an in-memory set: not durable and not cross-instance, which FR-016 rejects.

## R4: Existing rows (FR-020)

- **Decision**: the migration adds the column with server default `'auto'`, then runs
  `UPDATE conversations SET title_source = 'legacy'` in the same transaction, which
  covers every row that existed before it. The ORM default is `'auto'` as well. This is
  equivalent to the "default 'legacy', then switch to 'auto'" form the scrum master
  approved, but it needs no `ALTER COLUMN … SET DEFAULT`, so the same migration also runs
  in the SQLite migration test.
- **Rationale**: old chats, including old raid investigations whose explicit title had no
  marker, are never renamed. No per-turn "is this the first reply?" query is needed:
  a new chat reaches the hook in `auto` only until its first complete reply claims it.
- **Alternatives**: counting complete agent messages on every turn (an extra query per
  turn); renaming old chats (rejected by Q5-A).

## R5: When the job fires

- **Decision**: in `ws._handle_turn`, after `DoneFrame` is sent and only when the
  conversation row loaded at turn setup has `title_source == 'auto'`. A turn that errors
  or is interrupted returns before that point, so "first complete reply" holds (spec
  edge case). The input is this turn's user message and the saved reply. For a new chat,
  that is the first exchange.
- **Rationale**: no extra DB round trip on later turns (their row is no longer `auto`).
  The row is already loaded by `get_conversation_row` or `create_conversation`.
- **Alternatives**: a hook in `agent_runner.stream_response` (it has no DB or socket
  context); a hook in `repo.add_message` (it would mix model I/O into the repository).

## R6: The model call

- **Decision**: the cheap suggestions model and its process-wide genai client
  (`backend.app.suggestions._SUGGEST_MODEL` and `_get_client()`), reached through the
  `suggestions` module (`from .. import suggestions`), so tests can monkeypatch one place
  and nothing is duplicated. The call is non-streaming `generate_content`, with thinking
  off, `max_output_tokens=32` and `temperature=0.2`. It runs inside
  `generate_with_retry(once, RetryPolicy(attempts=2, initial_s=2.0, max_s=5.0,
  budget_s=8.0))` under `asyncio.timeout(15.0)`. `ModelRateLimited`, `TimeoutError` and any
  other exception are logged and swallowed.
- **Prompt**: "Write a short title (max 8 words) for this chat … Return only the title,
  no quotes, no markdown." It includes the question (cut to 1,000 chars) and the answer
  (cut to 2,000 chars) to keep the call cheap.
- **Cleaning (`clean_title`, pure)**: keep the first non-empty line. Strip a leading
  `Title:` label. Strip markdown markers (`#`, `*`, `_`, backticks, `>`), surrounding
  quotes (straight and curly) and trailing `.`/`:`. Collapse whitespace. If the result is
  over 60 characters, cut at the last space at or before 60 (hard cut if there is none)
  and strip trailing punctuation. An empty result means "keep the current title".
- **Why private names**: making them public means editing `suggestions.py`, which 018
  holds until it merges. Reading two module attributes is reuse without a second copy.
  A follow-up rename to public names is optional and out of scope.
- **Alternatives**: a fourth `_get_client()` copy (violates I, the "third time" rule
  already applies); the chat model (slow and premium; suggestions moved off it in
  PERF-005).

## R7: Background ownership and failure

- **Decision**: `services.background.spawn(retitle_conversation(...),
  key=("conversation-title", conv_id))`. It gives a strong reference and in-process dedup.
  The DB claim is the cross-instance guard. The coroutine catches everything and logs it
  (see plan, notes a–c). `background.py` is unchanged.
- **Deleted conversation meanwhile**: the claim or the final `UPDATE … WHERE id AND
  tenant_id AND title_source='generated'` matches 0 rows, so the job does nothing and
  doesn't notify.
- **Tenancy**: each DB step opens `tenant_scope(identity.tenant_id,
  user_id=identity.user_id)` (RLS context), and the repository functions take `tenant_id`.

## R8: How the client learns the title (FR-019)

- **Decision**: a new WS frame,
  `{"type": "conversation_title", "conversation_id", "title"}`
  (`ConversationTitleFrame`), sent through the `_TurnSocket` lock. On it, the client calls
  `refreshConversations()`, the same refetch it does on `done`, so the list stays the one
  source of truth. If the socket has gone, the title shows on the next list load (app
  start, next `done`, delete).
- **Alternatives**: polling the list after `done` (wasteful, and racy with a 1–10 s job);
  patching state in place from the frame (cheaper, but a second update path for the
  list; the refetch is one small query).

## R9: Frontend controls

- **Decision**: the shadcn `Toggle` (`ui/toggle.tsx`, already installed, Radix) with
  `LuPin` and `LuPinOff` from `react-icons/lu`:
  - **Sidebar entry**: `size="sm"`, beside the delete button. Hidden until hover or focus
    like delete, and always visible when pressed. `onClick` stops propagation so the
    row's select doesn't fire. `aria-label` is "Pin chat" or "Unpin chat", and Radix sets `aria-pressed` (FR-004a).
  - **Chat header**: shown when `activeId` is set and the conversation is in the list;
    `pressed` is derived from the list.
  - **Pinned group**: rendered inside the Conversations list only when at least one chat
    is pinned. Its label is a small `div` (Tailwind utilities), and a plain rule separates
    it from the rest.
- **Update path**: `updateConversation(id, {pinned})` returns the row, and App replaces
  that conversation in state (immediate, SC-002). On error it refetches the list.
- **Alternatives**: the `@shadcn/sidebar` system (rewrites the sidebar), a dropdown menu
  per entry (Q4-B), drag-to-reorder (Q1-C).

## R10: Migration testing

- **Decision**: `test_conversation_migration.py` loads `0012_conversation_pin_title.py`
  with `importlib`. It runs `upgrade()` and `downgrade()` through `alembic.operations.
  Operations` bound to a SQLite connection (`MigrationContext.configure`), against a
  hand-made pre-0012 `conversations` table with existing rows. It asserts the backfill
  (`legacy`), the new default (`auto`), `pinned_at IS NULL`, and that the downgrade
  removes both columns with the rows intact. Postgres up, down and up is a manual step in
  quickstart.md, since no test Postgres runs here.
- **Alternatives**: running the whole Alembic chain on SQLite (fails: 0004 uses
  Postgres-only RLS DDL).
