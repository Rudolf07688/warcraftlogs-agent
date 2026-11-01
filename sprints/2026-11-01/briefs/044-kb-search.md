# Brief 044: knowledge base search

Read `sprints/2026-11-01/briefs/common.md` first: team, contracts, ownership, environment,
hand-off contents. This file adds what is specific to 044.

- **Feature / branch:** 044, `044-kb-search`
- **Tier:** L (Spec Kit: specify, clarify (self-answered), plan, tasks, implement) with gates.
- **Seat:** `dev-3` (new seat: run `member.py me --seat dev-3`, then claim a short first name
  not already taken). Model opus, effort high.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b`. Base `sprint-2026-11-01` (`cda1f42 or later`).
- **Parallel developers:** Ansel on 043 (`dev-a`), Tomas on 045 (`dev-c`).
- **Migration:** none (the 0019 schema and models come from 043's sc-111 milestone merge).
- **Throwaway Postgres:** `wcl-044-pg`, port 15444, `pgvector/pgvector:pg17`.
- **Stories (Shortcut):** sc-304, sc-114, sc-115 (10 pts), in that order.

## Gates and stops
1. **Gate 1 (spec):** after `/speckit-specify` + `/speckit-clarify`. Return the spec path and
   your clarify decisions. Cover the ranking (RRF within and across queries, dedupe by
   source), the hard/soft filter relaxation and the output cap explicitly.
2. **Gate 2 (plan):** after `/speckit-plan` + `/speckit-tasks`. Return the plan path, the
   Constitution Check, GitNexus impact for the risky symbols and the **exact file list per
   story**. I grant from that list.
3. **Stop 3 (sc-304 milestone):** implement sc-304, commit, and return a hand-off for just
   that. I merge it early: 043 and 045 build on the resolver. Implement it first.
4. **Final:** sc-114 and sc-115 on the branch rebased onto the sc-111 merge and Tomas's
   sc-295 merge (the visibility clause, common.md contract 3). P7 review of sc-114 at this
   hand-off. If you are ready before those merges land, build and test the guide and chat
   paths first and the WCL path last; if you would actually sit idle, post a `blocker`.

## Ownership
**Granted now (whole feature):** `backend/app/services/name_resolver.py`,
`backend/app/kb/search.py`, `backend/app/agent_tools/kb_tools.py`, `backend/evals/kb/**`,
new tests `backend/tests/test_name_resolver*.py`, `test_kb_search*.py`, `test_kb_eval*.py`
(and fixtures under `backend/tests/fixtures/kb/**`), `specs/044-kb-search/**`.

**Granted at Gate 2 from your file list (expected):** `wcl_agent/agent.py` (the sc-115
search-first instruction; yours alone this sprint).

**Sequenced (granted at Gate 2, one developer at a time):** `backend/app/agent_runner.py`
(registering your tool group next to `PROFILE_TOOLS`; Tomas needs the same line for sc-131).

Notes:
- The resolver reuses `wcl_agent/game/constants.py` (`normalize_class_name`, spec roles),
  `wcl_agent/game/roster.py` (`resolve_spec`), `wcl_agent/game/patch.py` + `known_encounters`,
  and `user_characters` + `known_players`. No second class/spec map. If you must edit one of
  those files, ask at Gate 2.
- The WCL visibility join goes through `fetch_visible_clause` from `raw_fetches.py` (Tomas
  writes it in sc-295). You never write `RawFetch` or `join raw_fetches` yourself; the 039 guard
  test stays unchanged. Chat chunks rely on tenant RLS: run the query in a session scoped the
  way `read_stored_fetch` does it (`set_scope`).
- Embedding the query uses 043's `Embedder` Protocol (`RETRIEVAL_QUERY`). When
  `get_embedder()` is None or the call fails, fall back to keyword-only and say so (AC7).
- Context bloat matters (compare sc-302, a 220k-token turn): the output cap is a hard limit.

## Acceptance criteria (verbatim from the plan)

### sc-304 Shared name resolver (2)
1. One module resolves encounter (name to id, via `patch.py` and `known_encounters`), class, spec (with role), difficulty and character (`user_characters`, `known_players`), reusing `normalize_class_name` and `resolve_spec`; no second class/spec map.
2. Matching is case-, accent- and apostrophe-insensitive; `warr, dh, dk, ret, prot, resto, disc, bm, mm, sv` resolve (a test per abbreviation); "Ula'tek" and "ulatek" give the same id; "arms warr" gives Warrior / Arms.
3. An unknown or ambiguous value returns a typed, correctable error with close matches; never a silent empty result.
4. Both the chunk writers (sc-112, sc-305) and search (sc-114, sc-131) use it (checked at merge).

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

Drop order if we run late (Maren, board #9): sc-115 live-mode measures go first (keep the
prompt and the CI recall eval). Ask before dropping anything.

## P7 bypass attempts you should already have tests for
A chunk whose fetch is no longer visible (grant expired, report turned private, row gone), a
chat chunk from another workspace, filter values crafted to widen the scope (wildcards,
`%`, SQL fragments, another tenant's conversation id, `kind` outside the enum), a deleted
conversation.
