# Implementation Plan: Grounded, Patch-Aware Class Guides

**Branch**: `015-grounded-class-guides` | **Date**: 2026-10-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/015-grounded-class-guides/spec.md`; grounding
document `documentation/wow_guide_grounding_plan_v2.md`.

## Summary

Guides become **evidence-gated, per content type, and agent-first**. Each spec gets two
independent guides (Raid, Mythic+). Each guide is produced by a plain-async pipeline in
`backend/app/services/guide_pipeline/`:

1. a per-run briefing: live date, exact build from Blizzard's version endpoint, latest
   hotfix from Blizzard's hotfix articles, raid tier, Mythic+ season, roster;
2. a WCL data sheet from logs-only top rankings, which include talents and gear, plus
   casts, uptimes and stats for a 20-player cohort;
3. a version-filtered research fact sheet (Gemini `google_search` + `url_context`, filtered
   in code);
4. a tool-less author that writes structured claims citing evidence ids;
5. deterministic checks;
6. a stronger, different reviewer model for up to 3 rounds;
7. code-rendered outputs: a compact **coaching brief** for the agent and a readable guide.

The agent receives whole briefs matched to the conversation's content type, either inline
in the preamble (budgeted, never truncated) or via a new `get_coaching_brief` tool.
`get_cooldown_usage` uses the brief for the matching content type. The `<CURRENT_TIME>` line
becomes live through an ADK instruction provider. The class/spec roster comes from WCL
`gameData` (cached) with a static fallback that adds Devourer. `spec_guides` gains a
`content_type` dimension, a published-vs-latest-run split (needs-review drafts never reach
the agent), staleness and in-use tracking. Inaccuracy reports are stored in a new global
table.

Two more pieces:

- **UI:** a toolbar Raid/Mythic+ switch, an other-type status dot per row, and viewer tabs.
- **Measurement:** a maintainer-run accuracy check with a committed baseline gates the
  whole effort.

## Technical Context

**Language/Version**: Python 3.14 (backend, `wcl_agent`); TypeScript + React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async + Alembic, Pydantic v2, google-adk 2.10 (chat agent only), google-genai (guide pipeline: `aio.models.generate_content` with `response_schema`, `google_search`, `url_context`), httpx (WCL + version source), redis.asyncio via feature 014 `get_or_load`; frontend: shadcn/ui (+ `tooltip`), Tailwind v4, react-icons. **No new Python or npm dependency.**

**Storage**: PostgreSQL (migration `0011_guide_content_types`: `spec_guides` extended, new `guide_inaccuracy_reports`); Redis cache families `game_classes`, `spec_datasheet`, `guide_research`, `live_version`, `hotfix_feed`

**Testing**: pytest + pytest-asyncio (auto), SQLite fixtures, `wcl_fakes`, fake genai client; maintainer-run live accuracy check `python -m backend.evals.guides`; frontend `npm run build`/lint + manual UI checks (quickstart)

**Target Platform**: Linux containers (Docker Compose); Cloud Run later

**Project Type**: Web application (FastAPI backend + `wcl_agent` package + React frontend)

**Performance Goals**: 95% of guide generations (incl. review) ≤ 10 min (SC-013); preamble build adds ≤ 50 ms (DB read of ≤ 4 briefs, no WCL call beyond the cached zone list); `get_coaching_brief` ≤ 100 ms from the loader cache

**Constraints**:
- Briefs ≤ 6,000 characters each and ≤ 12,000 inline per turn, never truncated.
- The agent never sees drafts.
- WCL work for guides runs in `background_lane()` with the existing concurrency cap of 2.
- `wcl_agent` must not import the backend; the brief loader is injected.
- No ADK framework-within-framework (no `LoopAgent`, which is deprecated in 2.10).
- Publisher text is never reproduced (FR-043). Wowhead is never fetched because its
  robots.txt disallows AI crawlers.
- The WCL client budget is about 720 points per hour, so data sheets are cached 12 h, capped
  at about 60–90 points each, and built in the background lane (research R6).
- External sources (the Blizzard version endpoint and news) are best-effort and never block
  generation beyond the FR-006 rule.

**Scale/Scope**: ~40 specs × 2 content types ≈ 80 guides; a handful of tenants; regeneration bounded by the in-use rule (14 days)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — still passing.*

| Principle | Status | How |
|---|---|---|
| I. DRY & reuse | ✅ | One roster source (`wcl_agent/roster.py`, static `CLASS_SPECS` demoted to its fallback, also used by `tools.py` validation). One brief renderer feeds the preamble, the tool and the readable guide's "What the coach looks for". Reuses: `get_or_load` (014) for all new caches; `tools._fetch_rankings`, `benchmark.reduce_casts_entry` / `_per_min` / median logic and `REPORT_PLAYER` tables for the data sheet; `generate_with_retry` (011) for model calls; `spawn` + `pending` dedup for scheduling; `InProcessRateLimiter` for reports; `require_platform_admin` for the admin list; `uiPrefs` pattern for the switch. The guide-meta registry is replaced by one `get_brief` path, not duplicated. |
| II. Step-wise delivery | ✅ | Rollout in quickstart §4: baseline → time/briefing/author → roster → content types + brief → UI → data sheet → checks → research → review → freshness. Each step leaves tests green and is scored by the accuracy check. |
| III. Simplicity | ⚠ justified | Plain async functions instead of ADK agents/workflows; no scheduler service (an opportunistic throttled scan); no new dependency. Added complexity, justified below: a multi-stage pipeline, a new global table, and published-vs-run columns. |
| IV. Typed contracts | ✅ | Pipeline stages exchange Pydantic models (`GenerationBriefing`, `DataSheet`, `FactSheet`, `GuideClaim`, `CoachingBrief`, …). LLM output is validated through `response_schema` + `model_validate`. API models are in `guides-api.md`. Registry and roster use dataclasses. |
| V. Async FastAPI | ✅ | All new endpoints are `async def`. Model calls use the async genai client, WCL the async client, HTTP version/hotfix sources httpx async. Generation runs in background tasks. |
| VI. GitNexus | ⚠ tool degraded | Impact run 2026-10-18, CLI and MCP, before and after re-index. Every target resolves with an empty type and identical unrelated processes (the known quirk in memory), so results are **UNKNOWN** and callers were confirmed by text search (research R13). Treat as HIGH: `CLASS_SPECS` (tools.py, guides API, guide service), `build_preamble` (ws.py), `get_guide_meta`/`set_guide_meta` (cooldowns.py, guide service), `upsert_spec_guide`/`get_spec_guide(s_for)` (profile API, ws.py, guide API), `INSTRUCTION`/`build_agent` (runner, every chat turn). Re-run `impact` before each edit and `detect_changes` before each commit. |
| VII. shadcn UI | ✅ | Reuse check done via the shadcn MCP. Existing ToggleGroup, Tabs, Dialog, Field, Textarea, Alert, Badge. Add `@shadcn/tooltip` with the MCP's add command, then run its audit checklist. Only hand-built piece: an 8 px status-dot `span` inside the tooltip trigger, since no registry item is a bare dot. |

**HIGH-risk warning**:
- **What changes:** the guide key (`(class, spec)` → `(class, spec, content_type)`), the
  registry API, the preamble guide block, the `CharacterOut` guide fields and the `INSTRUCTION`
  delivery.
- **Why it's risky:** these touch every chat turn, the profile page and the Class Guides tab.
- **Mitigation:**
  - Migration 0011 keeps existing guides published as `raid`.
  - The prompt-contract, profile-context and spec-guide test suites are updated in the same
    step as each change.
  - The accuracy check runs after each step.

## Project Structure

### Documentation (this feature)

```text
specs/015-grounded-class-guides/
├── plan.md              # this file
├── research.md          # Phase 0 decisions R1–R14
├── data-model.md        # tables, pipeline models, registry, roster, caches, eval data
├── quickstart.md        # run/verify/rollout
├── contracts/
│   ├── guides-api.md       # REST + CharacterOut changes + status labels
│   ├── agent-context.md    # brief text, preamble, get_coaching_brief, cooldown tool, prompt
│   ├── guide-pipeline.md   # stages, prompts, checks, staleness, config
│   ├── ui-guides.md        # library switch, dot, viewer tabs, report dialog, characters tab
│   └── accuracy-check.md   # eval command, inputs, metrics, release gate
└── tasks.md             # /speckit-tasks (not created here)
```

### Source Code (repository root)

```text
wcl_agent/
├── agent.py              # INSTRUCTION → build_instruction provider; <COACHING_BRIEFS>; TOOLS += get_coaching_brief
├── constants.py          # CLASS_SPECS gains Devourer (fallback only); role sets unchanged
├── roster.py             # NEW load_roster()/roster_snapshot() (gameData classes, cached)
├── guide_meta.py         # BriefRecord + set_brief_loader/get_brief (replaces GuideMeta registry)
├── guides_tool.py        # NEW get_coaching_brief tool
├── cooldowns.py          # content_type param; reads get_brief
├── patch.py              # + current_mplus_season(), mplus_zone_from(), is_mplus_zone()
├── cache.py / cache_models.py  # + families game_classes, spec_datasheet, guide_research, live_version, hotfix_feed
├── queries.py            # + GAME_CLASSES query; rankings query variant with combatant info
└── tools.py              # validation via roster_snapshot()

backend/app/
├── services/guide.py             # ensure_guide(class, spec, content_type), roster merge, character flow, stale scan, last_wanted stamp
├── services/guide_pipeline/      # NEW
│   ├── __init__.py               # run_guide_generation
│   ├── models.py                 # Pydantic pipeline models
│   ├── briefing.py               # build_briefing (+ version/hotfix sources)
│   ├── datasheet.py              # build_data_sheet
│   ├── research.py               # build_fact_sheet + hard filters + tiers
│   ├── llm.py                    # genai structured calls with generate_with_retry
│   ├── prompts.py
│   ├── authoring.py              # author_claims, revise_claims
│   ├── review.py                 # review_claims (+ report verdicts)
│   ├── checks.py                 # run_checks
│   └── render.py                 # build_brief, render_brief_text, render_guide_markdown
├── services/content_type.py      # NEW classify_content_type
├── services/profile_context.py   # briefs block (whole-or-omit) + index
├── api/guides.py                 # content_type routes, reports
├── api/admin_guides.py           # NEW GET /api/admin/guide-reports
├── api/profile.py / api/ws.py    # CharacterGuides; preamble wiring; loader registration in main.py
├── db/models.py, db/repository.py
├── schemas.py, config.py, main.py
└── migrations/versions/0011_guide_content_types.py

backend/evals/guides/             # NEW accuracy check (package + data + reports/baseline.json)
backend/tests/                    # new: test_roster, test_content_type, test_coaching_brief,
                                  #      test_guide_pipeline_{checks,research,review,datasheet},
                                  #      test_guides_api_v2, test_guide_reports, test_stale_scan
                                  # updated: test_prompt_contract, test_profile_context, test_spec_guides,
                                  #      test_guide_meta, test_cooldowns, test_guide, test_guide_reconcile, test_guides_and_boot

frontend/src/
├── components/ui/tooltip.tsx                  # added via shadcn MCP
├── components/profile/ClassGuidesTab.tsx      # switch + dot + content-typed rows
├── components/profile/GuideViewerDialog.tsx   # NEW (tabs, draft warning, report button)
├── components/profile/ReportGuideDialog.tsx   # NEW
├── components/profile/CharactersTab.tsx       # GuideIndicators
├── components/StatusBadge.tsx                 # needs_review tone/labels
├── api/restClient.ts, types.ts, uiPrefs.ts
```

**Structure Decision**: The existing web-application layout is kept. The guide pipeline is a
new sub-package under `backend/app/services/`, because it is backend-only and uses DB and
settings. Agent-facing pieces (roster, brief registry, tool) live in `wcl_agent/` and keep
the backend → `wcl_agent` dependency direction through an injected loader.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Multi-stage pipeline (briefing → data sheet → research → author → checks → review loop → render) instead of one prompt | The spec's core requirements are FR-025, FR-028..FR-031 and FR-036..FR-047: evidence-gated claims, a separate reviewer and deterministic checks. Single-pass generation is the cause of today's hallucinations. | One better prompt: cannot verify claims, cannot keep PTR/Classic out structurally, cannot guarantee ability ids, and has no gate. ADK `LoopAgent` / `SequentialAgent`: deprecated in ADK 2.10 and add session and state plumbing for what is a `for` loop over typed function calls. |
| Published-vs-latest-run columns + `draft` JSON on `spec_guides` | FR-037, FR-049 and FR-053 require that a held or failed update never hides the last verified guide and never reaches the agent. | Status-only (today): a `pending`, `needs_review` or `failed` run hides the guide. A separate versions table: more joins and migrations for a single "current + latest attempt" need. |
| New global table `guide_inaccuracy_reports` without RLS | FR-052. The generator runs outside any tenant scope and must read open reports per guide, and the maintainer reads them across tenants. | A tenant-scoped RLS table: the background generator would need a bypass role or a per-tenant scan. Rows hold only a guide key, a ≤500-char note and a user id, mirroring `spec_guides`' global rationale. |
| Brief loader injection (`set_brief_loader`) instead of the static registry | FR-012/FR-016 need any spec's brief, both content types, current across instances. The registry only held cooldowns, loaded at boot. | Keep the in-process registry and warm it: stale across instances and only refreshed on restart. Importing backend DB code into `wcl_agent` would break the dependency direction. |
| Opportunistic throttled stale scan | FR-050/051 need regeneration after patch, season or hotfix changes, and there is no scheduler. | A cron or worker service: a new deployable for a once-per-10-minutes check that the existing traffic paths (library, chat, boot) already trigger. |
