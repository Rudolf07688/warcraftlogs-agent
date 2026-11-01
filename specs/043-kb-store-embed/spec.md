# Feature Specification: Knowledge base store and embedding

**Feature Branch**: `043-kb-store-embed`

**Created**: 2026-11-01

**Status**: Draft (Gate 1)

**Input**: Feature 043 of sprint 2026-11-01 (epic 100, semantic knowledge base): sc-111 vector
store setup, sc-112 embed WCL fetches and guides on write, sc-305 embed past conversations,
sc-113 backfill. ACs verbatim in `sprints/2026-11-01/briefs/043-kb-store-embed.md`; agreed
design in `documentation/designs/20261101_semantic_knowledge_base.md`.

This feature builds the **write side** of the knowledge base: where chunks live, how the
app's existing data (stored Warcraft Logs responses, published class guides, finished chat
exchanges) becomes short readable chunks with typed filters, and how those chunks get a
vector in the background. The **read side** (hybrid search, the agent tool, the name
resolver) is feature 044; the exact-lookup tools are 045.

## Clarifications

### Session 2026-11-01

Self-answered (tier L, owner preference 16); board keys `clarify:043-*`.

- Q: What does a WCL chunk point at, given `raw_fetches` is keyed by `query_key`? → A: `kb_chunks.raw_fetch_id` holds the fetch's `query_key` (FK to `raw_fetches.query_key`, `ON DELETE CASCADE`); the name follows contract 3 (`fetch_visible_clause(raw_fetch_id, …)`).
- Q: Which stored fetches get chunked, and when? → A: Only fetches whose stored body actually changed and that name at least one exact report code (039 can never serve the rest), in a recognised shape: report summary (single or batch) and `table` bodies (Summary, Deaths, entry tables such as DamageDone/Healing/Casts/DamageTaken, aura tables). Events, graphs, rankings, character data and unknown shapes produce no chunks. A table chunk copies encounter, difficulty, kill and start time from the same report's fight-summary chunk when one exists.
- Q: How is the embed backlog kept and retried? → A: The table is the backlog: a NULL vector means "pending". An in-process bounded job queue (like the 039 writer) chunks sources and embeds pending rows in batches; a periodic sweep (default every 10 min) retries NULL rows, global ones directly and chat ones per workspace under that workspace's scope. A vector is written only if the row's content hash still matches what was embedded. A model switch does not auto re-embed.
- Q: Which turns become chat chunks, and how are they keyed? → A: Only completed turns (the saved final answer), keyed by `(conversation_id, message_seq)` where `message_seq` is the agent answer's seq. The conversation link is a composite FK `(conversation_id, tenant_id)` → `conversations(id, tenant_id)` (a new unique constraint), so a chunk can never name another workspace's conversation, even though FK checks bypass RLS.
- Q: What does the backfill skip and estimate? → A: The dry run writes nothing. A confirmed run skips sources that already have chunks (so a live-indexed fetch is never re-chunked with less context) and embeds only NULL rows. Stored rows keep no query text, so a stored `table` whose metric can't be told from its body is skipped by the backfill. Cost = estimated tokens (characters / 4) × a configurable price per 1M tokens (default USD 0.15 for `gemini-embedding-001`, confirmed in the live check).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A store for knowledge chunks that keeps each source's visibility (Priority: P1, sc-111)

The operator upgrades the app to the vector-capable database image and migrates. Two chunk
stores appear: one global store for Warcraft Logs and guide chunks, one workspace-scoped store
for chat chunks that the database itself fences per workspace. Deleting a stored fetch, a
guide or a conversation deletes its chunks with it.

**Why this priority**: every other story (044's search included) writes to or reads from
these tables. It is the milestone the search stream waits on.

**Independent Test**: on a throwaway Postgres with the new image, run the migration up, down
and up again; insert chunks directly; check workspace isolation and cascades as the runtime
role.

**Acceptance Scenarios**:

1. **Given** a copy of an existing database volume made with the old image, **When** it starts
   under the new image, **Then** its data is intact and the migration to 0019 succeeds.
2. **Given** a session scoped to workspace B, **When** it reads chat chunks, **Then** it sees
   none of workspace A's, and inserting a chunk with A's workspace id is refused.
3. **Given** a chat chunk scoped to workspace B, **When** it names a conversation of workspace
   A, **Then** the insert is refused.
4. **Given** chunks for a stored fetch, a guide and a conversation, **When** each source is
   deleted (a fetch also when its report turns out gone or private), **Then** its chunks are
   gone.
5. **Given** the existing SQLite test suite, **When** it runs with the new models, **Then** it
   stays green.

---

### User Story 2 - Stored Warcraft Logs data and published guides become searchable chunks (Priority: P1, sc-112)

When the app stores a Warcraft Logs response or publishes a class guide, it renders the data
as short readable chunks ("Report X, fight 32, Heroic Ula'tek, kill, 535 s. Damage done:
Vagxsu (Arms Warrior) 139.1M, …") with typed filter values taken from the data itself, and a
background worker gives each chunk a vector. No fetch and no chat turn ever waits for this.

**Why this priority**: it is what fills the knowledge base with the data the agent should
answer from instead of calling Warcraft Logs again.

**Independent Test**: feed fixture responses and a fixture guide through the chunkers and the
queue with a fake embedder; check the rendered text, the filter columns, the vectors, the call
counts, and that a failing embedder leaves keyword-searchable rows that are retried later.

**Acceptance Scenarios**:

1. **Given** a stored report summary, **When** it is indexed, **Then** each boss fight has one
   summary chunk with report code, fight id, encounter, difficulty, kill, duration, start time
   and the roster with classes.
2. **Given** a stored table for one fight, **When** it is indexed, **Then** there is one chunk
   for the fight and metric with the top entries (bounded), and one chunk per player when the
   table is large, each keeping the fetch, report code and fight id.
3. **Given** a published guide, **When** it is indexed, **Then** there is one chunk per markdown
   section with class, spec, role, content type and section title in the text; **When** the
   guide is republished with fewer sections, **Then** no stale section chunk remains.
4. **Given** the embedder works, **When** the worker runs, **Then** each chunk gets a unit-length
   768-dimension document vector, the model name and the time.
5. **Given** the embedder fails, **When** the worker runs, **Then** rows keep a NULL vector (still
   keyword-searchable), the failure never reaches a fetch or a turn, and the rows are retried
   later.
6. **Given** a chunk whose content did not change, **When** its source is indexed again, **Then**
   it is not embedded again.

---

### User Story 3 - Past conversations become searchable within their workspace (Priority: P2, sc-305)

After a chat turn finishes and is saved, the exchange (the user's message and the agent's
final answer, without tool payloads) is queued as one chat chunk in the workspace's chat
store, with the characters it mentions, and embedded in the background.

**Why this priority**: lets the agent recall what was said in earlier chats ("what did we say
about my Arms build?"), workspace members only.

**Independent Test**: run a chat turn over the test socket with a fake agent stream that
includes tool calls; check that one chunk with only the user text and the final answer lands
in the chat store and that the turn did not wait for embedding.

**Acceptance Scenarios**:

1. **Given** a finished turn, **When** it is saved, **Then** one chunk per exchange is queued with
   workspace, conversation, message number, time and mentioned characters; tool payloads and
   frames are not in its text.
2. **Given** a turn that fails or is interrupted, **When** it ends, **Then** no chat chunk is
   written for it.
3. **Given** a conversation with chunks, **When** it is deleted, **Then** its chunks are gone;
   another workspace never sees them.

---

### User Story 4 - Backfill what was stored before this feature (Priority: P3, sc-113)

The operator runs one command that first prints how many chunks of each kind it would write
and what embedding them would roughly cost, and only with an explicit confirm flag writes and
embeds them. It can be interrupted and rerun without paying twice.

**Why this priority**: new data embeds on its own; the backfill makes the existing store,
guides and chats searchable too. First to drop if the sprint runs late (drop order #3).

**Independent Test**: seed fetches, guides and conversations; run without the flag (counts,
cost, nothing written); run with it, interrupt midway, rerun; count embedder calls.

**Acceptance Scenarios**:

1. **Given** no confirm flag, **When** the command runs, **Then** it prints chunk counts per kind
   and an estimated cost and exits without writing or embedding.
2. **Given** the confirm flag, **When** the command runs, is interrupted and runs again, **Then**
   every chunk ends up embedded exactly once (unchanged chunks with a vector are skipped).

---

### Edge Cases

- A report turns gone or private while its fetch is queued for indexing: the chunk insert
  finds no fetch row and is dropped; no orphan chunk survives.
- A newer response for the same query replaces the stored row: its chunks are replaced (new
  keys inserted, missing keys deleted, unchanged keys keep their vector).
- An unchanged refetch (same body hash) is not re-chunked at all.
- A response shape the chunker doesn't recognise (events, graphs, rankings, character data,
  a hand-written query) produces no chunks; a fetch that names no report is never chunked
  (039 never serves it).
- A chunk's text changes while its vector is being computed: the stale vector is not written.
- The embedder is not configured: chunks are still written with NULL vectors; nothing fails.
- The indexing queue is full: the job is dropped and counted, never blocks the caller; the
  backfill or a later write of the same source recovers it.
- Very long text (a huge answer, a long guide section) is cut to a bounded size before
  embedding.
- A guide is held for review or fails: only publishing changes its chunks.
- A chat chunk insert without a workspace scope, or for a foreign conversation: refused by the
  database.
- Process shutdown with jobs queued: bounded drain, then the rest is dropped (recovered later
  by the retry sweep or the backfill).

## Requirements *(mandatory)*

### Functional Requirements

**Store (sc-111)**

- **FR-001**: The local stack and the developers' throwaway database recipe MUST use the
  vector-capable Postgres 17 image (`pgvector/pgvector:pg17`); an existing Postgres 17 volume
  MUST start under it unchanged.
- **FR-002**: Migration 0019 (after `0018_raw_store_visibility`) MUST enable the vector
  extension and require version 0.8 or newer, and create `kb_chunks` (global; kind `wcl` or
  `guide`) and `kb_chat_chunks` (workspace-scoped).
- **FR-003**: Every chunk MUST carry its text, a content hash, a nullable 768-dimension vector,
  the embedding model and time, a generated keyword index (no stemming for `wcl`, English for
  `guide` and chat), typed filter columns, a free-form `extra` field, a stable chunk key
  unique within its source, and a short human label.
- **FR-004**: `kb_chunks` MUST reference its stored fetch (`raw_fetch_id` = the fetch's
  `query_key`) or its guide (exactly one, by kind), and `kb_chat_chunks` its conversation
  within the same workspace (composite key with `tenant_id`), so deleting the source deletes
  the chunks and a chat chunk can never name another workspace's conversation.
- **FR-005**: `kb_chat_chunks` MUST be under the standard `tenant_isolation` row-level policy,
  enabled and forced, so the runtime role reads and writes only the scoped workspace's rows.
- **FR-006**: Indexes MUST cover approximate nearest-neighbour search by cosine distance, the
  keyword index, the selective filters, and `extra`.
- **FR-007**: The migration MUST upgrade, downgrade and upgrade cleanly on Postgres; SQLite
  tests MUST keep building the schema from the models.
- **FR-008**: The project MUST ship an embedder contract (`backend/app/kb/embedder.py`: an
  `Embedder` protocol, `get_embedder()` returning `None` when embeddings are unavailable, and
  a test injection point) with the sc-111 milestone, for feature 044.

**Indexing WCL and guides (sc-112)**

- **FR-009a**: Only fetches whose stored body changed and that name at least one exact report
  code are chunked, and only recognised shapes (report summary, `table` bodies); others yield
  no chunks.
- **FR-009**: The WCL chunker MUST render readable text, one chunk per fight summary, one per
  fight and metric with the top entries (bounded), and one per player per fight for large
  tables, each keeping fetch, report code and fight id.
- **FR-010**: WCL filter columns MUST come from the query variables and the response (report
  code, zone, encounter, difficulty, fight, kill, start time, players with class and spec,
  region, realm and guild where present), normalised through the shared name resolver, with
  no model call.
- **FR-011**: The guide chunker MUST write one chunk per markdown section of the published
  guide with class, spec, role, content type and section title in the text, and a
  republished guide MUST replace its chunks.
- **FR-012**: Embeddings MUST use Vertex `gemini-embedding-001` at 768 dimensions with the
  document task type, be L2-normalised, and record the model and time; the model name MUST
  be configurable.
- **FR-013**: Indexing and embedding MUST run only in a background queue: bounded, batched,
  retried with backoff through the shared rate-limit layer; no fetch or chat turn awaits it.
  Failed embeddings leave NULL vectors that a periodic sweep picks up (chat rows per
  workspace, under its scope). A vector is stored only while the row's content hash still
  matches the embedded text.
- **FR-014**: A chunk whose content hash is unchanged MUST NOT be embedded again.
- **FR-015**: No code in this feature MAY serve chunks to a user; the only chunk reads are the
  indexer's own bookkeeping.
- **FR-016**: CI MUST never call Vertex; the embedder is injectable and faked.

**Indexing conversations (sc-305)**

- **FR-017**: After a turn's final answer is saved, one exchange chunk (user message plus final
  answer, no tool payloads or frames) MUST be queued; failed or interrupted turns queue none.
- **FR-018**: Chat chunks MUST record workspace, conversation, the answer's message number, the
  time and the characters mentioned (resolved through the name resolver against the
  workspace's characters and known players).
- **FR-019**: Chat chunks MUST be written under the turn's workspace scope and embedded in the
  background queue.

**Backfill (sc-113)**

- **FR-020**: A `backend.cli` command MUST backfill stored fetches, published guides and
  conversations with the same chunkers.
- **FR-021**: Without a confirm flag it MUST print the chunk count per kind and an estimated
  cost and exit without writing or embedding.
- **FR-022**: It MUST be resumable and idempotent: a rerun skips sources already indexed and
  chunks whose content hash already has a vector. Stored tables whose metric can't be told
  from the body are skipped (no query text is stored).
- **FR-024**: The cost estimate is characters / 4 tokens × a configurable price per 1M tokens.
- **FR-023**: It MUST go through the shared rate-limit layer and MUST NOT run at startup.

### Key Entities

- **Knowledge chunk (global)**: one readable unit from a stored WCL fetch or a published guide;
  kind, source pointer (fetch or guide), chunk key, label, text, content hash, vector state,
  filters (report code, zone, encounter, difficulty, fight, kill, start time, players, region,
  realm, guild, class, spec, role, content type, patch, section), extra.
- **Chat chunk (per workspace)**: one finished exchange; workspace, conversation, message
  number, created time, mentioned characters, text, content hash, vector state, extra.
- **Embedder**: turns texts into unit-length 768-d vectors for a task type; unavailable means
  "keyword only for now".
- **Indexing job**: a source to (re)chunk: a stored fetch, a published guide, or an exchange.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A chat turn's completion time is unchanged by this feature (indexing work after
  the turn is saved only enqueues; tested by a turn completing while the embedder blocks).
- **SC-002**: 100% of cross-workspace read and insert attempts on chat chunks are refused by the
  database in the Postgres tests.
- **SC-003**: Deleting any source leaves zero chunks behind (tested per source kind).
- **SC-004**: Re-indexing an unchanged source costs zero embedding calls; a backfill rerun after
  an interruption embeds each chunk exactly once.
- **SC-005**: When the embedder is down, 100% of new chunks are still stored and keyword-
  searchable, and they get vectors once it recovers.
- **SC-006**: The backfill always shows its count and cost before spending anything.

## Assumptions

- The name resolver (044, sc-304) is merged before sc-112/sc-305 land; until then the chunkers
  call one normalisation seam that will delegate to it.
- The writer hook in `fetch_persistence.py` and the backfill iterator in `raw_fetches.py` are
  edited only after 045 part 1 (sc-295, sc-296) merges, per the board's hot-spot sequence.
- One app process runs the indexer (as with the 039 fetch writer); a second process would at
  worst embed a chunk twice, never write a stale vector.
- Vertex embedding pricing and the per-request batch limit are confirmed in the owner's live
  check; defaults are conservative and configurable.
