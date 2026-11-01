# Feature Specification: Knowledge base search (epic 100)

**Feature Branch**: `044-kb-search`

**Created**: 2026-11-01

**Status**: Draft

**Input**: Brief `sprints/2026-11-01/briefs/044-kb-search.md` (sprint worktree): sc-304 (shared
name resolver), sc-114 (parallel hybrid search tool), sc-115 (search-first prompting + eval).
Design: `documentation/designs/20261101_semantic_knowledge_base.md` (agreed with the owner).
Contracts: `sprints/2026-11-01/briefs/common.md` (board `contract:kb`, #15).

## Clarifications

### Session 2026-11-01

Self-answered (developer autonomy); each is a board decision `clarify:044-<topic>`.

- Q: Ranking: how many candidates per leg, what k, how are queries fused and what is "a
  source"? → A: N = 40 per leg (vector, keyword); k default 8, range 1–15. Per query: RRF
  `1/(60+rank)` summed over the two legs. Across queries: RRF again over each query's fused
  rank (rank-based, so phrasings with different score scales weigh equally). A source is
  wcl: report code + fight + chunk label; guide: guide + section; chat: conversation + message
  seq. Duplicates of a source collapse to the best-scoring chunk; a chunk matching several
  phrasings sums their contributions (`clarify:044-ranking`).
- Q: How does the server know a filter was stated by the user, and which filters relax? → A:
  the agent lists them in `user_stated` (an enum list of filter names); default empty. Only
  spec, class, encounter and dates (together) relax, in that order and cumulatively;
  `difficulty` and `character` never relax (mixing difficulties or people misleads more than
  a short list). Hits from a relaxed pass rank below every hit of a stricter pass
  (`clarify:044-relaxation`).
- Q: What is the output cap? → A: each hit's text is cut to 400 characters (at a word
  boundary, with an ellipsis); the whole serialised result is at most 6,000 characters (about
  1.5k tokens, so 15 hits never approach sc-302's bloat). Over the cap, the lowest-ranked hits
  are dropped and `capped` is true (`clarify:044-cap`).
- Q: Does search apply 039's freshness rule, and who may search? → A: visibility yes,
  freshness no (freshness decides when a stored body replaces a WCL call; a hit is context and
  its text carries its own dates). The tool runs only inside an authenticated chat turn whose
  workspace matches the ADK session user; otherwise it fails closed (`clarify:044-scope`).
- Q: How does a filter treat kinds that do not carry it, and what if a character is unknown?
  → A: a filter narrows only the kinds that carry the attribute (table below); `kind` is the
  way to exclude kinds. An unknown character is a correctable error with close matches; the
  error text tells the agent it may drop the filter and put the name in a query instead
  (keyword search keeps names intact) (`clarify:044-applicability`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The app understands the names players use (Priority: P1, sc-304)

Players write "arms warr", "resto", "Ula'tek", "ulatek", "hc" or a friend's name in any casing.
Every part of the app that turns such words into filters (the chunk writers of feature 043, the
knowledge search, the exact stored-data lookups of feature 045) resolves them the same way, to
the same canonical class, spec (with its role), encounter id, difficulty id or character. A
value it cannot resolve, or one that fits several things, comes back as a clear, correctable
error naming the close matches, never as a silent empty result.

**Why this priority**: it is the shared seam that 043 and 045 build on (milestone merge first),
and a filter that resolves differently on the write and the read side silently loses results.

**Independent Test**: call the resolver with the abbreviations, accented and apostrophe forms,
unknown and ambiguous values, and check the canonical values and the typed errors.

**Acceptance Scenarios**:

1. **Given** the class/spec roster, **When** `warr, dh, dk, ret, prot, resto, disc, bm, mm, sv`
   are resolved (each in its own test), **Then** each gives its canonical class or spec value.
2. **Given** the zone list contains Ula'tek, **When** "Ula'tek", "ulatek" and "ULATEK" are
   resolved, **Then** all give the same encounter id.
3. **Given** "arms warr", **When** resolved as a class+spec phrase, **Then** the result is
   Warrior / Arms with role dps.
4. **Given** "prot" with no class, **When** resolved, **Then** the result is an ambiguous error
   listing Paladin / Protection and Warrior / Protection.
5. **Given** "Ulatk" (a typo), **When** resolved as an encounter, **Then** the result is an
   unknown error whose close matches include Ula'tek.
6. **Given** a character name the workspace has as an own character, a friend or a known
   player, **When** resolved, **Then** the result carries name, realm, region and (when known)
   class and spec; another workspace's characters are never used.

---

### User Story 2 - The agent finds what the app already knows (Priority: P1, sc-114)

A user asks a question the app could answer from data it already holds: a fight discussed last
week, a class guide, an earlier chat in the same workspace. The agent calls `search_knowledge`
with one to five phrasings and the filters it can infer, the searches run in parallel, and it
gets back a short, ranked list of hits it is allowed to show: the WCL data only when the
workspace may see that report today, the workspace's own chats only, and the global guides.

**Why this priority**: this is the sprint goal (epic 100) and the security-core story (P7).

**Independent Test**: insert chunks of all three kinds directly (no embedding pipeline needed),
call the tool with a fake query embedder, and check ranking, filters, relaxation, the cap and
every visibility rule; visibility is proved on Postgres.

**Acceptance Scenarios**:

1. **Given** chunks of all three kinds, **When** the agent searches with two phrasings,
   **Then** both run concurrently, the hits are fused into one ranked list, and a source that
   matched both phrasings appears once.
2. **Given** a WCL chunk whose fetch is no longer visible to the workspace (grant expired,
   report turned private, row gone), **When** any search runs, **Then** that chunk never
   returns.
3. **Given** a chat chunk from another workspace, or from a deleted conversation, **When** any
   search with any filter runs, **Then** it never returns.
4. **Given** `class="Warrior"` and `spec="Holy"`, **When** searched, **Then** the agent gets a
   correctable error (Holy is not a Warrior spec), not an empty list.
5. **Given** soft filters (spec, class, encounter, dates) that leave fewer than k hits,
   **When** searched, **Then** the server drops them one at a time in that order until k hits
   are found or none are left, and the result names the dropped filters.
6. **Given** a hard filter (`kind`, `report_code`, or a filter the agent marks as stated by the
   user) that leaves fewer than k hits, **When** searched, **Then** that filter is never
   dropped.
7. **Given** long chunks and k at its maximum, **When** searched, **Then** each hit's text is
   truncated and the whole result stays under the output cap.
8. **Given** the query embedder is unavailable or fails, **When** searched, **Then** the search
   runs keyword-only and the result says so; chunks with no embedding yet are still found by
   keyword.

---

### User Story 3 - The agent looks locally first, and we can measure it (Priority: P2, sc-115)

The agent's instruction tells it to try `search_knowledge` or an exact stored-data lookup
before a Warcraft Logs fetch when the question could be answered from stored data. A small
labelled eval over a fixture corpus tells us whether hybrid search beats vector-only search and
how fast it is, in CI, without calling Vertex. A live mode, run by team-lead at sprint end,
measures filter-extraction accuracy and the local-answer rate with and without the search-first
instruction. A short write-up recommends the embedding model and whether true BM25 is worth it.

**Why this priority**: it turns the tool into fewer WCL calls (epic 103 goal) and gives the
evidence for the model and BM25 decisions; its live parts are first in the drop order.

**Independent Test**: render the instruction with the capabilities and check the search-first
clause; run the eval in CI and check it reports recall@k for both modes and latency.

**Acceptance Scenarios**:

1. **Given** the agent built with the search tool, **When** its instruction is rendered,
   **Then** it contains the search-first clause naming `search_knowledge` and the exact lookups,
   and the capability list shows `search_knowledge`.
2. **Given** the fixture corpus (wcl, guide and chat chunks) and about 30 labelled questions
   with recorded embeddings, **When** the eval runs in CI, **Then** it reports recall@k for
   hybrid and vector-only, and latency, without any network call.
3. **Given** live credentials (team-lead only), **When** the live mode runs on the cheapest
   model with a question cap, **Then** it reports filter-extraction accuracy and the
   local-answer rate with and without search-first.

---

### Edge Cases

- A character the workspace does not know (not an own character, friend or known player):
  correctable error; the agent may retry without the filter and put the name in a query.
- A query string that is empty, only punctuation, or longer than 300 characters; more than five
  queries; zero queries: correctable error, no search.
- A filter value crafted to widen the scope: `%`, `*`, `_`, a SQL fragment, another workspace's
  conversation id, a `kind` outside the enum. Values are validated, never interpolated; no
  combination returns anything outside visibility.
- A report code containing anything but letters and digits, or longer than 32 characters:
  correctable error.
- `since` after `until`, or a date that does not parse: correctable error.
- The zone list cannot be loaded (WCL down, cold cache): encounters resolve from the
  workspace's known encounters only; an unresolvable name is an unknown error, not a crash.
- A spec given without a class: filters by that spec in every class that has it ("Holy" matches
  Paladin and Priest); a spec that exists in no class is an error.
- The search runs outside an authenticated chat turn (greeting, guide jobs): the tool fails
  closed with "unavailable in this session".
- The database is slow or down: the tool returns a plain error after a bounded wait; the turn
  goes on (the agent can still call Warcraft Logs).
- A chunk appears in several phrasings' results and several fetches render the same source:
  it appears once, with the best score.

## Requirements *(mandatory)*

### Functional Requirements

**Name resolver (sc-304)**

- **FR-001**: One module (`backend/app/services/name_resolver.py`) MUST resolve: class, spec
  (with role), a class+spec phrase, encounter (name or id to id, with its zone), difficulty
  (name, abbreviation or id to id) and character (to name, realm, region, class, spec).
- **FR-002**: Class and spec resolution MUST reuse `normalize_class_name`, the roster
  (`roster_snapshot`, `resolve_spec`) and `role_for_spec`; the only new data is an alias table
  of abbreviations (`warr`, `dh`, `dk`, `ret`, `prot`, `resto`, `disc`, `bm`, `mm`, `sv` and
  similar) that maps to canonical values checked against the roster. No second class/spec map.
- **FR-003**: Encounter resolution MUST read the shared zone list (the one `patch.py` and
  `find_encounter` read) and the workspace's `known_encounters`, and difficulty words inside an
  encounter phrase ("heroic ulatek") MUST be recognised and returned separately.
- **FR-004**: Character resolution MUST read the workspace's `user_characters` (own and
  friends) and `known_players`, scoped to the caller's workspace only.
- **FR-005**: Matching MUST be case-, accent- and apostrophe-insensitive (also ignoring spaces
  and hyphens).
- **FR-006**: An unknown or ambiguous value MUST produce a typed error (kind of value, the
  input, `unknown` or `ambiguous`, and up to five close matches) that a caller can turn into a
  message the agent can act on. The resolver never returns an empty "match".

**Search tool (sc-114)**

- **FR-010**: The agent MUST have a `search_knowledge` tool with: `queries` (1–5 strings),
  `kind`, `class_name`, `spec`, `encounter`, `difficulty`, `report_code`, `character`, `since`,
  `until`, `k`, and `user_stated` (the filters the user stated explicitly). `kind`,
  `class_name`, `spec` and `difficulty` MUST be enums in the tool schema.
- **FR-011**: The queries MUST run concurrently, each as a hybrid search: the top N = 40
  chunks by cosine distance to the query's `RETRIEVAL_QUERY` embedding and the top 40 by
  keyword rank (`ts_rank_cd`), fused by reciprocal rank fusion, score `1/(60 + rank)` summed
  over the two lists. `k` defaults to 8 and is limited to 1–15.
- **FR-012**: The per-query lists MUST then be fused across queries by the same RRF over each
  query's fused rank (contributions of one chunk summed), and deduplicated by source (wcl:
  report code + fight + chunk label; guide: guide + section; chat: conversation + message seq),
  keeping the best-scoring chunk per source.
- **FR-013**: Visibility MUST be applied inside the SQL of every search: a WCL chunk only when
  its fetch passes the 039 visibility rule for the caller's workspace (through
  `fetch_visible_clause`, the rule's one definition), a chat chunk only under the workspace's
  row-level security (plus an explicit workspace predicate), guides globally. Search code
  never names the raw fetch table or model itself.
- **FR-014**: All filter values MUST be normalised by the resolver (FR-001); an unknown or
  ambiguous value MUST return a correctable error to the agent, not an empty result. Report
  codes MUST match letters and digits only (1–32); dates MUST parse as ISO dates.
- **FR-015**: Visibility, `kind`, `report_code` and filters listed in `user_stated` MUST be
  hard. When fewer than k hits come back, the soft filters MUST be dropped cumulatively in the
  order spec, class, encounter, dates (`since` and `until` together), re-running the search
  after each drop, until k hits are found or no soft filter is left. `difficulty` and
  `character` are never dropped. The result MUST list the dropped filters, and hits found only
  after a drop MUST rank below hits that met every filter.
- **FR-016**: A filter narrows only the kinds that carry it; kinds without the attribute are
  not excluded by it (see Filter applicability).
- **FR-017**: Each hit MUST be compact: kind, a source pointer (report code + fight + label;
  guide class/spec/content type + section; conversation id + message seq), the text truncated
  to 400 characters, and the score rounded. The serialised result MUST stay at or under 6,000
  characters; when it would not, the lowest-ranked hits are dropped and `capped` is true.
- **FR-018**: When no query embedder is configured (`get_embedder()` is None) or embedding
  fails, the search MUST run keyword-only and the result MUST say so. Chunks with a NULL
  embedding MUST remain findable by keyword in every mode.
- **FR-019**: The tool MUST take the workspace only from the authenticated chat turn
  (`current_identity`, checked against the ADK session's user), never from arguments, and fail
  closed outside one. Errors are plain tool errors; the turn goes on.

**Search-first + eval (sc-115)**

- **FR-020**: The agent instruction MUST tell the agent to try `search_knowledge` or an exact
  stored-data lookup (`list_stored_fights`, `get_stored_fight_table`,
  `list_stored_reports_for_character`) before a Warcraft Logs fetch when the question could be
  answered from stored data, phrased so it only applies when those tools are exposed.
- **FR-021**: An eval harness under `backend/evals/kb/` MUST hold a fixture corpus covering
  wcl, guide and chat chunks and about 30 labelled questions (expected sources, expected
  filters), with recorded embeddings for corpus and questions, and MUST report recall@k for
  hybrid and vector-only and latency (p50/p95) per mode. CI runs it with no network call.
- **FR-022**: A live mode MUST run the agent on the cheapest chat model over the labelled
  questions with a question cap and report filter-extraction accuracy (tool arguments vs the
  labels) and the local-answer rate (turns with no Warcraft Logs tool call) with and without
  the search-first clause. It is run only by team-lead; CI never runs it.
- **FR-023**: A short write-up in this spec dir MUST recommend the embedding model and whether
  true BM25 is worth it, noting the licences of the candidates. The default model changes only
  on a clear eval win.

### Filter applicability

| Filter | wcl chunks | guide chunks | chat chunks |
|---|---|---|---|
| `class_name`, `spec` | chunk class/spec or any player's | guide class/spec | not applicable |
| `encounter`, `difficulty`, `report_code` | yes | not applicable | not applicable |
| `character` | a player in the chunk | not applicable | a mentioned character |
| `since`, `until` | fight/report start time | not applicable | message time |
| `kind` | yes | yes | yes |

"Not applicable" means the filter does not exclude that kind. Visibility applies to every row
regardless of filters.

### Key Entities

- **Resolved value**: the canonical form of one filter (class, spec + role, encounter id +
  name + zone, difficulty id + name, character name + realm + region + class + spec).
- **Resolution error**: what could not be resolved (field, input, unknown or ambiguous, close
  matches).
- **Search request**: the validated tool arguments after resolution, split into hard and soft
  filters.
- **Hit**: one chunk in the result: kind, source pointer, truncated text, score, and whether it
  was found only after relaxation.
- **Search result**: hits, mode (hybrid or keyword-only), the relaxed filters, and whether the
  cap dropped hits.
- **Eval question**: a question, its expected sources, its expected filters, and its recorded
  embedding.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every abbreviation in FR-002 and the accent/apostrophe forms resolve correctly
  (one test each); every unknown or ambiguous input gives a typed error with close matches.
- **SC-002**: Across the Postgres bypass tests (no-longer-visible fetch, another workspace's
  chat, deleted conversation, crafted filter values), zero out-of-scope chunks are returned.
- **SC-003**: A search result never exceeds the output cap, at the maximum k with maximal
  chunks (tested).
- **SC-004**: On the eval set, hybrid recall@k is reported next to vector-only recall@k, and
  hybrid is not worse than vector-only; search latency p95 on the fixture corpus is reported.
- **SC-005**: The CI suite makes no Vertex, LLM or Warcraft Logs call.

## Assumptions

- The chunk tables and models (`kb_chunks`, `kb_chat_chunks`, migration 0019) come from 043's
  sc-111 milestone merge; until then, tests are written against the agreed columns and run
  after the rebase. Chunks are inserted directly in tests; 043's pipeline is not needed.
- The query embedder is 043's `Embedder` Protocol (`get_embedder()`, `RETRIEVAL_QUERY`); 044
  tests use their own fake.
- `fetch_visible_clause` comes from 045's sc-295 merge; the WCL path is built and tested last.
- Search runs on Postgres (pgvector, full-text search). On SQLite (the default test suite) the
  pure parts (resolver, validation, fusion, relaxation, cap, tool schema) are tested with the
  SQL layer faked; the SQL and visibility are tested on a throwaway `pgvector/pgvector:pg17`.
- Freshness (039's `is_fresh`) is not applied to search: it decides when a stored body may
  replace a WCL call, while a search hit is context; visibility is applied.
- The tool joins a backend tool group registered next to `PROFILE_TOOLS` in `agent_runner.py`.
- The recorded eval embeddings are produced by a deterministic local stand-in until team-lead
  records real Vertex embeddings in the live pass; the write-up says which were used.
