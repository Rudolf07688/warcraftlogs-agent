# Tasks: Knowledge base search (044)

**Input**: `specs/044-kb-search/` (spec, plan, research, data-model, contracts, quickstart)
**Tests**: included (ACs require them). Postgres-only tests run on `wcl-044-pg` (port 15444).
Stories: US1 = sc-304, US2 = sc-114, US3 = sc-115.

## Phase 1: Setup

- [X] T001 Write `specs/044-kb-search/checkpoint.md` (decisions, files, where implementation starts) and confirm the SQLite baseline count with `env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q`

## Phase 2: Foundational

None: no shared infrastructure beyond the stories (no migration; 043 owns the schema).

## Phase 3: US1 — shared name resolver (sc-304, P1) — STOP 3 milestone

**Goal**: one module resolves class, spec (+role), class+spec phrases, difficulty, encounter and
character, with `name_key` and a typed `ResolutionError`.
**Independent test**: `pytest backend/tests/test_name_resolver.py`.

- [X] T002 [US1] Write tests first in `backend/tests/test_name_resolver.py`: `name_key` (accents, apostrophes, case, hyphens, spaces); one test per abbreviation `warr, dh, dk, ret, prot, resto, disc, bm, mm, sv`; "arms warr"/"warrior arms"/"bm hunter"/"beast mastery hunter" phrases; "prot" ambiguous in `resolve_class_spec`, both pairs in `spec_pairs`; class+spec mismatch error; difficulty names/abbreviations/ids incl. Mythic+; encounter "Ula'tek"/"ulatek"/"ULATEK" same id via patched `load_world_zones`, "heroic ulatek" returns difficulty 4, typo gives close matches, ambiguous across ids, zone list failure falls back to `known_encounters`; character from own/friend/known player, "Name-Realm" disambiguation, another tenant's rows never used; every error carries field/value/reason/matches
- [X] T003 [US1] Implement `backend/app/services/name_resolver.py` per `contracts/name-resolver.md`: `name_key`, `ResolutionError`, `ClassSpec`, `ResolvedEncounter`, `ResolvedDifficulty`, `ResolvedCharacter`, alias tables checked against `roster_snapshot()`, `resolve_class`, `resolve_class_spec`, `spec_pairs`, `resolve_difficulty` (reusing `_DIFFICULTY_NAMES` and `MYTHIC_PLUS_DIFFICULTY_ID`), async `resolve_encounter` (zone list + `known_encounters`), async `resolve_character` (`user_characters` + `known_players`, explicit tenant predicate)
- [X] T004 [US1] Run the resolver tests + full SQLite suite; mutation-check two tests (drop the accent strip; drop the tenant predicate) and confirm they fail; GitNexus `detect-changes`; commit; post `backlog:difficulty-names` and `backlog:find-encounter-resolver`; return the stop-3 hand-off

## Phase 4: US2 — parallel hybrid search tool (sc-114, P1)

**Goal**: `search_knowledge` with typed filters, visibility in SQL, RRF twice, dedupe, relaxation,
cap, keyword fallback.
**Independent test**: `pytest backend/tests/test_kb_search.py` (SQLite) and
`backend/tests/test_kb_search_pg.py` (Postgres).

### Pure parts (no 0019 needed)

- [X] T005 [US2] Write SQLite tests in `backend/tests/test_kb_search.py` for argument validation (queries 1–5, length, no-alnum; report code regex incl. `%`, `*`, `'; --`; dates; since > until; k bounds), filter building from resolved values, hard/soft split from `user_stated`, `fuse` (per-query RRF `1/(60+rank)`, cross-query RRF, dedupe by source, tie-break), relaxation order spec → class → encounter → dates with difficulty/character never dropped and relaxed hits ranked below, `cap` (400-char hits, ≤ 6,000 chars at k=15 with maximal chunks, `capped`), keyword-only mode when `get_embedder()` is None or raises, with the SQL layer faked
- [X] T006 [US2] Implement the pure core of `backend/app/kb/search.py`: `SearchFilters`, `SearchRequest`, `Candidate`, `Hit`, `SearchResult`, `fuse`, `relax` loop over an injectable per-query runner, `cap`, embedding step with timeout + fallback note, concurrency via `asyncio.gather` with one session per query, overall timeout
- [X] T007 [US2] Write tool tests in `backend/tests/test_kb_search.py`: enums in the generated schema (`kind`, `class_name`, `spec`, `difficulty`, `user_stated`); fail closed without `current_identity` or with a tenant/session mismatch; resolver errors returned as correctable tool errors; database error → plain error; result shape per `contracts/search-knowledge.md`
- [X] T008 [US2] Implement `backend/app/agent_tools/kb_tools.py`: `search_knowledge` (args → resolver → `SearchRequest` → `search` → dict) and `KB_TOOLS = ToolGroup("Stored knowledge", (search_knowledge,))` with a first docstring paragraph under the 160-char line budget

### SQL paths (after the sc-111 merge: rebase onto `sprint-2026-11-01`)

- [X] T009 [US2] Implement the per-query statement in `backend/app/kb/search.py` (R4): UNION ALL branches with per-branch `ORDER BY … LIMIT 40`, vector leg on `kb_chunks`/`kb_chat_chunks`, keyword legs (`simple` for wcl, `english` for guide and chat, OR-ed lexemes), filter applicability per kind, `SET LOCAL hnsw.iterative_scan`, `set_scope`, chat `tenant_id` predicate; guide and chat branches first, wcl branch left closed (returns nothing) until T011
- [X] T010 [US2] Write Postgres tests in `backend/tests/test_kb_search_pg.py` for guide and chat paths: hybrid ranking on inserted chunks with fake vectors, NULL-embedding rows found by keyword, another workspace's chat chunk never returned (RLS-only check with no predicate path too), deleted conversation's chunks gone, crafted values (`%`, SQL fragment, another tenant's conversation id) never widen scope, `kind` filter, relaxation on real SQL

### WCL path (after Tomas's sc-295 merge: rebase again)

- [X] T011 [US2] Open the wcl branch in `backend/app/kb/search.py` through `fetch_visible_clause(kb_chunks.raw_fetch_id, tenant_id=…, since=now - raw_store_reverify_days)`; confirm `backend/tests/test_raw_store_visibility.py` guard still passes unchanged
- [X] T012 [US2] Add WCL Postgres tests to `backend/tests/test_kb_search_pg.py`: visible public fetch returns; grant expired, report turned private, row gone (cascade) and a granted-to-another-tenant fetch return nothing; no filter combination (report_code, character, encounter, class/spec, dates, kind) returns an invisible chunk; mutation-check by dropping the visibility clause
- [X] T013 [US2] When Ilse grants it: register `KB_TOOLS` in `backend/app/agent_runner.py` (`extra_groups=(PROFILE_TOOLS, KB_TOOLS)` plus import); run `test_capabilities`, `test_prompt_contract`, `test_runner_retry`, `test_greeting`; release the file on the board

## Phase 5: US3 — search-first prompting + eval (sc-115, P2)

**Goal**: the instruction prefers local lookups; an eval measures recall@k hybrid vs vector-only and latency.
**Independent test**: `pytest backend/tests/test_kb_search_prompt.py backend/tests/test_kb_eval.py`.

- [X] T014 [US3] Write `backend/tests/test_kb_search_prompt.py`: the rendered instruction (with `KB_TOOLS` in `extra_groups`) contains the search-first clause naming `search_knowledge`, `list_stored_fights`, `get_stored_fight_table`, `list_stored_reports_for_character`, conditioned on the tools being exposed; capabilities list `search_knowledge`; no braces; time block still last
- [X] T015 [US3] Add the search-first clause to `<EVIDENCE_PLAN>` in `wcl_agent/agent.py` `_INSTRUCTION_BODY` (text only)
- [X] T016 [P] [US3] Create the fixture corpus `backend/evals/kb/corpus.json` (wcl, guide, chat chunks; ~15 each) and `backend/evals/kb/questions.json` (~30 labelled questions with expected chunk ids and filters)
- [X] T017 [P] [US3] Implement `backend/evals/kb/standin.py` (deterministic hashed-trigram 768-d unit vectors) and the metric helpers (recall@k, p50/p95) in `backend/evals/kb/harness.py`
- [X] T018 [US3] Implement the harness run in `backend/evals/kb/harness.py` (load corpus into Postgres via repository functions and direct inserts, run `search` per mode `hybrid`/`vector`/`keyword`, report) and the CLI `backend/evals/kb/__main__.py` (`run`, `record`, `live`) + `backend/evals/kb/__init__.py`
- [X] T019 [US3] Write `backend/tests/test_kb_eval.py`: SQLite: fixture integrity (≥ 28 questions, every expected id exists, all three kinds covered), stand-in determinism and unit norm, recall/latency math; Postgres: the run reports recall for every mode and latency, and asserts hybrid ≥ vector only when the embeddings set starts with `vertex:`
- [X] T020 [US3] Implement `backend/evals/kb/live.py`: `record` (real embedder, ≤ 300 texts, writes `embeddings.json`) and `live` (cheapest model, ≤ 30 questions × with/without clause; filter accuracy + local-answer rate); no test calls it (drop order 1)
- [X] T021 [US3] Write `specs/044-kb-search/eval-writeup.md`: embedding-model recommendation, BM25 options with licences, which embedding set produced the numbers; post `live-check:044` with the exact `record`/`live` steps

## Phase 6: Polish & cross-cutting

- [ ] T022 Full SQLite suite + Postgres-only tests (044 + 039 visibility) green; GitNexus `analyze --index-only` + `detect-changes --scope all`; footprint check vs `sprint-2026-11-01`; stop `wcl-044-pg`
- [ ] T023 P7: scoped `qa-security` review of sc-114 (search.py, kb_tools.py, the SQL); fix findings; hand-off with AC → test table

## Dependencies

- US1 (T002–T004) first; stop 3 after T004.
- US2: T005–T008 need only US1; T009–T010 need the sc-111 merge; T011–T012 need the sc-295 merge; T013 needs Ilse's grant.
- US3: T014–T015 need T008; T016–T017 parallel any time after US1; T018–T019 need T009; T020 last.

## Parallel examples

- After US1: T016 and T017 (eval data and helpers) alongside T005–T008.
- Waiting on merges: build T014–T017 while T009/T011 wait.

## Implementation strategy

MVP = US1 (milestone merge). Then US2 pure parts, guide/chat SQL, WCL SQL; then US3 prompt and
CI eval; live mode last (first to drop if late, per board #9).
