# Implementation Plan: Profile & Class-Guide Pages — Dedicated, Themed, with a Shared Spec-Guide Library

**Branch**: `008-profile-class-pages` | **Date**: 2026-10-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-profile-class-pages/spec.md`

## Summary

Three cohesive changes to how the profile and class guides work:

1. **Profile page (US1)** — promote the profile from the in-chat `ProfilePanel` modal to a dedicated, routed, **Warcraft-themed** page with a tabbed layout (Characters + Class Guides). All current profile capability (self, unlimited friends, raid roles, main guild, friendly duplicate message) moves over unchanged in behavior, restyled.
2. **Shared spec-guide library (US2)** — introduce a single **global** `spec_guides` store keyed by `(class, spec)`, replacing the per-character guide copies. A new **Class Guides tab** lists the full class/spec roster (from `wcl_agent.constants.CLASS_SPECS`) with per-spec status (ready / generating / failed / not-downloaded), lets any signed-in user **manually request, retry, or refresh** a guide, and view its content. Generation reuses the established off-loop `_generate_text` + `_GUIDE_PROMPT`, is best-effort/non-blocking, deduped by `(class, spec)`, and **rate-limited** (reusing `InProcessRateLimiter`). This fixes the standing "guides stick on `failed` with no retry" defect.
3. **Auto-fetch reconciliation + migration (US3)** — saving a self/friend still auto-triggers its resolved spec's guide, but now via the shared library (reuse if already ready → zero duplicate generation). Existing per-character guide content migrates into `spec_guides`; the agent context preamble (feature 007) and the character read-path derive each character's guide from the shared library by its resolved `(class, spec)`.

The work reuses the spec-resolution + generation machinery (`services/guide.py`), the class/spec SSOT (`constants.CLASS_SPECS`), the rate limiter (`auth/rate_limit.py`), the markdown renderer (`StreamMarkdown`), the auth dependencies, and the migration conventions. The one deliberate deviation from the feature-006 "every data table is tenant-scoped + RLS" convention is the **global `spec_guides` table** — justified below (generic, non-user content; explicit product decision; removes per-user duplication).

## Technical Context

**Language/Version**: Python 3.14 (backend); TypeScript + React 19 (frontend)

**Primary Dependencies**: FastAPI + asyncio, SQLAlchemy 2.x async ORM, Alembic, Pydantic v2; `google-adk`/`google-genai` (guide generation via the existing `stream_response` disposable-session path); React 19 + React Router v7, Vite, Tailwind v4, existing `StreamMarkdown` renderer.

**Storage**: PostgreSQL (asyncpg) prod, SQLite tests. Existing tenant-owned tables keep per-tenant isolation + RLS (feature 006). The **new `spec_guides` table is global** (no `tenant_id`, no RLS) — shared, generic content.

**Testing**: pytest (`backend/tests/`), in-memory SQLite via `conftest.py`. Frontend verified by running the app + `tsc` typecheck (Constitution II).

**Target Platform**: Linux server (uvicorn) + modern desktop browser.

**Project Type**: Web application (FastAPI backend + React frontend) plus the standalone `wcl_agent/` package (class/spec SSOT).

**Performance Goals**: The Class Guides list is O(roster) (~40 specs) merged with existing guide rows in one query. Guide generation runs off the event loop (unchanged), bounded; a spec already `ready` triggers zero regeneration. Manual generation is rate-limited per user.

**Constraints**: Generation stays best-effort and non-blocking; a failed guide MUST be retryable (never permanently stuck). The global library MUST contain only generic guide content — never per-tenant user data. All user-owned data (characters/friends/guild/roles/conversations) stays strictly per-tenant. Additive/zero-regression: existing guides migrate with no user-visible loss.

**Scale/Scope**: Small invite-only user base, single app process. In-process rate limiter + in-flight dedup set are sufficient (no distributed coordination needed).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| **I. Strict DRY & Reuse-First** | PASS — **improves** DRY: one spec-keyed guide store replaces N per-character copies of the same guide. Reuses `_generate_text`/`_GUIDE_PROMPT`, `CLASS_SPECS`, `InProcessRateLimiter`, `StreamMarkdown`, auth deps, and the migration pattern. No parallel generation path. |
| **II. Methodical, Step-Wise Delivery** | PASS — delivered as prioritized, independently-testable slices (US1 page, US2 library+tab, US3 reconcile+migrate); each leaves the app working. |
| **III. Simplicity First (YAGNI)** | PASS — a global table is *simpler* than a per-tenant+RLS one for shared content; in-process dedup/rate-limit (no new infra); no speculative abstraction. The one deviation (global table) is tracked below. |
| **IV. Typed Data Contracts** | PASS — Pydantic models for the guides API (list/detail/generate) and the page/profile bodies; ORM models typed. |
| **V. Async Python Backend** | PASS — new endpoints are `async`; generation stays off the event loop via the existing disposable-session path; list/read are single async queries. |
| **VI. Repo Awareness via GitNexus** | PASS (process) — impact analysis MUST precede edits to the shared symbols `build_preamble`, `run_character_guide`/`schedule_character_guide`, `UserCharacter`, `profile.py` routes, and `ws.py:_handle_turn` (Phase 0 / tasks T001). |

**Result**: PASS — one justified deviation (global `spec_guides` table), recorded in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/008-profile-class-pages/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── guides-api.md            # REST: list / detail / generate (global, shared)
│   ├── profile-page-ui.md       # UI contract: routed page, tabs, theming
│   └── context-and-generation.md# spec-guide generation + preamble reuse
├── checklists/
│   └── requirements.md  # from /speckit-specify
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── api/
│   │   ├── guides.py                 # NEW: GET /api/guides, GET /{class}/{spec}, POST generate
│   │   ├── profile.py                # (unchanged behavior; CharacterOut guide status now derived)
│   │   └── ws.py                     # EDIT: _handle_turn passes spec guides into build_preamble
│   ├── services/
│   │   ├── guide.py                  # EDIT: add spec-keyed ensure/generate; character flow → spec guide
│   │   ├── spec_guides.py            # NEW (optional): roster+status merge, ensure_spec_guide, dedup
│   │   └── profile_context.py        # EDIT: read guides from shared library by (class, spec)
│   ├── db/
│   │   ├── models.py                 # EDIT: + SpecGuide (global); UserCharacter guide columns retired
│   │   └── repository.py             # EDIT: spec-guide upsert/get/list; character guide read via spec
│   ├── auth/rate_limit.py            # REUSE: a guide-generation limiter instance
│   ├── schemas.py                    # EDIT: GuideOut/GuideListOut/GuideStatus; CharacterOut guide fields
│   └── config.py                     # EDIT: wcl_guide_generate_per_minute (rate-limit setting)
├── migrations/versions/
│   ├── 0007_spec_guides.py           # NEW (US2): create spec_guides (global) + backfill; keeps columns
│   └── 0008_drop_character_guide_columns.py  # NEW (US3): drop retired UserCharacter guide columns
└── tests/                            # NEW: spec-guide library, dedup/retry, rate-limit, preamble reuse

wcl_agent/
└── constants.py                      # REUSE: CLASS_SPECS roster (+ SPEC_ROLES) — no change expected

frontend/src/
├── pages/
│   └── ProfilePage.tsx               # NEW: routed, themed, tabbed (Characters + Class Guides)
├── components/
│   ├── profile/CharactersTab.tsx     # NEW: self/friends/guild management (from ProfilePanel)
│   ├── profile/ClassGuidesTab.tsx    # NEW: roster list, status, generate/retry/refresh, view
│   └── ProfilePanel.tsx              # REMOVE/retire (superseded by the page)
├── api/restClient.ts                 # EDIT: listGuides / getGuide / generateGuide (+ reuse profile fns)
├── types.ts                          # EDIT: Guide, GuideStatus, GuideListItem
├── main.tsx                          # EDIT: add guarded /profile route
├── App.tsx                           # EDIT: replace modal open with nav to /profile
└── styles.css / index.css            # EDIT: Warcraft theme tokens + page/tab/button/card styles
```

**Structure Decision**: Web application. The feature spans `backend/app` (new global table + guides API + generation reuse + preamble), the `wcl_agent` package (class/spec SSOT, reused as-is), and `frontend/src` (new routed page + tabs + theme). New files follow existing conventions; two new migrations (`0007_spec_guides` then `0008_drop_character_guide_columns`, split so US2 ships without US3's refactor) follow the `000N_*` sequence after `0006_raid_role`. The profile page is a top-level guarded route (mirroring `/admin/users`).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| **Global (non-tenant, non-RLS) `spec_guides` table** — a deliberate deviation from the feature-006 "every data table is `tenant_id`-scoped + RLS" convention | The user explicitly chose a guide library **shared across all users**; guide content is generic class/spec advice, not user data. A single shared store removes per-user duplication of identical generated content (DRY, Principle I) and model-budget waste. | A per-tenant `spec_guides` table was rejected because it duplicates byte-identical generated guides per user, re-spends the model budget per tenant, and still wouldn't give the requested cross-user sharing. The table holds **no user data**, so the RLS isolation it would add protects nothing. Endpoints still require authentication; mutations require CSRF and are rate-limited. |
