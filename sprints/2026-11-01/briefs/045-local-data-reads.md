# Brief 045: local data reads (raw-store probe, races, hit rate, exact lookups)

Read `sprints/2026-11-01/briefs/common.md` first: team, contracts, ownership, environment,
hand-off contents. This file adds what is specific to 045.

- **Feature / branch:** 045, `045-local-data-reads`
- **Tier:** M under the scrum master: one Spec Kit pass (specify, clarify self-answered, plan,
  tasks, implement) with **one gate after the plan**, plus a merge stop (below).
- **Seat:** `dev-2` (Tomas). Model opus, effort medium.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-c`. Base `sprint-2026-11-01` (`cda1f42 or later`).
- **Parallel developers:** Ansel on 043 (`dev-a`), dev-3 on 044 (`dev-b`).
- **Migration:** none.
- **Throwaway Postgres:** `wcl-045-pg`, port 15445, `pgvector/pgvector:pg17` (Redis, if you need
  a real one: 16445).
- **Stories (Shortcut):** sc-295, sc-296, sc-132, sc-131 (10 pts), in that order.

## Gate and stops
1. **Gate (plan):** after specify, clarify, `/speckit-plan` and `/speckit-tasks`. Return the
   plan path, the Constitution Check, GitNexus impact for the risky symbols
   (`read_visible_fetch`, `read_stored_fetch`, the writer, the client's single-flight / lane
   path) and the **exact file list per story**. I grant from that list.
2. **Stop 2 (part 1: sc-295 + sc-296):** commit and return a hand-off for those two. I merge
   them early: 044 needs the visibility clause (common.md contract 3) and Ansel needs the
   writer files after you. Build `fetch_visible_clause` early in sc-295.
3. **Final:** sc-132, then sc-131 (sc-131 needs the resolver merge and `raw_fetches.py` back
   from Ansel; I post the grant on the board).

## Ownership
**Granted now:** `backend/app/repositories/raw_fetches.py`, `backend/app/services/raw_fetch_reads.py`,
`backend/app/services/fetch_persistence.py`, `backend/app/config.py`, `wcl_agent/cache/cache.py`,
`wcl_agent/client/wcl_client.py`, `backend/app/api/cache_stats.py`, `backend/app/schemas.py`
(`CacheStats` only), `backend/app/agent_tools/stored_data_tools.py`, tests
`backend/tests/test_raw_store*.py`, `test_raw_fetch*.py`, `test_cache_stats.py`,
`test_cache_families.py`, new `test_stored_data_tools*.py`, `test_local_answer*.py`, and
`specs/045-local-data-reads/**`.

**Hand-overs after Stop 2 (part 1 merged):** `fetch_persistence.py`, `config.py` and
`raw_fetches.py` go to Ansel (043). `raw_fetches.py` comes back to you for sc-131 when Ansel
posts `released`. If you need `config.py` again, ask on the board.

**Not yours:** `backend/app/api/ws.py` (Ansel, sc-305). For the sc-132 per-turn "answered
locally" signal, find a seam outside `ws.py` (the client's per-turn context, or the turn
wrapper). `backend/app/agent_runner.py` is sequenced between you and dev-3 (tool
registration): name it in your Gate list if you need it and I'll order it.

Notes:
- Contract 3 (common.md): `fetch_visible_clause` is the one definition of the visibility rule,
  used by `read_visible_fetch` and by 044's search join. Keep the 039 guard test unchanged.
- sc-131 tools read only through the visibility rule; not visible and not stored give the
  same result. Use the tool names in common.md contract 4 and the resolver for arguments.
- Your memory notes that you sometimes miss state-machine edge cases (Maren, board #7): the
  breaker (closed / open / half-open), the gone-vs-write races and Redis refill are exactly
  that. Draw the states in the plan and test each transition.

## Acceptance criteria (verbatim from the plan)

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

### sc-132 Local-answer hit rate (2)
1. Raw-store probe counters `hit`, `miss`, `not_visible`, `timeout` appear in the existing cache stats (`read_stats`) wherever those are shown today.
2. A turn with no external WCL call counts as answered locally; the local-answer rate over the stats window is exposed with the cache stats.
3. Tests for both.

### sc-131 Exact lookups in stored data (3)
1. Agent tools return stored fights for a report, the stored table for a report fight (and metric), and reports stored for a character, reading only through the `read_visible_fetch` rule; no embeddings.
2. Not visible and not stored both return the same "not stored locally" result, so the agent falls back to WCL and the existence of invisible data never leaks.
3. Character and encounter arguments are normalised by the resolver.
4. Output is compact and bounded; tests cover a not-visible fetch.

Drop order if we run late (Maren, board #9): sc-296 is second to go. Ask before dropping.
