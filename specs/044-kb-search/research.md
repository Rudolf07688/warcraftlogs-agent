# Research: Knowledge base search (044)

Each entry: decision, rationale, alternatives considered. Clarify decisions are on the board
(`clarify:044-*`, #25–#29) and the Gate 1 review is #37.

## R1. Where the resolver gets its names (sc-304)

- **Decision**: classes and specs come from `roster_snapshot()` (the live roster, with
  `CLASS_SPECS` as its offline fallback) through `normalize_class_name`, `resolve_spec` and
  `role_for_spec`. Encounters come from `wcl_agent.menu.load_world_zones()` (the cached zone
  list `patch.py` and `find_encounter` read) plus the workspace's `known_encounters`.
  Characters come from the workspace's `user_characters` and `known_players`. Difficulty names
  reuse `wcl_agent.tools.tools._DIFFICULTY_NAMES` (1/3/4/5) and
  `patch.MYTHIC_PLUS_DIFFICULTY_ID` (10).
- **Rationale**: constitution I (one class/spec map) and AC1. The only new data is a small alias
  table (abbreviations to canonical names), validated against the roster at lookup time, so a
  roster change can never be contradicted by it.
- **Alternatives**: a fresh class/spec table in the resolver (rejected: a second map); calling
  `find_encounter` (rejected: it returns a tool envelope, does substring matching only and is
  not accent-insensitive). Two difficulty-name copies already exist (`tools.py`,
  `profile_context.py`); importing the first avoids a third. Merging the two is posted as
  `backlog:difficulty-names` (out of scope).

## R2. The name key

- **Decision**: `name_key(s) = NFKD(s)` with combining marks removed, casefolded, keeping only
  letters and digits (so "Ula'tek", "ulatek", "Ula-tek", "Úlatek" are one key). Ansel's writers
  store `players[].key` / `characters[].key` with it (#36); search matches with it.
- **Rationale**: one definition on both sides of the jsonb containment match.
- **Alternatives**: `roster._loose` (drops only spaces, apostrophes, hyphens; not accents) is
  kept for `resolve_spec`, which the resolver calls with already-keyed text.

## R3. Matching strategy

- **Decision**: exact key match first; then a unique prefix/substring match on the key; several
  distinct targets → `ambiguous`; none → `unknown` with `difflib.get_close_matches` (cutoff 0.6,
  up to 5). Class+spec phrases ("arms warr", "bm hunter", "warrior arms") are matched by
  checking whether the key equals class-form + spec-form or spec-form + class-form for any
  roster entry, where forms are the filter value, the display name and the aliases.
- **Rationale**: deterministic, no tokenisation rules to maintain, handles multi-word classes
  and specs ("beast mastery", "demon hunter").
- **Alternatives**: token-by-token parsing (fragile with multi-word names); fuzzy matching on
  every lookup (silently picks wrong targets; AC3 wants an error instead).

## R4. Search SQL shape (sc-114)

- **Decision**: per query and pass, one statement: a `UNION ALL` of branches, each with its own
  `ORDER BY … LIMIT 40` so the HNSW and GIN indexes are used:
  vector leg: `kb_chunks` (embedding NOT NULL, `<=>` cosine distance) and `kb_chat_chunks`;
  keyword leg: `kb_chunks` kind `wcl` with `simple` tsquery, kind `guide` with `english`
  tsquery, `kb_chat_chunks` with `english`; each ordered by `ts_rank_cd`. Each row is tagged
  with its leg; ranks and RRF are computed in Python.
- **Keyword query**: the query's lexemes OR-ed:
  `replace(plainto_tsquery(cfg, :q)::text, ' & ', ' | ')::tsquery` (plainto sanitises the
  input; natural-language questions rarely match every word, so AND starves the keyword leg).
- **Filtered vector search**: `SET LOCAL hnsw.iterative_scan = relaxed_order` per search
  transaction (pgvector ≥ 0.8, checked by 043's migration).
- **Rationale**: per-branch limits keep index use; Python fusion is simple and unit-testable on
  SQLite with the SQL layer faked.
- **Alternatives**: RRF inside SQL with window functions (harder to test, no gain at N=40);
  one leg per statement (twice the round trips); `websearch_to_tsquery` (AND semantics).

## R5. Visibility inside the SQL

- **Decision**: `kb_chunks` rows of kind `wcl` pass only `fetch_visible_clause(kb_chunks.raw_fetch_id,
  tenant_id=…, since=now - RAW_STORE_REVERIFY_DAYS)` (045's contract 3, the 039 rule's one
  definition; `raw_fetch_id` is `raw_fetches.query_key`, #31). Guide rows pass. Chat rows pass
  `kb_chat_chunks.tenant_id = :tenant` and run in a session scoped by `set_scope` (RLS). The
  search code never names the raw fetch model or table (039 guard test). No freshness (#28).
- **Rationale**: the AC and P7: a filter is ANDed onto a visibility predicate, so no filter
  combination can widen the scope; RLS plus the explicit predicate is defence in depth.
- **Alternatives**: post-filtering hits in Python through `read_visible_fetch` (N extra round
  trips and a hit count that drops after ranking).

## R6. Concurrency, timeouts and failure

- **Decision**: all queries of a call are embedded in one `Embedder.embed(…, task="RETRIEVAL_QUERY")`
  call (timeout 3 s; failure or `get_embedder()` None → keyword-only + note). Each query then
  runs in its own session (`asyncio.gather`; an `AsyncSession` is not concurrency-safe), at most
  5 at once. Relaxation passes run one after another. The whole search is bounded by 8 s; on
  timeout or a database error the tool returns a plain error and the turn goes on. On a
  non-Postgres database the search reports "unavailable".
- **Rationale**: AC1 (concurrent queries), FR-018/FR-019; one embed call is cheaper than five.
- **Alternatives**: one session for all queries (serialises them, violating AC1).

## R7. Tool schema enums

- **Decision**: `Literal[...]` aliases built from the single sources at import time:
  class = `tuple(CLASS_SPECS)`, spec = the sorted union of their specs, difficulty = the names in
  `_DIFFICULTY_NAMES` plus "Mythic+", kind = `wcl|guide|chat`, `user_stated` = a list of filter
  names. A probe confirmed ADK 1.x renders `Literal` and `list[Literal]` as JSON-schema `enum`.
- **Rationale**: AC1 (enums), constitution I (no copied lists).
- **Alternatives**: free strings validated by the resolver only (the model invents values).

## R8. Ranking details

- **Decision** (#25): N = 40 per leg; per query `score = Σ_legs 1/(60 + rank)`; across queries
  RRF over each query's fused rank, a chunk's contributions summed; dedupe by source (wcl:
  report code + fight + label; guide: guide id + section label; chat: conversation + seq),
  keeping the best. Relaxed passes (#26) are appended below stricter hits. Ties break on chunk
  id for determinism.

## R9. Eval embeddings (sc-115, Gate 1 change 1)

- **Decision**: `backend/evals/kb/embeddings.json` holds recorded vectors with a `set` field
  (`"stand-in"` or `"vertex:<model>"`). Without a recorded file the harness computes a
  deterministic stand-in (hashed character trigrams into 768 dimensions, unit-normalised) and
  only reports recall. `python -m backend.evals.kb record` embeds the corpus (as
  `RETRIEVAL_DOCUMENT`) and questions (as `RETRIEVAL_QUERY`) with the real embedder, capped at
  300 texts, and writes the file; the "hybrid not worse" assertion runs only when `set` starts
  with `vertex:`.
- **Rationale**: a stand-in proves the harness, not the model (#37).
- **Alternatives**: committing random vectors (meaningless numbers).

## R10. Eval runtime

- **Decision**: the harness loads the fixture corpus into a Postgres database through the
  public repository functions (`upsert_raw_fetch`, `record_report_status`, `grant_codes` for
  WCL rows; direct inserts into `spec_guides`, `conversations` and the chunk tables), runs the
  real search per mode (`hybrid`, `vector`, `keyword`) and reports recall@k and p50/p95
  latency. The CI test runs it against `TEST_DATABASE_URL` (skipped on SQLite); the metric
  functions and fixture integrity run in the SQLite suite.
- **Rationale**: measures the real SQL, not a Python imitation of `ts_rank_cd`.
- **Alternatives**: an in-Python BM25/cosine simulation (would not measure what ships).

## R11. Live mode (drop order 1)

- **Decision**: `python -m backend.evals.kb live --max-questions N` runs each labelled question
  as one agent turn on the cheapest chat model (`role_model(ModelRole.FAST)`, overridable with `--model`), once with the
  rendered instruction and once with the search-first clause removed, over the loaded fixture
  corpus. It reports filter-extraction accuracy (the first `search_knowledge` call's arguments
  vs the labels) and the local-answer rate (turns with no Warcraft Logs tool call). Capped at
  30 questions × 2 variants. Team-lead runs it; CI never does.

## R12. BM25 options (for the write-up)

- ParadeDB `pg_search`: AGPL-3.0. VectorChord-bm25: AGPL-3.0 / ELv2 dual. Timescale
  `pg_textsearch`: PostgreSQL licence (all three to be re-checked before adopting). Each needs a different image or extension build. The
  write-up recommends staying on `ts_rank_cd` unless the recorded eval shows keyword ranking is
  the weak leg; `pg_textsearch` is the first candidate if it is (licence fits).
