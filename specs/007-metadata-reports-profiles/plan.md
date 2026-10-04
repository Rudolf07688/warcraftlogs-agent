# Implementation Plan: Captured-Metadata Reuse, Findings-Based Reports & Role-Aware Profiles

**Branch**: `007-metadata-reports-profiles` | **Date**: 2026-10-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-metadata-reports-profiles/spec.md`

## Summary

Phase 5 refines three already-shipped capabilities, each as an additive slice:

1. **Captured-metadata reuse (US1)** — the app already captures "known raids" (`TrackedRaid`) from successful tool calls but never feeds them back to the agent. Close the loop: broaden capture to **known players** and **known zones/encounters** (new per-tenant tables), derive **known guilds** from existing raids, and extend the single `build_preamble` context block with a bounded "recently seen (this account)" section so follow-ups across a user's conversations benefit without re-querying Warcraft Logs.
2. **Findings-based reports (US2/US3)** — the PDF export currently renders the transcript. Insert one LLM synthesis step (reusing the established off-event-loop, fail-closed `google-genai` one-shot pattern from `suggestions.py`) that turns the in-scope messages into an analytic findings document; feed that markdown into the existing `render_report_pdf` renderer unchanged. Conversation-level and per-message reports share one synthesize→render pipeline.
3. **Role-aware profile (US4)** — multiple friends already work (verify + surface the duplicate-friend message in the UI). Add a per-character **raid role** (Tank/Healer/DPS) as a nullable override column on `UserCharacter`, defaulted from the resolved spec via a new `SPEC_ROLES` map (single source of truth in `wcl_agent/constants.py`), user-overridable via a new friends PATCH endpoint and the existing self upsert, and injected into the preamble per character.

The work reuses the existing capture hub (`_handle_tool_end`), the context preamble (`profile_context.build_preamble`), the PDF renderer (`render_report_pdf`), the profile REST/repository layer, and the WCL spec-resolution precedent (`guide._resolve_active_spec_sync`). Two Alembic migrations keep the stories independently deliverable: `0005_known_entities` (US1 tables) and `0006_raid_role` (US4 column).

## Technical Context

**Language/Version**: Python 3.14 (backend); TypeScript + React 19 (frontend)

**Primary Dependencies**: FastAPI + asyncio, SQLAlchemy 2.x async ORM, Alembic, Pydantic v2; `google-genai` / `google-adk` (Gemini) for LLM synthesis; reportlab + matplotlib (PDF); Vite + Tailwind v4, react-plotly.js (frontend)

**Storage**: PostgreSQL (asyncpg) in production, SQLite for tests; per-tenant isolation via app predicate + Postgres RLS (`app.tenant_id`, feature 006). New tables carry `tenant_id` and the same RLS/scoping treatment.

**Testing**: pytest (backend; existing suites under `backend/tests/`, e.g. `test_wcl_cache.py`). Frontend changes are thin and verified by running the app (Constitution Principle II).

**Target Platform**: Linux server (uvicorn) + modern browser

**Project Type**: Web application (FastAPI backend + React frontend) plus the standalone `wcl_agent/` analyst package.

**Performance Goals**: Preamble metadata block stays within a fixed character budget regardless of history (recency-capped). Report synthesis runs off the request event loop with a bounded timeout (~60 s) and a bounded input size; a single download triggers at most one LLM call.

**Constraints**: Strict per-tenant isolation — no captured entity may cross tenants (RLS + `tenant_id` scoping, mirrored on new tables). Metadata capture is best-effort and MUST never block or fail a turn. Synthesis is fail-closed: never return a partial/misleading PDF. All additions are additive — empty metadata store and unset roles reproduce today's behavior byte-for-byte.

**Scale/Scope**: Small, invite-only user base (founder + friends), single app process; in-process WCL result cache remains as-is (the new durable metadata store is a complementary layer).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| **I. Strict DRY & Reuse-First** | PASS — extends the single capture hub, the single preamble builder, the single PDF renderer, the profile repository, and reuses `constants.CLASS_SPECS`/`guide` spec-resolution. No parallel implementations; `SPEC_ROLES` is a new single source of truth for spec→role. Known guilds are **derived** from `TrackedRaid` rather than a duplicate store. |
| **II. Methodical, Step-Wise Delivery** | PASS — delivered as independent, testable slices aligned to the spec's prioritized user stories (US1 P1, US2 P1, US3 P2, US4 P2); each leaves the app working. |
| **III. Simplicity First (YAGNI)** | PASS — no synthesis caching (per-download), no known-guild table (derived), spec→role is a small static dict, one migration. No speculative abstraction. |
| **IV. Typed Data Contracts** | PASS — Pydantic models for all new/extended API bodies (`CharacterIn/Out`, friends PATCH, report flow); capture extractors return typed values; ORM models are typed. |
| **V. Async Python Backend** | PASS — captures are async off the tool-success hub; LLM synthesis and WCL spec resolution run via `asyncio.to_thread`/disposable session; no blocking on the event loop. |
| **VI. Repo Awareness via GitNexus** | PASS (process) — impact analysis MUST be run before editing the shared symbols `_handle_tool_end`, `build_preamble`, `render_report_pdf`/`reports.py` endpoints, `UserCharacter`, and `profile.py` (see Phase 0). |

**Result**: PASS — no violations; Complexity Tracking table left empty.

## Project Structure

### Documentation (this feature)

```text
specs/007-metadata-reports-profiles/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (REST + internal service contracts)
│   ├── profile-api.md
│   ├── reports-api.md
│   └── capture-and-context.md
├── checklists/
│   └── requirements.md  # from /speckit-specify
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── api/
│   │   ├── ws.py                     # EDIT: _handle_tool_end → add player/encounter capture calls
│   │   ├── profile.py                # EDIT: accept raid_role on self/friend; ADD PATCH /friends/{id}
│   │   └── reports.py                # EDIT: both endpoints → synthesize findings before render
│   ├── services/
│   │   ├── raids.py                  # reference pattern (unchanged)
│   │   ├── known_entities.py         # NEW: capture_players_from_tool / capture_encounters_from_tool
│   │   ├── profile_context.py        # EDIT: build_preamble → captured-metadata section + raid role
│   │   ├── report_synthesis.py       # NEW: synthesize_findings(messages, scope) → markdown
│   │   └── pdf_report.py             # unchanged (renders synthesized markdown as body)
│   ├── db/
│   │   ├── models.py                 # EDIT: UserCharacter.raid_role; ADD KnownPlayer, KnownEncounter
│   │   └── repository.py             # EDIT: profile helpers; ADD known-entity + friend-update helpers
│   ├── schemas.py                    # EDIT: CharacterIn/Out raid_role + effective_role; FriendPatchIn
│   └── config.py                     # EDIT: add wcl_report_model setting
├── migrations/versions/
│   ├── 0005_known_entities.py        # NEW (US1): +known_players, +known_encounters (+RLS)
│   └── 0006_raid_role.py             # NEW (US4): +user_characters.raid_role (nullable)
└── tests/                            # NEW: capture, preamble, synthesis, role-inference, PATCH tests

wcl_agent/
└── constants.py                      # EDIT: add SPEC_ROLES map + role_for_spec() helper (SSOT)

frontend/src/
├── components/ProfilePanel.tsx       # EDIT: role select per character; friendly duplicate message
├── types.ts                          # EDIT: Character/CharacterInput raid_role + effective_role
└── api/restClient.ts                 # EDIT: pass raid_role; add updateFriend (PATCH)
```

**Structure Decision**: Web application (Option 2). The feature spans the existing `backend/app` (FastAPI services/db/api), the standalone `wcl_agent` package (spec→role constants), and the React `frontend/src`. All changes extend existing modules; two new backend files (`known_entities.py`, `report_synthesis.py`) follow the established service-module convention, and two new migrations follow the `000N_*` sequence after `0004_rls` (`0005_known_entities` → `0006_raid_role`).

## Complexity Tracking

> No constitution violations — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
