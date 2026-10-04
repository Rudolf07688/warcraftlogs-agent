---
description: "Task list for Profile & Class-Guide Pages — dedicated page, themed, shared spec-guide library"
---

# Tasks: Profile & Class-Guide Pages

**Input**: Design documents from `/specs/008-profile-class-pages/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included — `research.md`/`quickstart.md` specify pytest coverage for the new pure/service functions, the preamble reuse, rate-limiting, and the API. Backend test tasks are per story; the frontend has no automated test harness, so frontend slices are verified by `tsc --noEmit` + running the app (Constitution II).

**Organization**: Grouped by user story (priority order) for independent implementation and testing.

> **Migration split (independence)**: US2's schema lands in `0007_spec_guides` (Foundational — create table + backfill, **keeps** the old per-character guide columns). US3's `0008_drop_character_guide_columns` drops them **inside the US3 phase**, after the read-path derives guides from the shared store — so US2 ships without US3's refactor. Linear history `0006 → 0007 → 0008`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 / US2 / US3 (maps to spec.md)

## Path Conventions

Web app: `backend/app/...`, `backend/migrations/...`, `backend/tests/...`, `wcl_agent/...`, `frontend/src/...` (per plan.md Structure Decision).

> **⚠ Shared-file coordination** (serialize edits if stories run in parallel):
> `backend/app/db/models.py` (T002 ↔ T020), `backend/app/db/repository.py` (T004 ↔ T020),
> `backend/app/services/guide.py` (T011 ↔ T017), `backend/app/schemas.py` (T012 ↔ T018),
> `frontend/src/pages/ProfilePage.tsx` (T006 ↔ T015).

---

## Phase 1: Setup

**Purpose**: Pre-edit safety per the constitution (Principle VI).

- [X] T001 Run GitNexus impact analysis (`impact`/`context`, repo `warcraftlogs-agent`) on the shared hot-path symbols this feature edits — `build_preamble` (`backend/app/services/profile_context.py`), `run_character_guide`/`schedule_character_guide` (`backend/app/services/guide.py`), `UserCharacter` + its guide columns (`backend/app/db/models.py`), the `backend/app/api/profile.py` routes, `CharacterOut` (`backend/app/schemas.py`), and `_handle_turn` (`backend/app/api/ws.py`) — and record the blast radius / risk before any edit. Warn on HIGH/CRITICAL.

---

## Phase 2: Foundational (Blocking Prerequisites for US2 + US3)

**Purpose**: The shared, global spec-guide store + data access. **⚠ No US2/US3 guide work can begin until this is complete.** (US1 is independent and needs none of this.)

- [X] T002 Add `SpecGuide` **global** ORM model (table `spec_guides`: `class_name`, `spec`, `guide_markdown`, `status`, timestamps; `UniqueConstraint(class_name, spec)` → `uq_spec_guide_identity`; **no** `tenant_id`/RLS) per data-model.md §1 in `backend/app/db/models.py` — ⚠ shared file with US3 T020
- [X] T003 Create Alembic migration `backend/migrations/versions/0007_spec_guides.py` (down_revision `0006_raid_role`): create `spec_guides` (global), grant the runtime role `SELECT, INSERT, UPDATE, DELETE` (mirror `0004`), **backfill** one row per distinct `(class_name, active_spec)` from `user_characters` with a `ready` guide (most-recent markdown, deduped), and **keep** the `user_characters` guide columns; `import sqlalchemy as sa`. Verify `upgrade`/`downgrade` round-trips. (depends on T002)
- [X] T004 [P] Add non-tenant repository helpers `get_spec_guide`, `upsert_spec_guide`, `list_spec_guides`, `get_spec_guides_for(pairs)` (per contracts/context-and-generation.md) in `backend/app/db/repository.py` — ⚠ shared file with US3 T020
- [X] T005 [P] Add `wcl_guide_generate_per_minute: int = 10` to `backend/app/config.py` and a module-level `guide_limiter = InProcessRateLimiter(per_minute=settings.wcl_guide_generate_per_minute)` in `backend/app/auth/rate_limit.py`

**Checkpoint**: `uv run alembic -c backend/alembic.ini upgrade head` succeeds; `spec_guides` exists (global) and existing ready guides are backfilled; old columns still present.

---

## Phase 3: User Story 1 — Dedicated, themed Profile page (Priority: P1) 🎯 MVP

**Goal**: Promote the profile from the modal to a routed, Warcraft-themed, tabbed page preserving all current profile capability.

**Independent Test**: Navigate to `/profile`; confirm it's a dedicated themed page with Characters + Class Guides tabs; all self/friends/roles/guild actions work with a friendly duplicate message (quickstart US1; SC-001, SC-007). Independent of the guide backend.

- [X] T006 [US1] Add a guarded top-level `/profile` route in `frontend/src/main.tsx` and create `frontend/src/pages/ProfilePage.tsx` — themed page shell with a tab bar (Characters default, Class Guides) preserving each tab's state on switch — ⚠ shared file with US2 T015
- [X] T007 [US1] Create `frontend/src/components/profile/CharactersTab.tsx` by extracting the self/friends/roles/guild management from `ProfilePanel` (reuse `getProfile`/`putSelf`/`addFriend`/`updateFriend`/`deleteFriend`/`putGuild`/`deleteGuild`; per-character raid-role control; `409 duplicate_friend` → friendly "already added"); render it in the Characters tab
- [X] T008 [US1] In `frontend/src/App.tsx`, replace the profile-modal open with navigation to `/profile` (`useNavigate`) and remove the `ProfilePanel` usage; delete `frontend/src/components/ProfilePanel.tsx`
- [X] T009 [US1] Add Warcraft-themed tokens + page/tab/button/input/select/card styles in `frontend/src/styles.css` (and `index.css` as needed), applied across the page and both tabs (FR-005)
- [X] T010 [US1] Verify US1: `cd frontend && npx tsc --noEmit` passes and the page is exercised per quickstart US1 (manual)

**Checkpoint**: Profile is a dedicated themed page with working Characters tab; Class Guides tab may be a placeholder until US2.

---

## Phase 4: User Story 2 — Class Guides tab + shared spec-guide library (Priority: P1)

**Goal**: List all classes/specs with status; manually request/retry/refresh guides into a shared, deduped, rate-limited library; view content.

**Independent Test**: Class Guides tab lists the full roster with per-spec status; generate a guide for a spec with no character → downloaded + viewable; failed → retryable (never stuck); a second account sees the shared guide (quickstart US2; SC-002/003/005/006).

- [X] T011 [US2] Add `ensure_spec_guide(class_name, spec, *, force=False)` (dedup on ready/pending, retry on failed/force, off-loop generation via existing `_generate_text`/`_GUIDE_PROMPT`, in-flight set re-keyed to `(class, spec)`, `IntegrityError`-safe) and a roster+status merge helper (full `CLASS_SPECS` left-joined to `spec_guides`) in `backend/app/services/guide.py` (or a new `backend/app/services/spec_guides.py`) per contracts/context-and-generation.md (depends on T004) — ⚠ shared file with US3 T017
- [X] T012 [P] [US2] Add guide schemas `GuideStatus`, `GuideListItem`, `GuideListOut`, `GuideOut`, `GuideGenerateIn` to `backend/app/schemas.py` (per contracts/guides-api.md) — ⚠ shared file with US3 T018
- [X] T013 [US2] Create `backend/app/api/guides.py` (`GET /api/guides`, `GET /api/guides/{class_name}/{spec}`, `POST /api/guides/{class_name}/{spec}/generate`) using `require_session`/`require_csrf` + the non-tenant `get_session`; validate `(class,spec)` against `CLASS_SPECS` (404 otherwise); gate generate on `guide_limiter` (429 `rate_limited` + `Retry-After`); register the router in `backend/app/main.py` (depends on T011, T012, T005)
- [X] T014 [P] [US2] Frontend: add `GuideStatus`/`GuideListItem`/`GuideListOut`/`Guide` types in `frontend/src/types.ts` and `listGuides`/`getGuide`/`generateGuide` in `frontend/src/api/restClient.ts`
- [X] T015 [US2] Create `frontend/src/components/profile/ClassGuidesTab.tsx` (roster grouped by class; per-spec status chip ready/pending/failed/none; Generate/Retry/Refresh → `generateGuide`; View → `getGuide` rendered via existing `StreamMarkdown`; poll `listGuides` while any pending; `429` → "slow down" message) and wire it into the Class Guides tab of `ProfilePage.tsx` (depends on T006, T014) — ⚠ shared file with US1 T006
- [X] T016 [P] [US2] Tests in `backend/tests/test_spec_guides.py`: `ensure_spec_guide` dedup (ready/pending no-op), retry/force regeneration, `IntegrityError` convergence; roster+status merge covers 100% of specs; rate-limit gating returns 429; API list/detail/generate happy + 404 for unknown spec (genai generation mocked)

**Checkpoint**: Class Guides tab fully functional; failures retryable; library shared and deduped.

---

## Phase 5: User Story 3 — Auto-fetch reconciliation + migrate-drop (Priority: P2)

**Goal**: Characters derive their guide from the shared library; auto-fetch on add reuses it (zero duplicate generation); retired per-character guide columns removed.

**Independent Test**: Add a friend whose spec guide is ready → attaches with zero new generation; preamble/agent context still includes the guide; empty library + unresolved spec ⇒ preamble byte-identical; removing a character keeps the shared guide (quickstart US3; SC-004).

- [X] T017 [US3] Refactor `run_character_guide` in `backend/app/services/guide.py` to resolve `(class, spec)`, persist `class_name`/`active_spec` on the character, then call `ensure_spec_guide(class, spec)` — no per-character markdown writes (depends on T011; ⚠ same file as T011 — after it)
- [X] T018 [US3] Make `CharacterOut.guide_status`/`guide_updated_at` **derived** from the character's spec guide, and batch-load spec guides in `GET /api/profile` to populate them, in `backend/app/schemas.py` + `backend/app/api/profile.py` (⚠ schemas.py shared with US2 T012 — after it)
- [X] T019 [US3] Extend `build_preamble` in `backend/app/services/profile_context.py` to take a `spec_guides: dict[(class,spec)->markdown]` map and inject guide-by-spec (reuse existing `_PER_GUIDE_CHARS`/`_TOTAL_GUIDE_CHARS` caps; empty/unresolved ⇒ byte-identical), and in `backend/app/api/ws.py` `_handle_turn` fetch `get_spec_guides_for(...)` for the profile characters' specs and pass it in
- [X] T020 [US3] Remove the retired `guide_markdown`/`guide_status`/`guide_updated_at` columns from `UserCharacter` in `backend/app/db/models.py` and clean up `set_character_guide`'s markdown/status writes in `backend/app/db/repository.py` (⚠ shared files with T002/T004 — after them)
- [X] T021 [US3] Create Alembic migration `backend/migrations/versions/0008_drop_character_guide_columns.py` (down_revision `0007_spec_guides`): drop the three columns; downgrade re-adds them nullable; `import sqlalchemy as sa`. Verify `upgrade`/`downgrade` round-trips. (depends on T017–T020 landed)
- [X] T022 [P] [US3] Tests in `backend/tests/test_profile_context.py` + `backend/tests/test_guide_reconcile.py`: `build_preamble` guide-by-spec reuse + empty-state byte-equality; derived `CharacterOut` guide status; auto-fetch reuse performs zero regeneration when the spec guide is ready; removing a character leaves the shared `spec_guides` row intact

**Checkpoint**: Single source of truth for guides; all four behaviors above hold; schema cleaned.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T023 [P] Update `documentation/ai_guide.md` (and `README.md` if it documents profile/guide behavior) for the dedicated profile page, the shared spec-guide library + `/api/guides`, and migrations `0007`/`0008`
- [X] T024 Run GitNexus `detect_changes --scope all` (and `--scope compare --base-ref main`) to confirm only expected symbols/flows changed — before committing
- [ ] T025 Run `quickstart.md` manual validation for all three stories (incl. migration/no-regression: backfilled guides appear; empty library ⇒ preamble unchanged)
- [X] T026 [P] Run the backend suite `uv run pytest backend/tests -k "guide or spec_guide or preamble or profile or rate"` and `cd frontend && npx tsc --noEmit`

---

## Dependencies & Execution Order

### Phase dependencies
- **Setup (T001)** → first (impact-analysis gate).
- **Foundational (T002–T005)** → after Setup; **blocks US2 + US3** (not US1). T002 → T003; T004 needs T002; T005 independent.
- **US1 (T006–T010)** → after Setup; **independent of Foundational** and of US2/US3.
- **US2 (T011–T016)** → after Foundational. T011 → T013; T015 needs T006 + T014.
- **US3 (T017–T022)** → after US2 (reuses `ensure_spec_guide`) and Foundational. T021 after T017–T020.
- **Polish (T023–T026)** → after all desired stories.

### User-story dependencies
- **US1 (P1)**: independent. **MVP** candidate on its own (page + themed Characters tab).
- **US2 (P1)**: needs Foundational. Independent of US1 behavior (shares only `ProfilePage.tsx`).
- **US3 (P2)**: depends on US2's `ensure_spec_guide`; shares `models.py`/`repository.py`/`guide.py`/`schemas.py` with Foundational/US2 — serialize those edits.

### Parallel opportunities
- After Setup, **US1 can run fully in parallel with Foundational + US2** (frontend-only page; the Class Guides tab is wired in T015 once US2 types exist).
- `[P]` within/after phases: T004/T005; T012/T014/T016; T022; T023/T026.

---

## Implementation Strategy

### MVP
1. Setup (T001) → **US1 (T006–T010)**: a dedicated, themed profile page is an immediate, shippable win.
2. Then **Foundational (T002–T005) → US2 (T011–T016)**: the shared Class Guides library (the headline ask + the retry fix).
3. **STOP & VALIDATE** per quickstart US1/US2.

### Incremental delivery
1. **US1** (page) — independent UI win.
2. **US2** (shared library + Class Guides tab) — headline capability; fixes the stuck-guide defect via retry + rate limit.
3. **US3** (reconcile + `0008` column drop) — single-source cleanup; migrate-drop last so nothing ever reads a dropped column.

---

## Notes
- `[P]` = different files, no incomplete-task dependency. Respect the ⚠ shared-file flags.
- The `spec_guides` table is **global** (no tenant scope) by design (plan Complexity Tracking); endpoints still require auth, mutations require CSRF + rate limit; **no user data** may enter the table.
- Guide generation stays best-effort/non-blocking; `failed` is always retryable (never permanently stuck).
- Additive/no-regression: empty library + unresolved specs reproduce today's agent-context behavior; backfill preserves existing guides.
- Run `detect_changes` before committing (T024) per the constitution.
