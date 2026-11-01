# Brief 043: knowledge base store and embedding

Read `sprints/2026-11-01/briefs/common.md` first: team, contracts, ownership, environment,
hand-off contents. This file adds what is specific to 043.

- **Feature / branch:** 043, `043-kb-store-embed`
- **Tier:** L (Spec Kit: specify, clarify (self-answered), plan, tasks, implement) with gates.
- **Seat:** `dev-1` (Ansel). Model opus, effort high.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a`. Base `sprint-2026-11-01` (`cda1f42 or later`).
- **Parallel developers:** dev-3 on 044 (`dev-b`), Tomas on 045 (`dev-c`).
- **Migration assigned:** `0019_kb_chunks`, `down_revision = "0018_raw_store_visibility"`. You are
  the only developer adding a migration, touching the lockfile or `docker-compose.yml`.
- **Throwaway Postgres:** `wcl-043-pg`, port 15443, `pgvector/pgvector:pg17`.
- **Stories (Shortcut):** sc-111, sc-112, sc-305, sc-113 (13 pts), in that order.

## Gates and stops
1. **Gate 1 (spec):** after `/speckit-specify` + `/speckit-clarify`. Return the spec path and
   your clarify decisions.
2. **Gate 2 (plan):** after `/speckit-plan` + `/speckit-tasks`. Return the plan path, the
   Constitution Check, GitNexus impact for the risky symbols (the writer path, turn
   persistence, guide publish) and the **exact file list per story**. I grant from that list.
3. **Stop 3 (sc-111 milestone):** implement sc-111 plus the embedder contract
   (`backend/app/kb/embedder.py`, Protocol + `get_embedder()` + test injection point), commit,
   and return a hand-off for just that. I run the P7 review and merge it early: 044 waits on
   the schema and models.
4. **Final:** sc-112, sc-305, sc-113 on the rebased branch. P7 review of sc-112 and sc-305 at
   this hand-off.

## Ownership
**Granted now (whole feature):** `docker-compose.yml`, `pyproject.toml`, `uv.lock`,
`backend/migrations/versions/0019_kb_chunks.py`, `backend/app/db/models.py` (the kb models),
`backend/app/kb/**` except `backend/app/kb/search.py` (044), `backend/cli/kb_backfill.py`,
new tests `backend/tests/test_kb_store*.py`, `test_kb_chunk*.py`, `test_kb_embed*.py`,
`test_kb_chat*.py`, `test_kb_backfill*.py`, and `specs/043-kb-store-embed/**`.

**Granted at Gate 2 from your file list (expected):** `backend/app/api/ws.py` (sc-305 enqueue
after the turn is persisted; yours alone), the guide publish hook (`backend/app/db/repository.py`
or `backend/app/services/guide*`), app lifespan wiring (`backend/app/main.py` / `startup.py`).

**Sequenced (after Tomas's 045 part 1 merges: sc-295 + sc-296):**
`backend/app/services/fetch_persistence.py` (the post-store hook), `backend/app/config.py`
(embedding settings), `backend/app/repositories/raw_fetches.py` (the stored row id for the
hook, the backfill iterator). Plan to do these edits **first** in sc-112/sc-113, commit, and
post `released` for `raw_fetches.py` straight away: Tomas needs it back for sc-131. Build the
chunkers, embedder and queue in your own files before that, so you never wait.

Notes:
- The test-container recipe for sc-111 AC1 goes in your `specs/043-kb-store-embed/quickstart.md`.
  If `developer.md` or a skill should change to `pgvector/pgvector:pg17`, post a board `notice`
  keyed `skill:<name>` (team-lead edits those files). Prove the old-volume compatibility on a
  copy of a throwaway pg17 volume, never the compose volume.
- Use the resolver (`backend/app/services/name_resolver.py`) once sc-304 merges; until then
  write the chunkers so the normalisation call is one seam.
- Embedding rate limits go through the shared layer in `wcl_agent/llm` (read it; reuse it).
  If you need to change a file there, it's a Gate-2 grant request.

## Acceptance criteria (verbatim from the plan)

### sc-111 Vector store setup (3)
1. `docker-compose.yml` and the throwaway test-container recipe use `pgvector/pgvector:pg17`. A copy of an existing pg17 data volume starts under the new image with its data intact (proved on a copy, never the compose volume).
2. Migration 0019 (`down_revision = "0018_raw_store_visibility"`) runs `CREATE EXTENSION IF NOT EXISTS vector` and creates `kb_chunks` (global; kind `wcl` | `guide`; FK `raw_fetch_id` / `guide_id` `ON DELETE CASCADE`) and `kb_chat_chunks` (`tenant_id`, `conversation_id` FK `ON DELETE CASCADE`, `message_seq`; RLS enabled and forced with the standard `tenant_isolation` policy).
3. Both tables have `text`, `content_hash`, `embedding vector(768)` (nullable), `embed_model`, `embedded_at`, a generated `tsvector` (`simple` for wcl, `english` for guide and chat), typed filter columns per the design, and `extra jsonb`.
4. Indexes: HNSW (`vector_cosine_ops`), GIN on the tsvector, B-tree on the selective filters, GIN on `extra`. The extension version is checked to be >= 0.8.
5. Upgrade, downgrade, upgrade is clean on Postgres, and the existing SQLite suite stays green.
6. Postgres tests: a session scoped to workspace B sees none of workspace A's chat chunks and cannot insert one with A's tenant id; deleting a raw fetch, a guide and a conversation deletes their chunks.
7. The `pgvector` package is added to `pyproject.toml` and `uv.lock`, with SQLAlchemy models for both tables.

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

## P7 bypass attempts you should already have tests for
A chat chunk from another workspace (read and insert), a deleted conversation (chunks gone),
a deleted / report-gone fetch (chunks gone), a chunk insert that skips the tenant scope.
