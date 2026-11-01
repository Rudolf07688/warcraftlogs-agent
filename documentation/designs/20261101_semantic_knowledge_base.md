# Semantic knowledge base: design notes (epic 100)

Agreed between the owner and team-lead on 2026-11-01, for the next sprint. These are design
notes, not acceptance criteria. The product owner and the developers write the ACs, and may
change details when the code says otherwise. If they do, they post the reason on the board.

## Goal

The agent searches what the app already knows before it calls Warcraft Logs. That covers
stored WCL data, the grounded class guides, and past conversations. It can run several
searches in parallel, and every result is one the asking user is allowed to see. This moves
us toward the epic 103 goal: answer 80% of questions without an external API call.

## Owner decisions (2026-11-01)

| Question | Decision |
|---|---|
| Scope | WCL fetches + class guides + past conversations |
| Embeddings | Vertex (`gemini-embedding-001` or `text-embedding-005`, see below) |
| Vector store | pgvector in the existing Postgres |
| Keyword side | Postgres full-text search, merged with vector results by Reciprocal Rank Fusion |
| Metadata filters | Agent fills typed filter parameters; the server resolves and validates them |
| Size | Big sprint, about 33 pts: epic 100 + sc-131, sc-132, sc-295, sc-296 |

## Visibility (the non-negotiable part)

Each source keeps the visibility it already has. No new sharing rules:

| Source | Today's rule | Rule for its chunks |
|---|---|---|
| WCL fetches (`raw_fetches`) | Global table; served only if every report code is public or granted to the workspace, within the re-verify window (039, `read_visible_fetch`) | Same check, joined at search time through the chunk's `raw_fetch_id`. Chunks never bypass it. |
| Class guides (`spec_guides`) | Global, no tenant, no RLS | Global |
| Conversations (`conversations`, `messages`) | Workspace-scoped (tenant RLS). There's no per-user column, so every member of a workspace sees its chats. | Workspace-scoped, under the same tenant RLS policy |

- **Deletes cascade.** Deleting a conversation, a stored fetch (including "report gone") or
  a guide deletes its chunks through a foreign key with `ON DELETE CASCADE`.
- **Suggested layout:** two tables, so each gets the RLS it needs without a nullable-tenant
  policy:
  - `kb_chunks` holds global chunks (WCL and guides);
  - `kb_chat_chunks` holds tenant chunks under the standard `tenant_isolation` policy.
  - Search queries both and merges the results.
- **Security-core work** (P7 in `meta/team-optimisation.md`): the visibility join and the
  chat RLS get a scoped `qa-security` review at hand-off, plus the usual bypass attempts.
  Bypass ideas to try:
  - a chunk whose fetch is no longer visible;
  - a chat chunk from another workspace;
  - filter parameters crafted to widen the scope;
  - a deleted conversation.

## Storage: pgvector

- **Image:** `pgvector/pgvector:pg17` replaces `postgres:17` in `docker-compose.yml` and in
  the developers' throwaway test containers.
  - It's the official image plus the extension. It's the same major version, so the
    existing data volume stays compatible.
  - The owner pulls it once. `bin/01_start_app.sh --build` works as before.
- **Migration 0019:**
  - `CREATE EXTENSION IF NOT EXISTS vector`; Alembic runs as the owner role, which is a
    superuser.
  - Then the chunk tables and their indexes.
- **Dependency:** the `pgvector` Python package, for the SQLAlchemy column type. This
  touches the lockfile, so the brief must grant it.
- **Columns per chunk:**
  - **Identity:** `id`, `kind` (`wcl` | `guide` | `chat`), the source key
    (`raw_fetch_id` | `guide_id` | `conversation_id` + `message_seq`).
  - **Content:**
    - `text`: the rendered chunk, i.e. what gets embedded and keyword-searched;
    - `content_hash`: an unchanged chunk is never re-embedded.
  - **Vector:** `embedding vector(768)`, `embed_model`, `embedded_at`. Rows waiting for an
    embedding have a NULL vector and are keyword-searchable only.
  - **Keyword:** a generated `tsvector`:
    - the `simple` config for WCL (no stemming, so names, spells and report codes stay
      intact);
    - the `english` config for guides and chats.
  - **Filters**, as typed columns (see below), plus `extra jsonb` for the long tail.
- **Indexes:**
  - an HNSW index on `embedding` (`vector_cosine_ops`);
  - a GIN index on the `tsvector`;
  - B-tree indexes on the selective filters (`report_code`, `encounter_id`, `class`/`spec`,
    `kind`, `tenant_id`);
  - a GIN index on `extra`.
- **Filtered vector search:**
  - use pgvector ≥ 0.8 with `hnsw.iterative_scan` enabled, so a WHERE clause doesn't
    starve the results;
  - for a very selective filter (one report code), Postgres just scans those rows exactly.

## Embeddings: Vertex

- **Access:** both models were checked from this machine on 2026-11-01, using the existing
  GCP config in `.env`:
  - `gemini-embedding-001` with `output_dimensionality=768` returned 768 dimensions;
  - so did `text-embedding-005`.
  - This works while chat runs on the Anthropic provider; it only needs the GCP credentials.
- **Default model:** `gemini-embedding-001` at 768 dimensions.
  - Normalise the vectors, because truncated Gemini embeddings aren't unit length.
  - sc-115's eval may switch to `text-embedding-005`. `embed_model` per row makes a switch a
    re-embed, not a schema change.
- **Task types:** `RETRIEVAL_DOCUMENT` when writing, `RETRIEVAL_QUERY` when searching.
- **Never on the hot path:**
  - embedding runs in a background queue, the same way the 039 fetch writer does, batched
    and retried;
  - a chat turn never waits for an embedding.
- **Rate limits and cost:**
  - go through the shared rate-limit layer (`wcl_agent/llm`);
  - the backfill prints a chunk count and a cost estimate before it runs, and can resume.

## Chunking: one meaningful unit per chunk, rendered as text

Raw JSON embeds badly. Each chunker turns its source into short, readable text with the key
names spelled out, and keeps a pointer back to the source:

- **WCL fetches:**
  - one chunk per fight summary;
  - per table, one chunk per fight and metric, holding the top entries;
  - per player per fight, for large tables.
  - Example: "Report BKNtypgnhrxXvj84, fight 32, Heroic Ula'tek, kill, 535 s. Damage done:
    Vagxsu (Arms Warrior) 139.1M, …"
- **Guides:** one chunk per markdown section, with the class, spec, role, content type and
  section title in the text.
- **Chats:** one chunk per exchange (the user message plus the agent's answer). Leave out
  tool payloads and frames; the WCL data they returned is already a `wcl` chunk.

## Metadata: extracted at write time, from structure, not from a model

| Source | Filter columns | Where they come from |
|---|---|---|
| WCL | `report_code`, `zone_id`, `encounter_id`, `difficulty`, `fight_id`, `kill`, `start_time`, players (names, with class and spec), `region`, `realm`, `guild` | The query variables and the response; `raw_reports` for visibility and end time |
| Guide | `class`, `spec`, `role`, `content_type`, `patch`, `section` | The `spec_guides` row and the guide pipeline |
| Chat | `tenant_id`, `conversation_id`, `created_at`, characters mentioned | The conversation row; mentions resolved against `user_characters` and `known_players` |

There's one shared **name resolver** (new story), used both when writing and when
searching. It reuses:
- `wcl_agent/game/constants.py` (`normalize_class_name`, spec roles);
- `wcl_agent/game/roster.py` (`resolve_spec`);
- the zone and encounter data from `wcl_agent/game/patch.py` and `known_encounters`;
- characters from `user_characters` and `known_players`.

## Query side: the agent extracts the filters, the server checks them

- **One tool.** `search_knowledge(queries: list[str] 1–5, kind?, class?, spec?, encounter?,
  difficulty?, report_code?, character?, since?/until?, k?)`.
  - `kind`, `class`, `spec` and `difficulty` are enums in the tool schema, so the model
    can't invent values.
  - The queries run in parallel (`asyncio.gather`), each as a hybrid search.
  - The results are merged across queries by RRF and deduplicated by source.
- **Hybrid search per query:**
  - take the top N by vector distance and the top N by `ts_rank_cd`;
  - merge them by RRF (`1/(60 + rank)`);
  - the visibility joins run inside the SQL;
  - true BM25 (ParadeDB `pg_search`, VectorChord-bm25, `pg_textsearch`) only if sc-115's
    eval shows keyword ranking is the weak spot. Some of these are AGPL, so check the
    licence first.
- **Filters are extracted by the chat model** as it calls the tool, with the context it
  already has (the user's characters, and the report and boss mentioned earlier in the
  chat). There's no separate "self-query" model call.
- **The server normalises and validates.**
  - The name resolver maps "Ula'tek" to its encounter ID and "arms warr" to Warrior with the
    Arms spec.
  - An unknown value returns a clear error the agent can correct, never a silent empty
    result.
- **Hard vs soft filters:**
  - Visibility is always hard.
  - `kind`, `report_code` and filters the user stated explicitly are hard.
  - Everything else is soft. When fewer than k results come back, the server relaxes the
    filters in a fixed order (spec, then class, then encounter, then the dates) and reports
    which ones it relaxed, so the agent can say so.
- **Result shape:** for each hit, return the chunk text, kind, source pointer (report
  code + fight, guide section, conversation + seq), score, and the relaxed filters. Keep it
  compact, because results go into the model's context (compare sc-302, a 220k-token turn).

## sc-131 vs sc-114

- **sc-131 (agent tools to query stored data)** is exact, structured lookups:
  - e.g. "stored fights for report X", "stored table for fight 32", "reports stored for
    character Y";
  - they read through `read_visible_fetch`, with no embeddings.
- **sc-114** is the semantic and hybrid search. The two share the name resolver.

## Measuring it

- **sc-115** builds a small labelled set: about 30 questions over a fixture corpus covering
  all three kinds. It measures:
  - recall@k, hybrid vs vector-only;
  - how accurately the agent extracts filters;
  - latency;
  - the local-answer rate with search-first prompting on.
- **sc-132 and sc-295** add hit, miss, not-visible and timeout counters to the existing
  cache stats. That's the baseline for "80% answered locally".

## Live checks (team-lead, at the end of the sprint)

- **Migration and image:**
  - back up the database;
  - switch to the pgvector image and migrate to 0019;
  - check that the existing data survives.
- **Embedding:**
  - ask a report question, then confirm a `wcl` chunk with a vector appears;
  - in a new chat, ask a related question and see `search_knowledge` hit it;
  - make sure the turn doesn't load the full table into context.
- **Guides:** a guide question is answered from `guide` chunks.
- **Chats:** one chat refers back to another ("what did we say about my Arms build?"). Then
  delete that chat and confirm its chunks are gone.
- **Spend:** the backfill's cost estimate is printed before it runs; Haiku is used for the
  chat turns.

## Points (estimates set 2026-11-01)

| Story | Pts |
|---|---|
| sc-111 Vector store setup (pgvector image, migration 0019, chunk tables, FTS, indexes, chat RLS) | 3 |
| sc-112 Embed WCL fetches and guides on write (chunkers, metadata, background embed queue) | 5 |
| sc-305 Embed conversations (exchange chunks, tenant RLS, delete cascade) | 3 |
| sc-304 Shared name resolver (encounters, classes, specs, characters) | 2 |
| sc-113 Backfill (cost estimate first, resumable) | 2 |
| sc-114 Parallel hybrid search tool with filters and relaxation | 5 |
| sc-115 Search-first prompting + eval | 3 |
| sc-131 Agent tools for exact lookups in stored data | 3 |
| sc-132 Local-answer hit rate | 2 |
| sc-295 QA: cheap, fail-fast raw-store probe and writer | 3 |
| sc-296 QA: revocation lag and gone-vs-write races | 2 |
| **Total** | **33** |
