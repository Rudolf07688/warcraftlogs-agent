# Implementation Plan: Knowledge base store and embedding

**Branch**: `043-kb-store-embed` | **Date**: 2026-11-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/043-kb-store-embed/spec.md` (Gate 1 passed, #44).

## Summary

Add the write side of the semantic knowledge base: the pgvector image, migration 0019 with a
global `kb_chunks` table (WCL + guides) and an RLS-fenced `kb_chat_chunks` table, an embedder
contract for 044, chunkers that render stored WCL responses, published guides and finished chat
exchanges as short readable text with typed filters, a background indexer modelled on the 039
fetch writer that writes chunks and embeds them with Vertex `gemini-embedding-001` (768-d,
L2-normalised), and a resumable backfill CLI that prints counts and cost first. The tables are
the embed backlog (NULL vector = pending); sources' deletes cascade to their chunks.

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async (asyncpg / aiosqlite), Alembic,
google-genai 2.25 (embeddings, via `wcl_agent.llm.provider`), new: `pgvector` (SQLAlchemy type)

**Storage**: Postgres 17 + pgvector ≥ 0.8 (`pgvector/pgvector:pg17`); SQLite for unit tests

**Testing**: pytest (+ pytest-asyncio); Postgres-only tests on a throwaway container (port 15443)

**Target Platform**: Linux server (docker compose locally)

**Project Type**: web service (backend only; no UI in this feature)

**Performance Goals**: zero added latency on a chat turn or a WCL fetch (enqueue only, O(1));
indexing a 5 MB table body parses off the event loop

**Constraints**: no Vertex call in CI; chat chunks never cross workspaces (RLS + composite FK);
no read path serves chunks (044 owns search); `backend/app/kb` never names the 039-guarded
`raw_fetches` table

**Scale/Scope**: a few thousand stored fetches and chats per install; chunks per fetch bounded
(≤ 60 fights per summary, ≤ 1 + 40 chunks per table)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design: still PASS.*

| Principle | How this plan meets it | Status |
|---|---|---|
| I Reuse-first | Indexer copies the proven `FetchWriter` shape (bounded queue, throttled drops, bounded drain) rather than a new framework; embeddings reuse `provider.genai_client()` and the shared retry loop (`generation._with_retry`); names via 044's resolver (one seam, `kb/names.py`); `exact_report_codes`, `tenant_scope`, `_insert` (on-conflict helper), `guide_has_published`, `normalize_class_name` reused. One chunk writer (`kb/store.py`) used by the indexer and the backfill. | PASS |
| II Small verified steps | Four stories in order, each committed with its tests; sc-111 ships alone as a milestone (Stop 3). | PASS |
| III Simplicity | No jobs table, no Redis, no new service: the chunk table is the backlog; one consumer task does jobs and the sweep, so there is no concurrency between them. | PASS (one dependency: see Complexity Tracking) |
| IV Typed boundaries | `Embedder` Protocol, frozen dataclasses for jobs (`GuideJob`, `ExchangeJob`), chunk drafts (`ChunkDraft`, `ChatChunkDraft`), `FetchSource`, `PlayerRef`; CLI args via argparse into a dataclass. | PASS |
| V Async backend | All DB and Vertex calls async; large JSON parses via `asyncio.to_thread`; no blocking work on the request path (offers never await). | PASS |
| VI GitNexus | Impact run on every edited symbol (below); detect-changes before every commit. | PASS |
| VII shadcn | No frontend change. | N/A |
| VIII Backlog sync | Stories moved to In Progress; Under Review at hand-off; backlog items posted as `backlog:*` notices (no `todo.md` edits: not in the footprint). | PASS |

## GitNexus impact (risky symbols, worktree index at 26e8c7d)

| Symbol | Risk | Callers / processes | Mitigation |
|---|---|---|---|
| `fetch_persistence.store_batch` | UNKNOWN (no resolved callers) | text search: `FetchWriter.__init__` default `store=`, tests (`test_raw_store_pg.py`, writer tests) | Edit after Tomas's sc-295 rework (contract 5); add only the post-commit offer; writer tests stay green; offer is a no-op without an indexer. |
| `fetch_persistence._store_one` / `FetchWriter` | LOW (1 caller each) | writer internals, `main.lifespan` | Not changed beyond the hook. |
| `ws._handle_turn` | LOW (2: `_start_turn`, `chat`; process `chat`) | the chat socket | One `offer_exchange` call after the final save transaction; ws tests (`test_proposal_ws`, `test_ws_rate_limit`, `test_model_fallback_ws`) + new `test_kb_chat.py` prove no change on partial/error paths and no wait. |
| `guide_pipeline._run` | LOW (3; process `run` in the guides eval) | `run_guide_generation` ← `guide._run_guide` | One `offer_guide` after the publish commit; `test_guide_pipeline_run.py` stays green. `publish_spec_guide` itself (HIGH, 3) is **not** edited. |
| `main.lifespan` | UNKNOWN (framework-invoked) | text search: `FastAPI(lifespan=lifespan)` only | Start/stop next to the fetch writer, guarded by `kb_index_enabled`; stop before `engine.dispose()`. |
| `models.Conversation` | **HIGH** (52, dispatch boundary) | every conversation query | Only adds `UniqueConstraint("id", "tenant_id")` to `__table_args__`; no column, relationship or behaviour change. Full SQLite suite + Postgres migration round trip prove it. Posted as a board notice. |

## Project Structure

### Documentation (this feature)

```text
specs/043-kb-store-embed/
├── spec.md  research.md  data-model.md  quickstart.md  plan.md  tasks.md  checkpoint.md
├── checklists/requirements.md
└── contracts/  embedder.md  indexer.md  backfill-cli.md
```

### Exact file list per story (Gate 2 grant request)

**sc-111 (milestone, Stop 3)** — all already granted (#17):

- `docker-compose.yml` (image)
- `pyproject.toml`, `uv.lock` (`pgvector`)
- `backend/migrations/versions/0019_kb_chunks.py` (new)
- `backend/app/db/models.py` (`KbChunk`, `KbChatChunk`, tsvector expression helper,
  `Conversation` unique constraint)
- `backend/app/kb/__init__.py`, `backend/app/kb/embedder.py` (new; contract 2)
- `backend/tests/test_kb_store.py` (SQLite: schema builds, constraints, model round trip),
  `backend/tests/test_kb_embed.py` (embedder contract: normalise, injection, `get_embedder` None), `backend/tests/test_kb_store_pg.py` (new; Postgres:
  extension ≥ 0.8, columns/indexes, HNSW + tsv work, cascades, chat RLS read/insert/foreign
  conversation/no scope)
- `specs/043-kb-store-embed/**`

**sc-112**:

- new, granted: `backend/app/kb/chunks.py` (drafts, hashing, bounds, number format),
  `backend/app/kb/names.py` (resolver seam), `backend/app/kb/wcl_chunker.py`,
  `backend/app/kb/guide_chunker.py`, `backend/app/kb/store.py` (chunk writes, pending rows,
  conditional vector update), `backend/app/kb/indexer.py` (queue, consumer, sweep, offers)
- tests, granted: `backend/tests/test_kb_chunk_wcl.py`, `backend/tests/test_kb_chunk_guide.py`,
  `backend/tests/test_kb_embed.py`, `backend/tests/test_kb_store.py`,
  `backend/tests/test_kb_store_pg.py` (fetch delete / report gone cascade through the writer)
- **sequenced (after 045 part 1)**: `backend/app/config.py` (KB settings),
  `backend/app/services/fetch_persistence.py` (post-commit `offer_fetch` from
  `BatchResult.changed`)
- **grant requested**: `backend/app/services/guide_pipeline/__init__.py` (`offer_guide` in `_run`
  after the publish commit), `backend/app/main.py` (indexer start/stop in `lifespan`)
- **grant requested (docs)**: `.env.example` (KB settings block), `README.md` (KB paragraph next to
  the raw store's), `documentation/ai_guide.md` (KB paragraph next to the raw store's)

**sc-305**:

- new, granted: `backend/app/kb/chat_chunker.py`
- **grant requested**: `backend/app/api/ws.py` (`offer_exchange` after the final save)
- tests, granted: `backend/tests/test_kb_chat.py` (turn → one chunk, tool payload excluded,
  partial/error/rate-limited → none, turn does not wait for a blocked embedder),
  `backend/tests/test_kb_chat_pg.py` (Postgres: cascade on conversation delete, other
  workspace sees none, mentions resolved under the scope)

**sc-113**:

- granted: `backend/cli/kb_backfill.py` (new), `backend/tests/test_kb_backfill.py`
- **sequenced**: `backend/app/repositories/raw_fetches.py` (`list_fetch_keys`,
  `load_fetch_for_index`; released straight after the commit)

- **grant requested (found at sc-111)**: `wcl_agent/llm/generation.py` (`embed_texts`,
  `embeddings_available`: only the provider layer may call model clients, `test_provider_e2e`)

Not touched: `backend/app/repositories/raw_fetches.py`
upsert (Tomas, contract 5), `backend/app/db/repository.py`, `conftest.py`, `kb/search.py`.

**Structure Decision**: a new backend package `backend/app/kb/` holds everything KB-specific
except the hooks (one line each in their owners' files), the models (with the other models)
and the migration. 044 adds `kb/search.py` to the same package.

## Implementation order (inside the sequencing)

1. sc-111: dependency + image → models (SQLite green) → migration on the container (up/down/up,
   extension check) → embedder contract → Postgres tests → commit → **Stop 3** hand-off.
2. sc-112, own files first (no waiting): `chunks.py`, `names.py` seam, `wcl_chunker.py`,
   `guide_chunker.py`, `store.py`, `indexer.py` (embed pass + sweep) with tests; settings read
   through one `kb_settings()` accessor so the `config.py` edit is one place.
3. sc-305 own files: `chat_chunker.py` + indexer exchange path, tests on SQLite.
4. When 045 part 1 merges: rebase; `config.py` + `fetch_persistence.py` hook; commit. When 044
   sc-304 merges: rebase; `names.py` delegates to `name_resolver.py`.
5. With the Gate-2 grants: `guide_pipeline` hook, `main.py` lifespan, `ws.py` hook; Postgres chat
   tests; commit per story.
6. sc-113: `raw_fetches.py` iterator first → commit → post `released`; then the CLI and tests.
7. Own bypass review (memory: before the last story), docs, detect-changes, hand-off.

## Risks

| Risk | Mitigation |
|---|---|
| A chunk outlives a source that became invisible but wasn't deleted (grant expired) | Not this feature's read path: 044 joins `fetch_visible_clause` on every query (contract 3); 043 serves nothing. |
| Composite FK bypass via FK check ignoring RLS | `UNIQUE(id, tenant_id)` + composite FK; Postgres test inserts a B-scoped chunk naming A's conversation and expects a refusal. |
| Indexer writes chat rows without a scope | Every chat write runs inside `tenant_scope(job.tenant_id)`; Postgres test proves an unscoped insert is refused. |
| Stale vector on a changed chunk | Conditional `UPDATE … WHERE content_hash = :hash`; unit test changes text mid-embed. |
| Vertex batch limit / price unknown in CI | Defaults conservative (1 text per request, 0.15 USD/1M); `live-check:043` question with exact steps. |
| Embedding cost runaway | Only changed fetches with report codes; unchanged hashes never re-embedded; backfill estimate first; sweep stops on the first failure. |
| Hot-spot files shared with 045 | Edits only inside the SM's windows; `raw_fetches.py` released right after the iterator commit. |
| `Conversation` (HIGH) | Constraint-only change, full suite + migration round trip. |

## Complexity Tracking

| Addition | Why needed | Simpler alternative rejected because |
|---|---|---|
| `pgvector` Python package | The `vector(768)` column type for SQLAlchemy (AC sc-111.7) | Raw SQL casts everywhere would leak into 044's queries and the models couldn't describe the column. |
