# Phase 1 Data Model: Streaming Chat Frontend

Persistence target: **PostgreSQL 17** via SQLAlchemy 2.0 async. Two tables model app
state over time. Single-user (no `user` table in v1).

## Entity: Conversation

A chat session shown in the sidebar.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID (PK) | Generated server-side. |
| `title` | text | Short label for the sidebar. Default derived from the first user message (e.g. first ~60 chars); editable later. |
| `model` | text | Model id currently associated with the conversation (e.g. `gemini-3.6-flash`). |
| `created_at` | timestamptz | Set on creation. |
| `updated_at` | timestamptz | Bumped on each new message; sidebar orders by this desc. |

Relationships: has many **Message** (ordered). Delete cascades to messages.

Validation / rules:
- `model` MUST be one of the configured allow-list at the time it is set.
- `title` non-empty; auto-filled from first user message if not provided.

## Entity: Message

One turn within a conversation.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID (PK) | Generated server-side. |
| `conversation_id` | UUID (FK → conversation.id) | Indexed; `ON DELETE CASCADE`. |
| `role` | text enum (`user` \| `agent`) | Who produced the message. |
| `content` | text | Final message text. For agent messages this is the fully streamed result. |
| `seq` | integer | Monotonic order within the conversation (0-based). |
| `created_at` | timestamptz | Timestamp. |

Validation / rules:
- `role` ∈ {`user`, `agent`}.
- `content` for `user` is non-empty; empty sends are rejected before persistence.
- `(conversation_id, seq)` is unique → stable ordering for replay.
- Only **final** agent text is persisted; intermediate stream tokens and tool
  traces are transient (not stored in v1 — "improve later").

## Derived / transient (not persisted in v1)

- **Streaming tokens** and **tool_start/tool_end** events — sent over the WebSocket
  only; reconstructed conversation history uses the final `content`.
- **ADK session** — rebuilt in memory from stored messages when a conversation is
  (re)opened; not a DB entity.
- **Analysis context** (encounter/difficulty) — handled conversationally by the
  agent; not a persisted column in v1.

## Indexes

- `messages(conversation_id, seq)` unique composite (ordering + lookup).
- `conversations(updated_at desc)` for the sidebar list.

## Lifecycle

1. `POST /api/conversations` (or first WS message with no `conversation_id`) creates
   a Conversation with the selected `model`.
2. Each user turn: persist the user Message (`seq = n`), run the agent (streaming),
   then persist the agent Message (`seq = n+1`) with the final text; bump
   `conversation.updated_at`.
3. Reopen: load all Messages ordered by `seq` to render history and to rebuild the
   agent session.
4. `DELETE /api/conversations/{id}` removes the conversation and its messages.
