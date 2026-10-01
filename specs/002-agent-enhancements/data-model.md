# Phase 1 Data Model: Agent App Enhancements

Extends the `001` schema (`conversations`, `messages`). New tables: `tracked_raids`,
`captured_graphs`. One new column on `messages`. ADK's `DatabaseSessionService` owns its
own session tables in the same database (not modeled here — managed by ADK).

## Existing (unchanged) — for reference

- **Conversation** (`conversations`): `id` (UUID PK), `title`, `model`, `created_at`,
  `updated_at`. Has many Messages.
- **Message** (`messages`): `id` (UUID PK), `conversation_id` (FK → conversations,
  cascade), `role` (`user`|`agent`), `content`, `seq` (unique per conversation),
  `created_at`.

## Changed

### Message — add `status`

| Field | Type | Notes |
|-------|------|-------|
| `status` | String(10), default `"complete"` | `"complete"` \| `"partial"`. Set to `"partial"` when a streamed agent reply is interrupted (FR-009). Enables the UI/PDF to distinguish partial answers. |

- **Validation**: role ∈ {user, agent}; status ∈ {complete, partial}.
- **Migration**: ⚠️ `Base.metadata.create_all` creates missing *tables* only — it does
  **not** ALTER the already-existing `messages` table from feature 001. Add the column
  with an **idempotent startup statement** in the lifespan (after `create_all`):
  `ALTER TABLE messages ADD COLUMN IF NOT EXISTS status VARCHAR(10) NOT NULL DEFAULT
  'complete'` (Postgres supports `IF NOT EXISTS`). Existing rows backfill to `complete`
  via the default. (New tables `tracked_raids` / `captured_graphs` are created by
  `create_all` normally.)

## New

### TrackedRaid (`tracked_raids`) — US1 / FR-001–005

A Warcraft Logs report the user has successfully pulled data for.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK, default uuid4 |
| `report_code` | String(32) | **Unique**. The WCL report code (natural dedup key — FR-002). |
| `label` | String(200) | Human-readable: `"<guild> — <zone> — <date>"`, resolved from report metadata; falls back to the report code if unresolved. |
| `zone` | String(120), nullable | Zone/raid name when resolved. |
| `guild` | String(120), nullable | Guild name when resolved. |
| `report_started_at` | DateTime(tz), nullable | Raid start time from WCL (`startTime`), when resolved. |
| `first_seen_at` | DateTime(tz) | server_default now(); when first captured. |
| `last_asked_at` | DateTime(tz) | server_default now(), updated on every re-reference; **sort key** (FR-003). |
| `last_conversation_id` | UUID, FK → conversations, nullable, `ON DELETE SET NULL` | The most recent conversation that referenced this raid (context/debugging). |

- **Uniqueness / dedup rule (FR-002)**: `report_code` is unique. Capture is an
  **upsert**: insert if new (set `first_seen_at`, resolve label), else update
  `last_asked_at` (and `last_conversation_id`). Never creates duplicates.
- **Ordering (FR-003)**: list ordered by `last_asked_at DESC`.
- **Lifecycle**: created on first successful report retrieval; updated on each later
  reference; persists across restarts (FR-005). Not deleted when a conversation is
  deleted (raid outlives any single chat — matches the "separate from conversations"
  UI decision); FK nulled instead.

### CapturedGraph (`captured_graphs`) — US5 / FR-018

Graph data the agent retrieved during a conversation, kept for PDF rendering.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK, default uuid4 |
| `conversation_id` | UUID | FK → conversations, `ON DELETE CASCADE`, indexed. |
| `message_seq` | Integer, nullable | The agent turn (`messages.seq`) this graph was fetched during, for ordering within the report. |
| `report_code` | String(32) | Which report the graph came from. |
| `data_type` | String(40) | e.g. `DamageDone`, `Healing`, `Resources`. |
| `fight_id` | Integer, default 0 | Fight filter used (0 = all). |
| `source_id` | Integer, default 0 | Actor filter used (0 = all). |
| `graph_json` | JSONB | The `graph` payload returned by `get_report_graph` (already size-capped by the tool). Rendered to a chart at PDF time. |
| `created_at` | DateTime(tz) | server_default now(). |

- **Validation**: `data_type` ∈ the tool's `GRAPH_DATA_TYPES`; `graph_json` non-null.
- **Lifecycle**: inserted when `get_report_graph` returns success during a turn;
  cascade-deleted with its conversation. No dedup required (a conversation may fetch the
  same graph with different filters); the PDF renders them in `(message_seq, created_at)`
  order.

## Relationships

```text
Conversation 1───* Message
Conversation 1───* CapturedGraph           (cascade delete)
Conversation 1───0..1  TrackedRaid.last_conversation_id   (SET NULL on delete)
TrackedRaid  (standalone; keyed by report_code; outlives conversations)
```

## Derived / non-persisted

- **Validated model set** — computed once at startup from candidate lists + probe
  (research §5), held in `app.state`, not a table. Shape: `{ models: list[str],
  default: str, degraded: bool }`.
- **PDF report** — generated on demand from a Conversation's agent messages +
  CapturedGraphs; not stored.
- **Grounding usage** — transient per-turn signal from event `grounding_metadata`,
  surfaced as a WS frame; not persisted in v2.
