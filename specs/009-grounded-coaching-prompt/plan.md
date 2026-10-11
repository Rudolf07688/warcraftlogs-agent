# Implementation Plan: Grounded, Evidence-Based Coaching

**Branch**: `009-grounded-coaching-prompt` | **Date**: 2026-10-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/009-grounded-coaching-prompt/spec.md`
**Grounding**: `documentation/designs/20261007_prompt_upgrade.md`

## Summary

Make Barnaby's coaching **grounded**: rewrite the agent instruction around an evidence
contract (observed / benchmarked / guidance / inferred), explicit abstention,
validation-before-analysis, verdict-first output with ≤3 confidence-rated fixes, and
persona-after-facts (US1). Back it with deterministic, code-side capabilities the prompt
can rely on:

- a **provenance + completeness envelope** on every Warcraft Logs tool result and
  explicit percentile context (`compare`/`timeframe`, overall + bracket) (US3);
- `compare_player_to_cohort` — a **matched cohort** of 3–5 kill parses from the
  ~75th–95th percentile band located via `totalParses`, duration ±15%, medians and
  ranges, budget-bounded (US2);
- **guide provenance** — patch, generated date, sources, and machine-readable major
  cooldowns on the shared spec guides, with read-time freshness from the current raid
  partition, surfaced in the Class Guides page and agent context (US5);
- `get_cooldown_usage` — **opportunity-based** cooldown coaching over eligible time
  (minus death and intermission windows) using guide cooldowns (US4).

All API behaviour this relies on was verified against the live WCL API (research.md).

## Technical Context

**Language/Version**: Python 3.14 (backend + `wcl_agent`); TypeScript/React (frontend)

**Primary Dependencies**: Google ADK (agent/tools, Gemini + Claude-on-Vertex),
FastAPI + asyncio, SQLAlchemy (async) + Alembic, Pydantic v2, pandas (existing
percentile maths), `requests` WCL client with existing TTL/LRU cache; React + Vite

**Storage**: PostgreSQL — `spec_guides` gains 4 nullable columns (migration 0009);
in-process `wcl_agent.guide_meta` registry (no new store)

**Testing**: pytest + pytest-asyncio (`uv run --extra test pytest -q`), offline with
faked WCL responses; manual review sample per quickstart.md

**Target Platform**: Linux server (Docker Compose locally), single backend process

**Project Type**: Web application (FastAPI backend + React frontend) with an agent
tool library (`wcl_agent/`)

**Performance Goals**: Benchmark answer wall time ≤ +50% vs today's comparable
answer (SC-011); a benchmark costs ≈10 WCL calls at size 5, mostly cache-hits on repeat

**Constraints**: WCL budget 720 points/hour (probed) — benchmark auto-shrinks below
100 / 40 remaining points; leaderboard `page ≤ 20`; tool payloads to the model stay
under the existing 60 KB cap (heavy tables reduced in code); additive-only changes to
existing tool result shapes

**Scale/Scope**: ~40 class/spec guides; 2 new tools, 1 changed tool signature, 1
envelope across 13 WCL tools; 1 migration; 1 frontend component

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment | Status |
|---|---|---|
| **I. DRY & Reuse-First** | One envelope helper used by all tools; reuse WCL client + cache, `_cap`, `METRICS`, `CLASS_SPECS`, `MENU_DISCOVERY`, `stream_response` grounding records, existing guide generation path (`_generate_text`, `ensure_spec_guide`) and Regenerate action. Cohort and cooldown tools share one Casts-table reducer. `current_patch`/`guide_freshness` defined once in `wcl_agent` and imported by backend. | ✅ |
| **II. Methodical, Step-Wise** | Six independently verifiable slices in order (below); each leaves the app working. | ✅ |
| **III. Simplicity (YAGNI)** | No new services, queues, or stores. Cohort compares casts + throughput only (buff/damage-breakdown comparison deferred). Wipe cohorts, analysis trace, eval harness, curated cooldown lists: out of scope. Metadata parsed from the same generation call (no second model call). | ✅ (see Complexity Tracking) |
| **IV. Typed Data Contracts** | Pydantic: `GuideMetaBlock` (model output at the edge), REST schema additions. Dataclasses: `Provenance`, `Completeness`, `PercentileContext`, `GuideMeta`/`GuideCooldown`, cohort/cooldown results (→ `asdict` for ADK). | ✅ |
| **V. Async FastAPI** | REST unchanged in style; guide generation stays off-loop; sync WCL tools still run in ADK worker threads; startup registry load is async DB + sync dict set. | ✅ |
| **VI. GitNexus awareness** | Impact run during planning: `_cap` **CRITICAL** (10 direct, 8 processes) → not modified, envelope added beside it; `_generate_text` **CRITICAL** (spec-guide + guild-summary flows) → signature change limited to returning sources, both callers updated in the same slice; `INSTRUCTION`, `get_report_rankings` **UNKNOWN** → text search: consumed by `build_agent` / `TOOLS` and by tool-name readers (`services/tool_summary.py`, `raids.py`, `encounters.py`) → additive keys only; `_summarize` LOW. Re-run `impact` before each edit and `detect_changes` before each commit. | ✅ |

**Post-design re-check (after Phase 1)**: no new violations. The registry is the only
new in-process mechanism; justified below.

## Project Structure

### Documentation (this feature)

```text
specs/009-grounded-coaching-prompt/
├── plan.md              # This file
├── research.md          # Phase 0 — live-API-verified decisions R1–R14
├── data-model.md        # Phase 1 — columns, Pydantic/dataclass models, tool results
├── quickstart.md        # Phase 1 — per-story checks + review sample for SCs
├── contracts/
│   ├── prompt.md        # Required instruction sections & clauses
│   ├── agent-tools.md   # Envelope, changed/new tools, helpers
│   └── rest-guides.md   # Guides API/UI freshness additions
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
wcl_agent/
├── agent.py             # INSTRUCTION rewrite (US1); register 2 new tools (US2, US4)
├── provenance.py        # NEW — Provenance/Completeness dataclasses + envelope helper (US3)
├── report_tools.py      # envelope on report/character tools; get_report_rankings compare/
│                        #   timeframe + percentiles; whitelist fix (US3)
├── tools.py             # envelope + sample_scope on distribution/compare_specs (US3)
├── fight_time.py        # NEW — resolve_player (ambiguity), dead/intermission windows,
│                        #   eligible time; created in US2, extended/reused in US4
├── benchmark.py         # NEW — compare_player_to_cohort + shared Casts reducer (US2)
├── cooldowns.py         # NEW — get_cooldown_usage, opportunity maths (US4)
├── guide_meta.py        # NEW — GuideCooldown/GuideMeta registry (US5)
└── patch.py             # NEW — current_patch(), guide_freshness() (US5)

backend/
├── migrations/versions/0009_spec_guide_provenance.py   # NEW (US5)
├── app/db/models.py               # SpecGuide: 4 columns (US5)
├── app/db/repository.py           # upsert_spec_guide accepts new fields (US5)
├── app/schemas.py                 # GuideMetaBlock, GuideSource, Guide* additions (US5)
├── app/services/guide.py          # prompt + meta-block parse + sources + registry (US5)
├── app/services/profile_context.py# guide heading shows patch/freshness (US5)
├── app/api/guides.py              # populate new response fields (US5)
├── app/main.py                    # lifespan: load ready guides into registry (US5)
└── tests/
    ├── test_prompt_contract.py    # NEW — required sections/clauses (US1)
    ├── test_provenance.py         # NEW — envelope on each tool, truncation, has_more (US3)
    ├── test_report_rankings.py    # NEW — compare/timeframe, percentiles flattening (US3)
    ├── test_fight_time.py         # NEW — player resolution/ambiguity, interval merge,
    │                              #   dead/intermission windows, eligible time (US2, US4)
    ├── test_benchmark.py          # NEW — band/page maths, clipping, filtering, labels,
    │                              #   budget shrink, wipe → limited, alive-time rates (US2)
    ├── test_cooldowns.py          # NEW — opportunity formula, matching, no-guide
    │                              #   fallback, freshness caveat (US4)
    ├── test_guide_meta.py         # NEW — block parse/strip, invalid block, freshness,
    │                              #   registry load (US5)
    └── test_guide.py / test_spec_guides.py   # extended for new columns/fields (US5)

frontend/src/
├── types.ts                               # guide fields (US5)
└── components/profile/ClassGuidesTab.tsx  # patch, date, "May be out of date", sources (US5)
```

**Structure Decision**: Existing web-app layout. New WCL logic lives in small
single-purpose modules under `wcl_agent/` (matching `tools.py`/`report_tools.py`
style); backend changes are confined to the existing guide slice.

## Delivery Order (independently verifiable slices)

1. **Foundation** — `provenance.py` envelope on all WCL tools + whitelist fix. Verify:
   `test_provenance.py`; existing suite green (additive shape).
2. **US1 (P1) prompt** — rewrite `INSTRUCTION` per `contracts/prompt.md`, *without*
   the benchmark/cooldown tool clauses (they land with their tools). Verify:
   `test_prompt_contract.py`; quickstart US1 checks.
3. **US3 (P3) percentile context** — `get_report_rankings(compare, timeframe)` +
   `percentiles`; distribution `sample_scope`. Verify tests + quickstart US3.
   *(Ordered before US2 because the cohort reuses its percentile flattening.)*
4. **US2 (P2) benchmark** — `benchmark.py`, register tool, add `<BENCHMARK_POLICY>`
   tool clause. Verify `test_benchmark.py` + quickstart US2.
5. **US5 (P5) guide freshness** — migration, model, generation meta/sources,
   registry, API, preamble, UI. Verify `test_guide_meta.py` + quickstart US5.
6. **US4 (P4) cooldown usage** — `cooldowns.py`, register tool, add coaching
   clauses. Verify `test_cooldowns.py` + quickstart US4.
7. **Review sample** — quickstart "Review sample" for SC-001..SC-012.

## Risks

| Risk | Mitigation |
|---|---|
| Guide model omits or malforms the `guide-meta` block | One repair turn on the same session; if that fails, guide still `ready`, metadata NULL ⇒ unknown freshness + rate-only coaching; covered by tests |
| New evidence contract makes the (shared) guide generator hedge or under-deliver | Contract scoped to claims about logged play + explicit authoring permission (research R15); content check in US5 verification |
| Early death makes benchmark rates look low | Player rates over time alive, `dead_s` reported (FR-015a) |
| Duplicate player names in a fight | Tools refuse ambiguous names and return candidates; optional `source_id` (FR-006) |
| Guide-stated cooldowns wrong (talents, hallucination) | Always "~N" approximate; `talent_modified` flag; freshness caveat; cooldown cited to guide |
| Large populations push the band past page 20 | Clip to pages 18–20, disclose sampled band (`band_clipped`) |
| Longer prompt raises latency/cost | Sections replace (not add to) the current prose; measure SC-011 in review |
| Persona clauses weaken the requested "brutal banter" | Keep mistake-first voice; only density/targeting constrained (user decision recorded in spec) |
| Consumers of tool results break | Additive keys only; existing tests for `tool_summary`, `raids`, `encounters` stay green |

## Complexity Tracking

| Addition | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| In-process `wcl_agent.guide_meta` registry | Sync WCL tools (worker threads, no backend import) need guide cooldowns deterministically | Model-passed cooldowns aren't trustworthy inputs; DB access from tools reverses the dependency direction and mixes sync/async; a backend-only tool would be a second tool-construction path |
| 4 new `spec_guides` columns | Patch, date, sources, cooldowns must persist with the guide and be queryable without parsing prose | Embedding in markdown can't be validated or read reliably by tools/UI |
