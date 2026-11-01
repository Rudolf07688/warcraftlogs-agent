# Data model: 043 knowledge base store

Migration `0019_kb_chunks` (`down_revision = "0018_raw_store_visibility"`), Postgres only.
SQLAlchemy models `KbChunk`, `KbChatChunk` in `backend/app/db/models.py`.

## `kb_chunks` (global, no RLS)

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `kind` | varchar(8) | `wcl` \| `guide` (CHECK) |
| `raw_fetch_id` | varchar(64) NULL | FK `raw_fetches.query_key` ON DELETE CASCADE |
| `guide_id` | uuid NULL | FK `spec_guides.id` ON DELETE CASCADE |
| `chunk_key` | varchar(200) | stable key within the source, e.g. `fight:32`, `table:DamageDone:32`, `player:DamageDone:32:vagxsu`, `section:3` |
| `label` | varchar(200) | short human pointer: `fight 32 summary`, `fight 32 Damage done`, `Vagxsu, fight 32 Damage done`, guide section title |
| `text` | text | rendered chunk (bounded 2,000 chars) |
| `content_hash` | varchar(64) | sha256 of `text` |
| `embedding` | vector(768) NULL | NULL = pending (keyword only) |
| `embed_model` | varchar(80) NULL | |
| `embedded_at` | timestamptz NULL | |
| `tsv` | tsvector GENERATED STORED | `to_tsvector(CASE WHEN kind='wcl' THEN 'simple' ELSE 'english' END::regconfig, text)` |
| `report_code` | varchar(32) NULL | wcl |
| `zone_id`, `encounter_id`, `difficulty`, `fight_id` | int NULL | wcl (difficulty = WCL id) |
| `kill` | bool NULL | wcl |
| `start_time` | timestamptz NULL | wcl: report start + fight start |
| `players` | jsonb NULL | wcl: `[{"name","key","class","spec"}]`, key = normalised name |
| `region`, `realm`, `guild` | varchar NULL | wcl, where present |
| `class_name`, `spec`, `role` | varchar(40) NULL | guide; per-player wcl chunks |
| `content_type` | varchar(8) NULL | guide: `raid` \| `mplus` |
| `patch` | varchar(20) NULL | guide `game_patch` |
| `section` | varchar(200) NULL | guide section title |
| `extra` | jsonb NULL | long tail (metric, hostility, source id, fight ids, …) |
| `created_at`, `updated_at` | timestamptz | |

Constraints: `CHECK ((kind='wcl' AND raw_fetch_id IS NOT NULL AND guide_id IS NULL) OR
(kind='guide' AND guide_id IS NOT NULL AND raw_fetch_id IS NULL))`;
`UNIQUE (raw_fetch_id, chunk_key)`, `UNIQUE (guide_id, chunk_key)` (NULLs distinct, so each
applies to its own kind).

Indexes: HNSW `embedding vector_cosine_ops`; GIN `tsv`; GIN `extra`; GIN `players
jsonb_path_ops`; B-tree `report_code`, `encounter_id`, `(class_name, spec)`, `kind`; the unique
constraints double as the source lookups (cascade deletes, re-index).

## `kb_chat_chunks` (tenant, RLS `tenant_isolation`, enabled + forced)

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid | FK `tenants.id` ON DELETE CASCADE |
| `conversation_id` | uuid | composite FK `(conversation_id, tenant_id)` → `conversations(id, tenant_id)` ON DELETE CASCADE |
| `message_seq` | int | the agent answer's `messages.seq` |
| `created_at` | timestamptz | the answer's time |
| `characters` | jsonb NULL | `[{"name","key"}]` mentioned characters |
| `label` | varchar(200) | first words of the question |
| `text`, `content_hash`, `embedding`, `embed_model`, `embedded_at`, `extra` | as above | text bounded 6,000 chars |
| `tsv` | tsvector GENERATED STORED | `to_tsvector('english', text)` |

Constraints: `UNIQUE (tenant_id, conversation_id, message_seq)` (tenant first: a foreign
conversation id fails on the FK, never on this key, so there is no existence oracle; P7 SEC-001). Indexes: HNSW, GIN `tsv`, GIN `extra`,
GIN `characters jsonb_path_ops`, B-tree `(tenant_id, created_at)`.

`conversations` gains `UNIQUE (id, tenant_id)` (`uq_conversations_id_tenant`), the target of
the composite FK: FK checks bypass RLS, so the composite key is what stops a B-scoped insert
from naming A's conversation.

## Lifecycle of a chunk

```
source written (fetch stored with a changed body / guide published / turn saved)
  -> job queued (offer_*; dropped + counted when the queue is full)
  -> chunked; per source: insert new keys, update changed text (embedding := NULL),
     delete keys no longer produced, untouched keys keep their vector
  -> embedded in the background (vector + model + time, only if content_hash still matches)
  -> on embed failure: stays NULL, retried by the sweep
source deleted (fetch deleted or report gone/private, guide row deleted, conversation deleted)
  -> chunks deleted by ON DELETE CASCADE
```

## Notes for 044 (search)

- Keyword side must use the same config per kind: `simple` for `wcl`, `english` for `guide`
  and chat.
- Visibility for `wcl` rows is `fetch_visible_clause(KbChunk.raw_fetch_id, …)` (contract 3);
  chat rows rely on RLS plus the app's `tenant_id` predicate.
- Character filter: `players @> '[{"key": "<name_key>"}]'` / `characters @> …`.
