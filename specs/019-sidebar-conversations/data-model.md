# Data model: feature 019

## `conversations` (existing table, two new columns)

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `pinned_at` | `timestamptz` | yes | `NULL` | `NULL` means not pinned. Set to the pin time on pin and kept on a repeated pin; cleared on unpin. It orders the Pinned group, newest first. |
| `title_source` | `varchar(10)` | no | `'auto'` (server and ORM) | One of `auto`, `explicit`, `generated`, `legacy`. Existing rows are backfilled to `legacy` by migration 0012 (an UPDATE right after the column is added with default `auto`). |

The existing columns are unchanged: `id`, `tenant_id`, `title` (`varchar(200)`, default
"New chat"), `model`, `created_at` and `updated_at` (`onupdate=now()`). Neither pin
writes nor title-source writes may bump `updated_at`. The generated-title write doesn't
either: it isn't user activity, so the list order stays put.

There are no new indexes. `ix_conversations_tenant_updated` still serves the list query.
RLS is unchanged: the table policy is row-level, so the new columns are covered.

### `title_source` state machine

```text
create_conversation(title=None|"")  ─►  auto
create_conversation(title="X")      ─►  explicit                      (terminal)
migration 0012, rows that existed   ─►  legacy                        (terminal)

auto ──claim_title_generation()──►  generated                         (terminal)
        (a conditional UPDATE, WHERE title_source='auto'; exactly one caller wins)
```

- `auto`: the title is "New chat" or the excerpt `add_message` writes from the first user
  message (unchanged behaviour).
- `generated`: only set by the claim. `set_generated_title` writes `title` only
  `WHERE title_source='generated'`, so it cannot overwrite an explicit title.
- No path goes back to `auto`. There is no rename feature.

## Repository functions (`backend/app/db/repository.py`)

| Function | Change | Contract |
|---|---|---|
| `create_conversation(session, model, title=None, *, tenant_id)` | changed (additive) | Sets `title_source='explicit'` iff `title` is truthy, else `'auto'`. Signature unchanged. |
| `set_conversation_pinned(session, conv_id, pinned: bool, *, tenant_id) -> Conversation \| None` | new | One UPDATE scoped by id and tenant: `pinned_at = coalesce(pinned_at, now)` or `NULL`, `updated_at` unchanged. Returns the refreshed row, or `None` when no row matched (the caller returns 404). |
| `claim_title_generation(session, conv_id, *, tenant_id) -> bool` | new | `UPDATE … SET title_source='generated' WHERE id, tenant_id, title_source='auto'`; `updated_at` unchanged. True iff 1 row changed. |
| `set_generated_title(session, conv_id, title: str, *, tenant_id) -> bool` | new | `UPDATE … SET title=:title WHERE id, tenant_id, title_source='generated'`; `updated_at` unchanged. True iff 1 row changed. |
| `list_conversations`, `get_conversation(_row)`, `add_message`, `delete_conversation` | unchanged | The rows now carry `pinned_at` and `title_source`. |

## Pydantic schemas (`backend/app/schemas.py`)

- `ConversationOut` gains `pinned_at: datetime | None = None`, which `ConversationDetail`
  inherits. `title_source` is **not** exposed; the client has no use for it.
- `ConversationUpdate`: `pinned: bool`, `model_config = ConfigDict(extra="forbid")`.
- `ConversationTitleFrame` (phase 2): `type: Literal["conversation_title"]`,
  `conversation_id: uuid.UUID`, `title: str`.

## Frontend types

- `frontend/src/types.ts` `Conversation`: `+ pinned_at: string | null`.
- `frontend/src/api/wsClient.ts` frame union (phase 2):
  `+ { type: "conversation_title"; conversation_id: string; title: string }`.
