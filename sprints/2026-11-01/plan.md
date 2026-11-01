# Sprint 2026-11-01: semantic knowledge base (epic 100 + 4 from epic 103)

PO: Maren. Tier L (SM + three developers). Branch `sprint-2026-11-01`, base `ec966c5`.
Design: `documentation/designs/20261101_semantic_knowledge_base.md` (agreed with the owner).
33 points planned, nothing added beyond the steer.

## Goal

The agent searches what the app already knows (stored WCL fetches, class guides, past
chats of the same workspace) before it calls Warcraft Logs, with several searches in
parallel, and every result is one the asking user may see.

## User flow

1. A user asks about a report. The fetch is stored (039); in the background its fights and
   tables are chunked into readable text and embedded (Vertex, 768-d).
2. Every saved exchange in a chat is chunked and embedded the same way, in the
   workspace's own table.
3. Later, in a new chat, the user asks a related question. The agent calls
   `search_knowledge` with 1–5 queries and typed filters (or an exact lookup tool), gets
   compact, visible-only hits, and answers without a WCL call where it can.
4. The owner sees hit/miss counters and the local-answer rate in the cache stats.

## Features

| Feature | Stories | Pts | Tier | Model (recommended) | Worktree |
|---|---|---|---|---|---|
| 043-kb-store-embed | sc-111, sc-112, sc-305, sc-113 | 13 | L | Ansel (dev-1), opus/high | dev-a |
| 044-kb-search | sc-304, sc-114, sc-115 | 10 | L | new dev-3, opus/high | dev-b |
| 045-local-data-reads | sc-295, sc-296, sc-132, sc-131 | 10 | M (under SM) | Tomas (dev-2), opus/medium | dev-c |

Migration: `0019_kb_chunks`, `down_revision = "0018_raw_store_visibility"`, feature 043 only.
Lockfile (`pgvector`) and `docker-compose.yml` (image `pgvector/pgvector:pg17`): 043 only.

## Order and dependencies

1. Milestone merges first: **sc-304** (044, the resolver) and **sc-111** (043, schema + models).
2. 043 then sc-112 and sc-305 (need the resolver), then sc-113 (needs both chunkers).
3. 044 then sc-114 (needs the 0019 schema; tests insert chunks directly), then sc-115.
4. 045 runs sc-295 -> sc-296 -> sc-132 from the start; sc-131 after the resolver merges.
5. Shared files the SM sequences: `wcl_agent/agent.py` (044, 045),
   `backend/app/services/fetch_persistence.py` (043 hook, 045 writer), the chat-turn
   persistence path (043 sc-305, 045 sc-132).

P7: scoped `qa-security` review at hand-off for sc-111, sc-112, sc-305 (043) and sc-114
(044), plus bypass attempts: a chunk whose fetch is no longer visible, another workspace's
chat chunk, filters crafted to widen scope, a deleted conversation.

## Acceptance criteria

### sc-111 Vector store setup (3)
1. `docker-compose.yml` and the throwaway test-container recipe use `pgvector/pgvector:pg17`. A copy of an existing pg17 data volume starts under the new image with its data intact (proved on a copy, never the compose volume).
2. Migration 0019 (`down_revision = "0018_raw_store_visibility"`) runs `CREATE EXTENSION IF NOT EXISTS vector` and creates `kb_chunks` (global; kind `wcl` | `guide`; FK `raw_fetch_id` / `guide_id` `ON DELETE CASCADE`) and `kb_chat_chunks` (`tenant_id`, `conversation_id` FK `ON DELETE CASCADE`, `message_seq`; RLS enabled and forced with the standard `tenant_isolation` policy).
3. Both tables have `text`, `content_hash`, `embedding vector(768)` (nullable), `embed_model`, `embedded_at`, a generated `tsvector` (`simple` for wcl, `english` for guide and chat), typed filter columns per the design, and `extra jsonb`.
4. Indexes: HNSW (`vector_cosine_ops`), GIN on the tsvector, B-tree on the selective filters, GIN on `extra`. The extension version is checked to be >= 0.8.
5. Upgrade, downgrade, upgrade is clean on Postgres, and the existing SQLite suite stays green.
6. Postgres tests: a session scoped to workspace B sees none of workspace A's chat chunks and cannot insert one with A's tenant id; deleting a raw fetch, a guide and a conversation deletes their chunks.
7. The `pgvector` package is added to `pyproject.toml` and `uv.lock`, with SQLAlchemy models for both tables.

### sc-304 Shared name resolver (2)
1. One module resolves encounter (name to id, via `patch.py` and `known_encounters`), class, spec (with role), difficulty and character (`user_characters`, `known_players`), reusing `normalize_class_name` and `resolve_spec`; no second class/spec map.
2. Matching is case-, accent- and apostrophe-insensitive; `warr, dh, dk, ret, prot, resto, disc, bm, mm, sv` resolve (a test per abbreviation); "Ula'tek" and "ulatek" give the same id; "arms warr" gives Warrior / Arms.
3. An unknown or ambiguous value returns a typed, correctable error with close matches; never a silent empty result.
4. Both the chunk writers (sc-112, sc-305) and search (sc-114, sc-131) use it (checked at merge).

### sc-112 Embed WCL fetches and guides on write (5)
1. The WCL chunker renders readable text (design example format): one chunk per fight summary, per fight and metric with the top entries (bounded), per player per fight for large tables. Each chunk keeps `raw_fetch_id`, `report_code`, `fight_id`.
2. Filter columns come from the query variables and the response (report_code, zone_id, encounter_id, difficulty, fight_id, kill, start_time, players with class and spec, region/realm/guild where present), normalised by the resolver. No model call.
3. The guide chunker writes one chunk per markdown section, with class, spec, role, content type and section title in the text; a regenerated guide replaces its chunks (no stale sections).
4. Embeddings: Vertex `gemini-embedding-001`, `output_dimensionality=768`, `RETRIEVAL_DOCUMENT`, L2-normalised (a test asserts unit norm); `embed_model` and `embedded_at` stored; the model name is configurable.
5. Background queue only: batched, retried with backoff, through the shared rate-limit layer. No fetch or chat turn awaits it. When Vertex fails, rows keep a NULL embedding (keyword-searchable) and are retried later.
6. An unchanged `content_hash` is never re-embedded (a test counts embed calls).
7. A deleted or gone fetch loses its chunks (cascade, tested). No new read path serves chunks outside the visibility rule.
8. CI never calls Vertex (the embedder is injectable and faked).

### sc-305 Embed past conversations (3)
1. After a turn is persisted, one chunk per exchange (user message + the agent's final answer) is queued; tool payloads and frames are left out (tested).
2. Chunks land in `kb_chat_chunks` with `tenant_id`, `conversation_id`, `message_seq`, `created_at` and characters mentioned (via the resolver).
3. Embedding runs in the background queue, never on the chat hot path; an unchanged `content_hash` is not re-embedded.
4. Postgres tests: deleting a conversation deletes its chunks; another workspace never sees them.

### sc-113 Backfill (2)
1. A `backend.cli` command backfills raw fetches, guides and conversations with the sc-112 / sc-305 chunkers.
2. Without a confirm flag it prints the chunk count per kind and an estimated cost, then exits without embedding.
3. It is resumable and idempotent: a re-run skips chunks whose `content_hash` already has an embedding (tested, including resume after an interruption).
4. Rate-limited through the shared layer; not a startup task.

### sc-114 Parallel hybrid search tool (5)
1. `search_knowledge(queries 1–5, kind?, class?, spec?, encounter?, difficulty?, report_code?, character?, since?, until?, k?)` is registered on the agent; `kind`, `class`, `spec` and `difficulty` are enums in the schema; the queries run concurrently.
2. Per query: top N by cosine distance (`RETRIEVAL_QUERY` embedding) and top N by `ts_rank_cd`, fused by RRF `1/(60+rank)`; then fused across queries and deduplicated by source.
3. Visibility runs inside the SQL: WCL chunks only when their fetch passes the `read_visible_fetch` rule for the caller's workspace; chat chunks under tenant RLS; guides global. Postgres tests: a fetch that is no longer visible returns nothing; another workspace's chat never returns; no filter combination widens the scope.
4. Filters are normalised by the resolver; an unknown value returns a correctable error to the agent, not an empty result.
5. Visibility, `kind`, `report_code` and user-stated filters are hard. Others relax in the order spec, class, encounter, dates when fewer than k results come back, and the result names the relaxed filters.
6. Each hit is compact (truncated text, kind, source pointer, score); the total output is capped (tested).
7. When embeddings are unavailable (Vertex down, NULL vectors), search falls back to keyword-only and says so.

### sc-115 Search-first prompting + eval (3)
1. The agent instruction tells it to try `search_knowledge` or an exact lookup before a WCL fetch when the question could be answered locally (tested against the rendered instruction and capabilities).
2. An eval harness with about 30 labelled questions over a fixture corpus (wcl, guide, chat) measures recall@k hybrid vs vector-only and latency in CI, with recorded embeddings (CI never calls Vertex).
3. A live mode (cheapest model, capped) measures filter-extraction accuracy and the local-answer rate with and without search-first; team-lead runs it at sprint end.
4. A short write-up in the spec dir recommends the embedding model and whether true BM25 is worth it (licence noted). The default model changes only on a clear eval win.

### sc-131 Exact lookups in stored data (3)
1. Agent tools return stored fights for a report, the stored table for a report fight (and metric), and reports stored for a character, reading only through the `read_visible_fetch` rule; no embeddings.
2. Not visible and not stored both return the same "not stored locally" result, so the agent falls back to WCL and the existence of invisible data never leaks.
3. Character and encounter arguments are normalised by the resolver.
4. Output is compact and bounded; tests cover a not-visible fetch.

### sc-132 Local-answer hit rate (2)
1. Raw-store probe counters `hit`, `miss`, `not_visible`, `timeout` appear in the existing cache stats (`read_stats`) wherever those are shown today.
2. A turn with no external WCL call counts as answered locally; the local-answer rate over the stats window is exposed with the cache stats.
3. Tests for both.

### sc-295 Cheap, fail-fast raw-store probe and writer (3)
1. The probe timeout is configurable with a default of 500 ms or less, and a breaker (about 30 s) opens after a timeout or connection error so no probe runs while it is open (tested with a hung session).
2. The probe looks up the row first; a miss costs at most 2 round trips; a hit merges the `set_config` calls and fetches visibility and payload in one statement (tested by statement count).
3. The probe no longer holds a connection across a fan-out (it runs after single-flight and the lane limiter).
4. The writer no longer rewrites the scope and the grant when unchanged (fewer round trips per item, tested).
5. A store hit no longer re-serialises the JSONB on the event loop.
6. PERF-007: a decision on skipping the probe for Redis-cached families, based on the sc-132 counters, posted on the board.
7. All 039 visibility tests stay green.

### sc-296 Revocation lag and gone-vs-write races (2)
1. A store hit for a granted-only (non-public) row never back-fills the shared Redis entry (tested).
2. A stale fetch written after a ReportGone does not bring back the row or its grant, and a loader cannot refill Redis after the eviction (tested), or each race is reported "not reproduced, with evidence".

## Key decisions (board keys)
- `decision:features`: three dependency chains, one developer each.
- `decision:order`: resolver and schema merge first.
- `tier:043/044/045`: L, L, M under the SM.
- `decision:staffing`: model recommendations.
- `decision:drop-order`: sc-115 live parts, then sc-296, then sc-113.

## Risks
- Critical path: sc-111 -> sc-112 -> real chunks for the eval. Mitigated: sc-114/115 test on directly inserted chunks.
- Shared files (`agent.py`, `fetch_persistence.py`, chat persistence) across streams: the SM grants them in sequence.
- The image swap touches the owner's data volume: proved on a copy; team-lead backs up first.
- Disk (21 GB free): throwaway pgvector containers are removed after use.
- Context bloat from search results (compare sc-302): hard output cap in sc-114.
