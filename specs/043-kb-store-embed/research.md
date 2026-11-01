# Research: 043 knowledge base store and embedding

Each item: decision, rationale, alternatives. Board decisions `clarify:043-*` (#31–#35) and the
SM's Gate 1 notes (#44, #45) are binding here.

## R1. Image and old-volume compatibility

- **Decision**: `pgvector/pgvector:pg17-trixie` in `docker-compose.yml` and every throwaway recipe.
  Prove compatibility by starting a throwaway `postgres:17` with a named volume, writing a
  marker row, stopping it, copying the volume (`docker run --rm -v src:/from -v dst:/to alpine
  cp -a /from/. /to`), and starting `pgvector/pgvector:pg17-trixie` on the copy; the marker survives
  and `CREATE EXTENSION vector` works. Never the compose volume.
- **Rationale**: same major version and the same Debian-based Postgres build plus the extension
  files, so the on-disk format is identical. The `-trixie` tag matters: the plain `pg17` tag is a
  bookworm build whose glibc differs from the `postgres:17` image, which gives a collation
  mismatch on an existing volume (board #82).
- **Alternatives**: a separate vector DB (rejected by the owner's design); building the
  extension into a custom image (more to maintain).

## R2. Migration 0019 on Postgres only

- **Decision**: 0019 returns early on non-Postgres (like 0004). It runs `CREATE EXTENSION IF NOT
  EXISTS vector`, then checks `SELECT extversion FROM pg_extension WHERE extname='vector'` and
  raises when it is below 0.8 (needed for `hnsw.iterative_scan`). It adds
  `UNIQUE (id, tenant_id)` on `conversations` (`uq_conversations_id_tenant`), creates both tables,
  their indexes, RLS on `kb_chat_chunks`, and grants DML to the runtime role. Downgrade drops
  them in reverse and leaves the extension installed (other databases on the server may use
  it; dropping it is not needed for a clean re-upgrade).
- **Rationale**: the vector type and tsvector only exist on Postgres; SQLite builds from the
  models (Gate 1 note a).

## R3. SQLite builds the same models

- **Decision**: `embedding` uses `pgvector.sqlalchemy.Vector(768)` (a user-defined type; its DDL
  `VECTOR(768)` is accepted by SQLite's loose typing and values round-trip as text). `tsv` is
  `TSVECTOR().with_variant(Text(), "sqlite")` with `Computed(...)` over a tiny `@compiles`
  expression: `to_tsvector(...)` on Postgres, `NULL` on SQLite (SQLite rejects unknown
  functions in a generated column at CREATE time: checked). Postgres-only index options
  (`postgresql_using="hnsw"`, ops) are ignored by SQLite.
- **Alternatives**: leaving `tsv` out of the models (044 then needs `literal_column`, and the
  metadata lies about the schema); a PG-only `__table_args__` switch (models import-time
  dialect knowledge: worse).

## R4. Keyword index per kind in one table

- **Decision**: `kb_chunks.tsv GENERATED ALWAYS AS (to_tsvector(CASE WHEN kind = 'wcl' THEN
  'simple'::regconfig ELSE 'english'::regconfig END, text)) STORED`; `kb_chat_chunks.tsv` uses
  `'english'`. The literal casts fold to constants, so the expression is immutable (verified on
  the container).
- **Rationale**: the design's per-kind config without a second table. 044 must use the same
  config in `to_tsquery` per kind (stated in the data model).

## R5. Embedder

- **Decision**: `VertexEmbedder` calls `client.aio.models.embed_content(model, contents,
  config=EmbedContentConfig(task_type, output_dimensionality=768, auto_truncate=True))` on the
  shared genai client (`wcl_agent.llm.provider.genai_client()`, Vertex at the model location,
  or the API-key setup), through the shared rate-limit loop
  (`wcl_agent.llm.generation._with_retry` with its own `RetryPolicy(attempts=4, budget_s=60)`).
  Vectors are L2-normalised in Python. Requests carry at most `kb_embed_request_batch` texts
  (default 1: gemini-embedding-001 on Vertex historically took one input per request;
  live-check whether a larger batch works and raise the default then).
- **`get_embedder()`**: the injected embedder when one is set (tests), else `None` when
  `kb_embed_enabled` is off or the client can't be built (no credentials), else a cached
  `VertexEmbedder(settings.kb_embed_model)`. Never raises.
- **Provider layer (corrected at sc-111):** `test_provider_e2e` allows only `provider.py` and
  `generation.py` to build or call model clients. So the SDK call goes into
  `wcl_agent/llm/generation.py` as `embed_texts(model, texts, *, task, dimensions, policy)` (raw
  vectors, one request, through `_with_retry`) plus `embeddings_available()`; `kb/embedder.py`
  keeps batching, dimension checks and normalisation. Grant requested for sc-112.
- **Alternatives**: `text-embedding-005` (sc-115 may switch; `embed_model` per row makes that a
  re-embed); SDK retries (off project-wide, feature 011).

## R6. Queue and retry

- **Decision**: one `KbIndexer` per process, started by the lifespan, modelled on the 039
  `FetchWriter`: `offer_*` methods are O(1) and never await; a bounded `asyncio.Queue` of jobs;
  one consumer task. Each job (fetch, guide, exchange) is chunked and written in its own short
  transaction, then the consumer embeds pending rows of what it just wrote (NULL vectors) in
  batches of `kb_embed_batch`. The consumer's `queue.get` times out every
  `kb_embed_sweep_s` (default 600): the sweep embeds all remaining NULL rows (global directly;
  chat per tenant under `tenant_scope`). After an embed failure the consumer stops embedding
  until the next sweep (rows stay NULL, keyword-searchable). A vector is written with
  `UPDATE … WHERE id = :id AND content_hash = :hash` so a changed chunk never gets a stale
  vector. Shutdown: bounded drain like the writer.
- **Rationale**: the table is the durable backlog (#33); one task means no sweep/consumer race.
- **Alternatives**: a jobs table (more schema for no present need); Redis queue (tenant-less,
  rejected for chat text); embedding inline in the writer (would slow the 039 writer).

## R7. What a fetch job carries, and the hook

- **Decision**: per Contract 5 (#45) Tomas's sc-295 writer reports per item whether the stored
  payload changed. After `store_batch` commits, the writer calls
  `kb.indexer.offer_fetch(FetchedResponse)` for each changed item whose
  `exact_report_codes(query, variables)` is non-empty. The job keeps the in-memory response
  (query text, variables, body bytes): no re-read of `raw_fetches`, so `backend/app/kb` never
  touches the 039-guarded table. Body parsing runs in a thread above 256 kB (like the writer).
  The offer is skipped when no indexer is running (CLI, tests).
- **Edit window**: `fetch_persistence.py` and `config.py` after 045 part 1 merges; `raw_fetches.py`
  only for the backfill iterator, released straight after.

## R8. WCL chunk shapes

- **Decision**: recognised bodies (anything else yields no chunks):
  - **Report summary** (`ReportSummary`, `ReportsBatch`): per fight with `encounterID > 0`
    (bounded `MAX_FIGHTS = 60` per report), one `fight:<id>` chunk.
  - **Table** (`reportData.report.table.data`): metric from the query text
    (`table(dataType: X`) on the live path; in the backfill (no query text stored) from the
    body: `playerDetails` → Summary, entries with `deathTime` → Deaths, `auras` → Auras; plain
    `entries` with `total` → ambiguous → skipped (#35). `fight_id` = the single `fightIDs`
    value, else NULL (whole report). One `table:<metric>:<fight>` chunk with the top 10
    entries; when the table has more than 10 entries, one `player:<metric>:<fight>:<name>`
    chunk per entry (bounded 40). A source-filtered table (one player) yields one player chunk
    with its top abilities.
  - Table chunks copy `encounter_id`, `difficulty`, `kill`, `start_time`, `zone_id` and the
    "Heroic Ula'tek, kill" phrase from the same report's `fight:<id>` chunk when it exists
    (one indexed lookup in `kb_chunks`).
- **Text**: the design's example format, numbers humanised (139.1M), bounded to 2,000 chars.

## R9. Name normalisation seam

- **Decision**: `backend/app/kb/names.py` is the only place the chunkers normalise names:
  `name_key`, `class_spec`, `difficulty_name`, `mentioned_characters`. Until 044's
  `name_resolver.py` merges it uses `normalize_class_name` / `role_for_spec` from
  `wcl_agent/game/constants.py` and a casefold key; after the merge it delegates (one edit in
  one file; asked Nils for a public `name_key`, #36).
- **Mentions** (chat): the workspace's `user_characters` and `known_players` names (read under
  the tenant scope), matched against the exchange's words by key; bounded to 20.

## R10. Cost estimate

- **Decision**: tokens ≈ characters / 4; cost = tokens / 1e6 × `kb_embed_price_per_mtok`
  (default 0.15 USD, gemini-embedding-001 on Vertex). Printed per kind with the chunk count.
  Live check confirms the price.

## R11. Chat chunk text

- **Decision**: `Question: <user message>\n\nAnswer: <final answer>`; the answer is the saved
  agent message (streamed text only: tool results travel as `tool_end` records and never enter
  the tokens). Bounded to 6,000 chars (head kept). Only completed turns (#34).
