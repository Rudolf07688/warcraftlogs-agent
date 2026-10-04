---
description: "Task list for Captured-Metadata Reuse, Findings-Based Reports & Role-Aware Profiles"
---

# Tasks: Captured-Metadata Reuse, Findings-Based Reports & Role-Aware Profiles

**Input**: Design documents from `/specs/007-metadata-reports-profiles/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included — the project runs pytest and `research.md`/`quickstart.md` specify unit coverage for the new pure functions, the preamble empty-state, and the synthesis failure paths. Test tasks are per story; they need not precede implementation (the suite is not strict TDD).

**Organization**: Grouped by user story (priority order) for independent implementation and testing.

> **Migration split (independence)**: US1's schema (new tables) lands in migration `0005_known_entities` (Foundational, blocks US1). US4's schema (`raid_role` column) lands in its own migration `0006_raid_role` **inside the US4 phase**, so US1 can ship as the MVP without any US4 schema. Alembic history is linear, so `0006` chains after `0005` (apply order only; no behavioral coupling).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 / US2 / US3 / US4 (maps to spec.md)

## Path Conventions

Web app: `backend/app/...`, `backend/migrations/...`, `backend/tests/...`, `wcl_agent/...`, `frontend/src/...` (per plan.md Structure Decision).

> **⚠ Shared-file coordination**: US1 and US4 both edit `backend/app/db/models.py`, `backend/app/db/repository.py`, and `backend/app/services/profile_context.py`; US2 and US3 both edit `backend/app/api/reports.py`. These are flagged below and are NOT `[P]` across stories. If stories run in parallel, serialize edits to those files.

---

## Phase 1: Setup

**Purpose**: Pre-edit safety per the project constitution (Principle VI).

- [X] T001 Run GitNexus impact analysis (`impact`/`context`) on the shared hot-path symbols this feature edits — `_handle_tool_end` (`backend/app/api/ws.py`), `build_preamble` (`backend/app/services/profile_context.py`), `render_report_pdf` + both endpoints in `backend/app/api/reports.py`, `UserCharacter` (`backend/app/db/models.py`), and the `backend/app/api/profile.py` routes — and record the blast radius / risk before any edit. Warn on HIGH/CRITICAL.

---

## Phase 2: Foundational (Blocking Prerequisites for US1)

**Purpose**: US1's new per-tenant tables. **⚠ No US1 data work can begin until this phase is complete.** (US2/US3 need no migration; US4 carries its own migration in its phase.)

- [X] T002 Add `KnownPlayer` and `KnownEncounter` ORM models (per data-model.md §1–§2: `tenant_id` FK cascade, identity `UniqueConstraint`, `(tenant_id, last_seen_at)` index) in `backend/app/db/models.py` — ⚠ shared file with US4 T016
- [X] T003 Create Alembic migration `backend/migrations/versions/0005_known_entities.py` (down_revision `0004_rls`): create `known_players` + `known_encounters`, enable RLS + tenant policy on both, grant the runtime role privileges (mirror `0004_rls`); include `import sqlalchemy as sa`. Verify `uv run alembic upgrade head` then `downgrade` round-trips. (depends on T002)

**Checkpoint**: `uv run alembic upgrade head` succeeds; the two new tables exist with RLS.

---

## Phase 3: User Story 1 — Captured-metadata reuse across conversations (Priority: P1) 🎯 MVP

**Goal**: Capture known players/encounters from successful tool calls into durable per-tenant stores and surface known raids/players/encounters/guilds into the agent's context across a user's conversations.

**Independent Test**: Capture a report/player/boss in one chat; in a new chat reference them loosely → the assistant resolves them and a repeat known-raid reference issues **zero** report-metadata lookups; a second account sees none of it (quickstart US1; SC-002).

- [X] T004 [P] [US1] Add repository helpers `upsert_known_player`, `upsert_known_encounter`, `list_recent_known_players`, `list_recent_known_encounters`, `list_recent_known_guilds` (derived from `TrackedRaid.guild`) in `backend/app/db/repository.py` (per contracts/capture-and-context.md) — ⚠ shared file with US4 T020
- [X] T005 [P] [US1] Create `backend/app/services/known_entities.py` with pure extractors (`players_from_tool`, `encounters_from_find`) and best-effort `capture_players_from_tool` / `capture_encounters_from_tool` (signatures per contracts/capture-and-context.md; sources: `get_character_zone_rankings`/`get_character_encounter_rankings`/`get_report_master_data` for players, `find_encounter` for encounters; skip incomplete identities and name-only encounter matches lacking a stable id; never raise) (depends on T004)
- [X] T006 [US1] Wire `capture_players_from_tool` + `capture_encounters_from_tool` into `_handle_tool_end` alongside the existing captures, and include their results in the commit-and-rescope guard, in `backend/app/api/ws.py` (depends on T005)
- [X] T007 [US1] Extend `build_preamble` in `backend/app/services/profile_context.py` to accept capped `known_raids/known_players/known_encounters/known_guilds` and append a bounded `RECENTLY SEEN (this account)` section (new cap constants; dedup players vs profile; empty inputs ⇒ byte-identical output) — ⚠ shared file with US4 T022
- [X] T008 [US1] In `_handle_turn` (`backend/app/api/ws.py`), fetch the recency-capped known raids/players/encounters/guilds for the tenant and pass them to `build_preamble` (depends on T004, T007; same file as T006 — after T006)
- [X] T009 [P] [US1] Tests in `backend/tests/test_known_entities.py` and `backend/tests/test_profile_context.py`: extractor dedup/skip rules (incl. name-only encounter skip); `build_preamble` empty-state byte-equality and char-cap bound; per-tenant isolation of recency queries; a repeat known-raid reference performs no new report-metadata lookup (SC-002)

**Checkpoint**: US1 independently testable and shippable as the MVP (no US4 schema required).

---

## Phase 4: User Story 2 — Conversation-level findings report (Priority: P1)

**Goal**: The conversation PDF body is an analytic findings synthesis (not the transcript), with charts still attached.

**Independent Test**: Download a multi-turn analysis conversation's report → body is organized by findings/topic with Key Findings + per-boss results + recommendations; chit-chat → "no substantive findings"; synthesis failure → 500, no file (quickstart US2).

- [X] T010 [P] [US2] Add `wcl_report_model: str = "gemini-3.6-flash"` setting to `backend/app/config.py`
- [X] T011 [US2] Create `backend/app/services/report_synthesis.py` with `async synthesize_findings(messages, *, scope, question=None) -> str` (one-shot `genai` via `asyncio.to_thread`, no web search, `asyncio.wait_for` timeout, oldest-first input char-cap, findings-oriented prompt that emits a short "no substantive findings" doc when none; markdown limited to renderer-supported constructs) per contracts/reports-api.md (depends on T010)
- [X] T012 [US2] Add shared `_synthesize_and_render(...)` helper and wire the conversation endpoint `GET /{conv_id}/report.pdf` to synthesize then render the result as a single synthetic agent message (graphs/artifacts + title unchanged) in `backend/app/api/reports.py` (depends on T011) — ⚠ shared file with US3 T014
- [X] T013 [P] [US2] Tests in `backend/tests/test_report_synthesis.py`: mocked-genai happy path produces markdown; empty model output ⇒ no-findings doc; exception/timeout ⇒ propagates to `500` (no partial file)

**Checkpoint**: Conversation reports render synthesized findings; failures fail closed.

---

## Phase 5: User Story 3 — Per-message findings report (Priority: P2)

**Goal**: Same findings synthesis scoped to one agent reply (+ its originating question for context), only that reply's charts.

**Independent Test**: Use a reply's ⬇ Report → PDF synthesizes only that reply's findings, excludes other messages, includes only its charts (quickstart US3).

- [X] T014 [US3] Wire the per-message endpoint `GET /{conv_id}/messages/{message_id}/report.pdf` through the shared `_synthesize_and_render(...)` helper, passing the originating user question as `question` context, in `backend/app/api/reports.py` (depends on T012)
- [X] T015 [P] [US3] Test in `backend/tests/test_reports_message.py`: per-message slice synthesized in isolation; only `message_seq`-matched charts attached; other replies excluded

**Checkpoint**: Both report scopes share one synthesize→render pipeline.

---

## Phase 6: User Story 4 — Role-aware profile: multiple friends + raid roles (Priority: P2)

**Goal**: Confirm multi-friend; add an optional per-character raid role (user override) defaulted from the resolved spec, surfaced in UI and agent context. **Self-contained schema** (own migration) so it is independently deliverable.

**Independent Test**: Add ≥3 friends (friendly duplicate message on re-add); inferred role shows from spec; override via UI persists over the default across reload; invalid role ⇒ 422; role appears in the preamble (quickstart US4).

- [X] T016 [US4] Add nullable `raid_role` column (`String(10)`, values `tank|healer|dps|null`) to `UserCharacter` in `backend/app/db/models.py` (⚠ shared file with US1 T002 — serialize)
- [X] T017 [US4] Create Alembic migration `backend/migrations/versions/0006_raid_role.py` (down_revision `0005_known_entities`): `add_column("user_characters", raid_role nullable)`; no backfill; `import sqlalchemy as sa`. Verify `upgrade`/`downgrade` round-trips. (depends on T016)
- [X] T018 [P] [US4] Add `SPEC_ROLES` map + `role_for_spec(spec) -> str | None` (tanks/healers enumerated, else `dps`, unknown/None ⇒ None) in `wcl_agent/constants.py` (SSOT, per contracts/capture-and-context.md)
- [X] T019 [P] [US4] Extend schemas in `backend/app/schemas.py`: add optional `raid_role: Literal["tank","healer","dps"] | None` to `CharacterIn`; add `raid_role` + computed `effective_role` to `CharacterOut`; add `FriendPatchIn`
- [X] T020 [US4] Thread `raid_role` through `upsert_self`/`add_friend` and add `update_friend_role(session, char_id, *, tenant_id, raid_role)` in `backend/app/db/repository.py` (depends on T017; ⚠ shared file with US1 T004 — serialize)
- [X] T021 [US4] Accept `raid_role` on `PUT /self` and `POST /friends`, populate `effective_role` (via `role_for_spec`) in responses, and add `PATCH /api/profile/friends/{char_id}` (body `FriendPatchIn`, in-place update, `commit_and_rescope`, `404` when not a tenant friend) in `backend/app/api/profile.py` (depends on T018, T019, T020)
- [X] T022 [US4] Extend `_ident` in `backend/app/services/profile_context.py` to append the effective raid role (`role_for_spec(active_spec)` unless overridden) in the existing `" — "` style; unset ⇒ byte-identical to today (depends on T018; ⚠ shared file with US1 T007 — after T007)
- [X] T023 [P] [US4] Frontend: add a raid-role select per character in `frontend/src/components/ProfilePanel.tsx` (indicate inferred vs set) + map the `409 duplicate_friend` to a friendly "already added" message; extend `Character`/`CharacterInput` with `raid_role`/`effective_role` in `frontend/src/types.ts`; add `updateFriend` (PATCH) and pass `raid_role` in `frontend/src/api/restClient.ts`
- [X] T024 [P] [US4] Tests in `backend/tests/test_roles.py`: `role_for_spec` mapping (tank/healer/dps/unknown); `PATCH /friends/{id}` in-place + clear-to-null; invalid role ⇒ 422; `effective_role` = override-or-inferred; duplicate friend still 409

**Checkpoint**: All four stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T025 [P] Update `documentation/ai_guide.md` / `README.md` if they document report behavior, profile roles, or agent context (keep consistent with the constitution)
- [X] T026 Run GitNexus `detect_changes --scope all` (and `--scope compare --base-ref main`) to confirm only expected symbols/flows changed — before committing
- [ ] T027 ⏳ (manual — needs a running app + live WCL/Vertex) Run `quickstart.md` manual validation for all four stories (incl. SC-008 no-regression with empty metadata + unset roles)
- [X] T028 [P] Run the backend suite: `uv run pytest backend/tests -k "known or preamble or synthesis or role or friend or reports"`

---

## Dependencies & Execution Order

### Phase dependencies
- **Setup (T001)** → no deps; do first (impact analysis gate).
- **Foundational (T002–T003)** → after Setup; **blocks US1 only** (new tables).
- **US1 (T004–T009)** → after Foundational.
- **US2 (T010–T013)** → independent of any migration; can start right after Setup.
- **US3 (T014–T015)** → depends on **US2 T012** (shared `_synthesize_and_render`).
- **US4 (T016–T024)** → self-contained (own model + migration `0006`); no dependency on US1/US2/US3 behavior.
- **Polish (T025–T028)** → after all desired stories.

### User-story dependencies
- **US1 (P1)**: needs Foundational tables. Independent of other stories. **MVP.**
- **US2 (P1)**: independent of all migrations. Independent of US1.
- **US3 (P2)**: depends on US2 T012.
- **US4 (P2)**: independent story with its own schema (T016–T017). Shares files with US1 (`models.py` T002↔T016, `repository.py` T004↔T020, `profile_context.py` T007↔T022) — serialize those edits if run in parallel. Note `0006` chains after `0005` in alembic history (apply-order only).

### Within a story
- US1: T004 → T005 → T006 → T008; T007 → T008; T009 [P].
- US2: T010 → T011 → T012; T013 [P].
- US3: T012 → T014; T015 [P].
- US4: T016 → T017; T018/T019/T020 → T021; T018(+T007) → T022; T023/T024 [P].

### Parallel opportunities
- After Setup, **US2 can run in parallel with Foundational** (no migration dependency).
- **US4 is fully independent** of US1/US2/US3 (own schema) — can run anytime after Setup, serializing only the three shared files with US1.
- `[P]` within stories: T009, T013, T015, T023, T024, T025, T028 (distinct files).

---

## Parallel Example: after Setup

```bash
# US2 (no migration dep) and US4's standalone pieces can start immediately:
Task: "T011 report_synthesis.synthesize_findings in backend/app/services/report_synthesis.py"
Task: "T018 SPEC_ROLES + role_for_spec in wcl_agent/constants.py"
Task: "T019 profile schemas in backend/app/schemas.py"

# Once T002–T003 land, start US1's standalone pieces:
Task: "T005 known_entities extractors in backend/app/services/known_entities.py"
```

---

## Implementation Strategy

### MVP (US1 only)
1. Setup (T001) → Foundational (T002–T003) → US1 (T004–T009).
2. **STOP & VALIDATE**: capture in one chat, reuse in another (zero report-metadata lookup on repeat), confirm isolation (quickstart US1). Deploy/demo. **No US4 schema is pulled in by the MVP.**

### Incremental delivery
1. Foundation ready → **US1** (captured-metadata reuse) = MVP.
2. **US2** (conversation findings report) — high value, independent of the migration.
3. **US3** (per-message findings report) — builds on US2's pipeline.
4. **US4** (role-aware profile) — self-contained schema; coordinate shared-file edits with US1.
5. Each story ships without breaking the others; SC-008 (no-regression on empty state) verified at each checkpoint.

---

## Notes
- `[P]` = different files, no incomplete-task dependency. Respect the ⚠ shared-file flags across US1/US4 and US2/US3.
- Every new table/read is tenant-scoped; captures stay best-effort (never block a turn); synthesis stays fail-closed (never a partial PDF).
- Additive everywhere: empty metadata store + unset roles must reproduce today's behavior (SC-008).
- Run `detect_changes` before committing (T026) per the project constitution.
