# Implementation Plan: Knowledge base search (epic 100)

**Branch**: `044-kb-search` | **Date**: 2026-11-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/044-kb-search/spec.md` (Gate 1 passed, #37)

## Summary

Three stories in order. **sc-304**: one resolver module turns loose names into canonical
class/spec (+ role), encounter id, difficulty id and workspace characters, reusing the roster,
the cached zone list and the workspace tables; it exposes `name_key` for 043's writers and
raises a typed, correctable `ResolutionError`. **sc-114**: a backend agent tool
`search_knowledge` validates and resolves its typed arguments, embeds the 1–5 queries once
(043's `Embedder`, `RETRIEVAL_QUERY`; keyword-only fallback), runs one hybrid statement per
query concurrently (vector and keyword legs, visibility in the SQL through 045's
`fetch_visible_clause` and tenant RLS), fuses by RRF twice, dedupes by source, relaxes soft
filters in a fixed order and caps the output at 6,000 characters. **sc-115**: a search-first
clause in the agent instruction and an eval harness (fixture corpus, ~30 labelled questions,
recall@k hybrid vs vector-only, latency; `record` and `live` modes for team-lead).
Details: [research.md](research.md), [data-model.md](data-model.md),
[contracts/](contracts/).

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: FastAPI app, google-adk (tool schema from type hints), SQLAlchemy 2
async (asyncpg), pgvector's SQLAlchemy type (043 adds the package). No new dependency in 044.

**Storage**: PostgreSQL 17 + pgvector ≥ 0.8 (043's migration 0019); no 044 migration.

**Testing**: pytest SQLite suite (resolver, validation, fusion, relaxation, cap, tool, prompt,
eval metrics) + Postgres-only tests on a throwaway `pgvector/pgvector:pg17` (port 15444):
visibility, bypass attempts, the real SQL, the eval run.

**Target Platform**: Linux server (Docker compose).

**Project Type**: web service backend + `wcl_agent` package (instruction text only).

**Performance Goals**: a search of 5 queries on the fixture corpus in well under 1 s (p95
reported by the eval); 5 queries share one embedding call.

**Constraints**: visibility inside SQL (no post-filtering); output ≤ 6,000 chars; whole search
bounded (8 s) and never fails the turn; no Vertex/LLM/WCL call in CI; search code never names
the raw fetch model/table (039 guard test unchanged).

**Scale/Scope**: 3 new modules, 1 eval package, 2 one-line/one-paragraph edits to shared files.

## Constitution Check

*GATE: passed before Phase 0; re-checked after Phase 1 (no change).*

| Principle | Status |
|---|---|
| I. Reuse-first | Roster (`roster_snapshot`, `resolve_spec`, `normalize_class_name`, `role_for_spec`), the cached zone list (`load_world_zones`), `_DIFFICULTY_NAMES` + `MYTHIC_PLUS_DIFFICULTY_ID`, `known_encounters` / `known_players` / `user_characters`, `set_scope`, `current_identity`, `ToolGroup`, `settings.raw_store_reverify_days`, 045's `fetch_visible_clause`, 043's `Embedder`. Enums built from `CLASS_SPECS`, not copied. The only new data is an abbreviation alias table validated against the roster. |
| II. Step-wise | sc-304 → milestone merge → sc-114 (guide + chat paths, then WCL after the sc-295 merge) → sc-115. Each slice tested before the next. |
| III. Simplicity | Plain functions + frozen dataclasses; Python RRF over two small legs; no new service, table, cache or dependency. |
| IV. Typed contracts | `ClassSpec`, `Resolved*`, `ResolutionError`, `SearchFilters`, `SearchRequest`, `Hit`, `SearchResult` dataclasses; tool args typed with `Literal` enums. |
| V. Async | DB and embedder I/O async; queries concurrent via `asyncio.gather`, one session each; bounded by timeouts. |
| VI. GitNexus | Impact below; detect-changes before every commit. |
| VII. shadcn | No UI. |
| VIII. Backlog | Stories In Progress → Under Review; follow-ups as `backlog:` notices (`backlog:difficulty-names`, `backlog:find-encounter-resolver`). |

## GitNexus impact (risky symbols, upstream, worktree index)

| Symbol | Edit | Risk | Callers / processes | Mitigation |
|---|---|---|---|---|
| `agent_runner._get_runner` | add `KB_TOOLS` to `extra_groups` | **HIGH** (1 direct; greeting, guild summary, chat turn processes) | every agent build (chat, greeting, guide summary) gets the tool | tool fails closed without an authenticated turn (tested); one-line change; `test_capabilities`, `test_prompt_contract`, `test_runner_retry`, `test_greeting` must stay green |
| `wcl_agent/agent.py` `_INSTRUCTION_BODY` (read by `build_instruction`) | add the search-first clause to `<EVIDENCE_PLAN>` | `build_instruction`: UNKNOWN (ADK calls it via `functools.partial`); text search: `test_prompt_contract.py`, `INSTRUCTION` snapshot | no braces, time block stays last, clause conditioned on "when exposed in this session"; `test_prompt_contract` stays green, new test asserts the clause |
| `render_capability_summary` | none (new group only) | HIGH (7 upstream) | the summary budget `CAPABILITY_SUMMARY_MAX_CHARS = 4000` is shared: today 3,283 chars with the profile group; 044 adds ~190, 045's three tools ~500 → ~3,970 | short docstring first paragraph (< 160 chars); asserted after both merges; if over, the second merger shortens its own lines (flagged to Ilse) |
| `normalize_class_name`, `resolve_spec`, `load_world_zones` | none (called only) | HIGH (callers elsewhere) | unchanged | read-only reuse |

## Project Structure

### Documentation (this feature)

```text
specs/044-kb-search/
├── spec.md  plan.md  research.md  data-model.md  quickstart.md  tasks.md
├── checkpoint.md          # written before implementation
├── eval-writeup.md        # sc-115 AC4
└── contracts/  name-resolver.md  search-knowledge.md
```

### Source code — exact file list per story

**sc-304 (resolver; stop 3 milestone)**
- `backend/app/services/name_resolver.py` (new)
- `backend/tests/test_name_resolver.py` (new)

**sc-114 (search tool)**
- `backend/app/kb/search.py` (new): filters, SQL legs, fusion, relaxation, cap
- `backend/app/agent_tools/kb_tools.py` (new): `search_knowledge` + `KB_TOOLS`
- `backend/app/agent_runner.py` (**sequenced**, one import + `KB_TOOLS` in `extra_groups`)
- `backend/tests/test_kb_search.py` (new, SQLite: validation, fusion, relaxation, cap, tool, fail-closed, keyword fallback)
- `backend/tests/test_kb_search_pg.py` (new, Postgres: SQL, visibility, bypass attempts)

**sc-115 (search-first + eval)**
- `wcl_agent/agent.py` (granted at Gate 2: the clause in `_INSTRUCTION_BODY` only)
- `backend/evals/kb/__init__.py`, `__main__.py`, `harness.py`, `standin.py`, `live.py` (new)
- `backend/evals/kb/corpus.json`, `questions.json` (new; `embeddings.json` written by team-lead's `record`)
- `backend/tests/test_kb_search_prompt.py` (new: the rendered instruction + capabilities)
- `backend/tests/test_kb_eval.py` (new: metrics + fixture integrity on SQLite; the run on Postgres)
- `specs/044-kb-search/eval-writeup.md` (new)

No other file. Not touched: `raw_fetches.py` (045), the chunk tables/models (043),
`test_raw_store_visibility.py` (unchanged guard), `wcl_agent/game/*`, `wcl_agent/tools/*`.

**Structure Decision**: the resolver is a backend service (it reads tenant tables); the search
core sits in 043's `backend/app/kb/` package (`kb/search.py` is mine); the tool follows the
`agent_tools/profile_tools.py` pattern; the eval follows `backend/evals/guides/`.

## Dependencies and order

1. sc-304 now → commit → stop 3 (Ilse merges early; 043 and 045 import it).
2. sc-114 pure parts (validation, fusion, relaxation, cap, tool) on SQLite with the SQL layer
   faked; then the guide and chat SQL paths after the sc-111 merge (0019 + models); the WCL
   path after Tomas's sc-295 merge (`fetch_visible_clause`). `agent_runner.py` when Ilse grants
   it (Tomas needs the same line for sc-131).
3. sc-115 prompt + eval after sc-114; live mode last (drop order 1).

## Complexity Tracking

No violations. Two choices recorded for review:

| Choice | Why | Simpler alternative rejected because |
|---|---|---|
| Abbreviation alias table in the resolver | AC2 needs `warr`, `ret`, `bm`… which no existing map has | adding aliases to `constants.py` would change a shared module other features read; the table only maps to canonical names checked against the roster |
| `Literal` enums built at import from `CLASS_SPECS` | AC1 enums without a copied list | static `Literal["Warrior", …]` would be a second class/spec list |
