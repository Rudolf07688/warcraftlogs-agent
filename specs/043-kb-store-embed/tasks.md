# Tasks: Knowledge base store and embedding (043)

**Input**: plan.md, spec.md, research.md, data-model.md, contracts/ in `specs/043-kb-store-embed/`.
Tests are required by the ACs (each AC names a test), so each story carries its tests.
US1 = sc-111, US2 = sc-112, US3 = sc-305, US4 = sc-113. Commit per story.

## Phase 1: Setup

- [ ] T001 Add the `pgvector` dependency with `uv add pgvector` (updates `pyproject.toml`, `uv.lock`); run the SQLite suite once for the "before" count
- [ ] T002 Switch the `db` service image to `pgvector/pgvector:pg17` in `docker-compose.yml`

## Phase 2: Foundational

(None beyond US1: US1 is the foundation every other story writes to.)

## Phase 3: User Story 1 - Vector store setup (sc-111, P1, milestone) 🎯

**Goal**: pgvector image, migration 0019 with `kb_chunks` + `kb_chat_chunks`, models, embedder contract.
**Independent test**: SQLite schema builds; on the container, 0019 up/down/up, RLS and cascades hold as the runtime role.

- [ ] T003 [US1] Add `KbChunk`, `KbChatChunk` (columns, CHECK, unique keys, indexes per data-model.md), the tsvector `@compiles` expression (Postgres `to_tsvector`, SQLite `NULL`) and `UniqueConstraint("id", "tenant_id", name="uq_conversations_id_tenant")` on `Conversation` in `backend/app/db/models.py`
- [ ] T004 [US1] Write migration `backend/migrations/versions/0019_kb_chunks.py` (`down_revision = "0018_raw_store_visibility"`): extension + version check ≥ 0.8, conversations unique, both tables, indexes (HNSW cosine, GIN tsv/extra/players/characters, B-trees), RLS enable+force+`tenant_isolation` on `kb_chat_chunks`, grants; downgrade in reverse; Postgres only
- [ ] T005 [P] [US1] Create `backend/app/kb/__init__.py` and `backend/app/kb/embedder.py` per contracts/embedder.md (`EmbedTask`, `DIMENSIONS`, `Embedder`, `normalise`, `VertexEmbedder` over `provider.genai_client()` + `generation._with_retry`, `get_embedder`, `set_embedder`)
- [ ] T006 [P] [US1] SQLite tests in `backend/tests/test_kb_store.py`: schema builds, a wcl and a guide chunk round-trip (vector value too), the kind/source CHECK and unique `(raw_fetch_id, chunk_key)` refuse bad rows
- [ ] T007 [P] [US1] Embedder tests in `backend/tests/test_kb_embed.py`: unit norm, injection and clearing, `get_embedder()` is None without a client, `VertexEmbedder` with a fake genai client (task type, 768 dims, per-request batching, a wrong dimension raises, a 429 is retried through the shared loop)
- [ ] T008 [US1] Postgres tests in `backend/tests/test_kb_store_pg.py` (skipped without `TEST_DATABASE_URL`): extension ≥ 0.8; tsv config per kind; an HNSW-ordered query runs; deleting a raw fetch, a guide and a conversation deletes their chunks; workspace B reads none of A's chat chunks, can't insert one with A's tenant id, can't insert one naming A's conversation under its own tenant id, and an unscoped insert is refused
- [ ] T009 [US1] On `wcl-043-pg` (port 15443): `init_db`, run T008 + `test_rls.py` + `test_raw_store_pg.py`, 0019 down/up/down/up; old-volume copy proof (quickstart §3); record results in `specs/043-kb-store-embed/quickstart.md`; stop the container
- [ ] T010 [US1] Detect-changes, ownership check, commit; post `skill:` notice for the image change; **Stop 3** hand-off for the milestone

## Phase 4: User Story 2 - Embed WCL fetches and guides on write (sc-112, P1)

**Goal**: chunkers, metadata, background indexer with embed + sweep; hooks.
**Independent test**: fixtures through chunkers and indexer with a fake embedder.

Own files first (no waiting):

- [ ] T011 [P] [US2] `backend/app/kb/chunks.py`: `ChunkDraft`, `ChatChunkDraft`, `PlayerRef`, `content_hash`, `bounded(text, n)`, `humanise(number)` (139.1M), max sizes
- [ ] T012 [P] [US2] `backend/app/kb/names.py` seam: `name_key`, `class_spec(class, spec)`, `role_for`, `difficulty_name`, `mentioned_characters(session, text)` (stubbed to constants/casefold until sc-304)
- [ ] T013 [US2] `backend/app/kb/wcl_chunker.py`: `FetchSource` (from a `FetchedResponse` or a stored row), `chunk_fetch(source) -> list[ChunkDraft]` for report summaries (single + batch) and tables (metric from the query or inferred from the body; top-10 table chunk; per-player chunks over 10 entries, bounded 40; source-filtered player chunk), filters from variables + body
- [ ] T014 [P] [US2] `backend/app/kb/guide_chunker.py`: `chunk_guide(job) -> list[ChunkDraft]`, one chunk per markdown section (heading-delimited; preamble as its own section), class/spec/role/content type/section title in the text
- [ ] T015 [US2] `backend/app/kb/store.py`: `replace_source_chunks(session, *, raw_fetch_id | guide_id, drafts)` (insert new keys, update changed text with embedding reset, delete missing keys), `fight_context(session, report_code, fight_id)`, `pending_rows(session, table, ids|limit)`, `store_vectors(session, table, rows, vectors, model)` (conditional on content_hash), `upsert_chat_chunk(session, draft)`
- [ ] T016 [US2] `backend/app/kb/indexer.py`: `KbIndexer` (bounded queue, `start/stop`, consumer, per-job transaction, embed pass with pause-on-failure, sweep on idle timeout), `GuideJob`, module offers `offer_fetch` / `offer_guide` (no-op without an indexer), throttled drop warning; settings via one `kb_settings()` accessor
- [ ] T017 [P] [US2] `backend/tests/test_kb_chunk_wcl.py`: design-format summary text + filters, batch summary, table top-N + per-player chunks + bounds, source-filtered table, fight context copied, unknown shapes / no report code → none, backfill inference (Summary/Deaths/Auras yes, plain entries no)
- [ ] T018 [P] [US2] `backend/tests/test_kb_chunk_guide.py`: one chunk per section with the labels in the text; republish with fewer sections leaves no stale chunk (through `replace_source_chunks`)
- [ ] T019 [US2] Extend `backend/tests/test_kb_embed.py`: indexer embeds pending rows (unit norm stored, model + time); unchanged hash → zero embed calls on re-index; failing embedder → NULL rows, no exception to the offerer, sweep embeds them later; changed text mid-embed → stale vector not stored; full queue drops and counts; `offer_*` without an indexer is a no-op; CI never builds a Vertex client (fake injected)
- [ ] T020 [US2] (after 045 part 1 merges: rebase) KB settings in `backend/app/config.py` (`kb_index_enabled`, `kb_embed_enabled`, `kb_embed_model`, `kb_index_queue_max`, `kb_embed_batch`, `kb_embed_request_batch`, `kb_embed_sweep_s`, `kb_embed_price_per_mtok`); point `kb_settings()` at them
- [ ] T021 [US2] (after 045 part 1) post-commit `offer_fetch` for each `BatchResult.changed` item in `backend/app/services/fetch_persistence.py`; writer test for the offer in `backend/tests/test_kb_embed.py`; Postgres cascade-through-writer test (fetch deleted by ReportGone / private summary loses its chunks) in `backend/tests/test_kb_store_pg.py`
- [ ] T022 [US2] (Gate-2 grant) `offer_guide(GuideJob(...))` after the publish commit in `_run` of `backend/app/services/guide_pipeline/__init__.py`; test that a published run offers and a held run doesn't in `backend/tests/test_kb_chunk_guide.py`
- [ ] T023 [US2] (Gate-2 grant) start/stop the indexer in `lifespan` of `backend/app/main.py` (guarded by `kb_index_enabled`, stop before `engine.dispose()`)
- [ ] T024 [US2] (after 044 sc-304 merges: rebase) `backend/app/kb/names.py` delegates to `backend/app/services/name_resolver.py`; chunker tests still green
- [ ] T025 [US2] Full suite + Postgres tests; detect-changes; commit sc-112

## Phase 5: User Story 3 - Embed past conversations (sc-305, P2)

**Goal**: one chat chunk per completed exchange, per workspace, embedded in the background.
**Independent test**: a socket turn with a fake stream (tokens + tool calls) writes exactly one chunk.

- [ ] T026 [P] [US3] `backend/app/kb/chat_chunker.py`: `chunk_exchange(job, characters) -> ChatChunkDraft` (`Question:/Answer:` text bounded 6,000, label, hash)
- [ ] T027 [US3] Indexer exchange path in `backend/app/kb/indexer.py`: `ExchangeJob`, `offer_exchange`, write under `tenant_scope(job.tenant_id)` with `mentioned_characters`, chat sweep per tenant under its scope
- [ ] T028 [US3] (Gate-2 grant) `offer_exchange(...)` after the final save in `_handle_turn` of `backend/app/api/ws.py` (completed turns with streamed text only)
- [ ] T029 [P] [US3] `backend/tests/test_kb_chat.py`: turn → one chunk with question + final answer, tool payload text absent; partial / agent error / rate-limited turn → none; the `DoneFrame` arrives while the embedder is blocked; unchanged exchange not re-embedded; mentions found
- [ ] T030 [US3] `backend/tests/test_kb_chat_pg.py`: conversation delete cascades; workspace B never sees A's chunks; indexer writes under the scope and mentions read the workspace's characters only
- [ ] T031 [US3] Suites + container run; detect-changes; commit sc-305

## Phase 6: User Story 4 - Backfill (sc-113, P3)

**Goal**: one CLI: dry run with counts + cost, confirmed run resumable and idempotent.
**Independent test**: seeded store; dry run writes nothing; interrupted confirmed run + rerun embeds each chunk once.

- [ ] T032 [US4] (after 045 part 1) `list_fetch_keys(session, *, after, limit, summaries)` and `load_fetch_for_index(session, key)` in `backend/app/repositories/raw_fetches.py`; commit; post `released` for `raw_fetches.py`
- [ ] T033 [US4] `backend/cli/kb_backfill.py` per contracts/backfill-cli.md (argparse → dataclass, kinds, dry-run estimate, confirmed write + embed via `kb/store.py` + the indexer's embed pass, per-tenant chat under `tenant_scope`, `--limit`)
- [ ] T034 [US4] `backend/tests/test_kb_backfill.py`: dry run prints counts + cost and writes nothing, calls no embedder; confirmed run indexes all three kinds; interruption (embedder raises after N) then rerun embeds each chunk exactly once (call count); already-indexed sources skipped; ambiguous stored table skipped
- [ ] T035 [US4] Suites; detect-changes; commit sc-113

## Phase 7: Polish

- [ ] T036 Own bypass review (before T033 ideally): chat read/insert from another workspace, deleted conversation, deleted / report-gone fetch, unscoped insert, filter text never trusted; fix findings
- [ ] T037 [P] (grant) KB settings block in `.env.example`; KB paragraphs in `README.md` and `documentation/ai_guide.md`
- [ ] T038 `live-check:043` board question with exact steps; backlog notices; Shortcut stories → Under Review; final hand-off

## Dependencies

- US1 blocks everything (schema + embedder). US2's own files (T011–T019) need only US1.
- T020/T021/T032 wait for the 045 part 1 merge; T024 waits for 044 sc-304; T022/T023/T028 wait for the Gate-2 grants.
- US3 needs the indexer (T016) and `names.py` (T012); US4 needs US2 + US3 chunkers and T032.

## Parallel examples

- US1: T005 + T006 + T007 after T003.
- US2: T011, T012, T014 together; then T013 / T015; tests T017 + T018 in parallel.
- US3: T026 + T029 drafting in parallel with T027.

## Implementation strategy

MVP = US1 (the milestone 044 waits on), handed off at Stop 3. Then US2 → US3 → US4, each
committed on its own; US4 is drop-order #3 if the sprint runs late.
