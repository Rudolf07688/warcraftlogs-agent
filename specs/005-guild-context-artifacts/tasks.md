---
description: "Task list for feature 005 — Personalized Guild Context, Interactive Artifacts & Faster Analysis"
---

# Tasks: Personalized Guild Context, Interactive Artifacts & Faster Analysis

**Input**: Design documents from `/specs/005-guild-context-artifacts/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (all present)

**Tests**: Backend pytest tasks are included per story (the plan lists new test files and the repo has an
established suite). Frontend/UI slices are verified via `quickstart.md` (no frontend test harness).

**Organization**: Tasks are grouped by user story. Stories are independently implementable/testable.
US1, US2, US3 are all **P1**; US1 is the suggested MVP (personalization backbone the others lean on).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US6 (setup/foundational/polish have no story label)

## Path Conventions

Web app layout: `wcl_agent/` (ADK agent + WCL client, standalone), `backend/app/` (FastAPI),
`frontend/src/` (React/Vite). Tests in `backend/tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencies and configuration for the feature.

- [X] T001 [P] Add backend `plotly` dependency (`uv add plotly`); confirm `pyproject.toml` + `uv.lock` updated
- [X] T002 [P] Add frontend deps in `frontend/package.json` and install: `react-plotly.js`, `plotly.js-dist-min`, `katex`, `remark-math`, `rehype-katex` (`cd frontend && npm install`)
- [X] T003 [P] Add settings to `backend/app/config.py` (`wcl_guide_model` default `gemini-3.6-flash`; optional `wcl_cache_ttl_report_s`, `wcl_cache_ttl_leaderboard_s`) and document them in `.env.example`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared DB tables + the turn-end capture-linkage helper that US1/US2/US5/US6 build on.

**⚠️ CRITICAL**: Complete before starting any user story.

- [X] T004 Add ORM models `UserCharacter`, `GuildProfile`, `Artifact` to `backend/app/db/models.py` (reuse `_JSON`/`_UUID` dual-dialect helpers; follow `CapturedGraph`/`TrackedRaid` patterns per data-model.md)
- [X] T005 Ensure the three new tables are created at startup via `Base.metadata.create_all` in `backend/app/main.py` lifespan (verify model imports; additive/idempotent, SQLite-safe for tests)
- [X] T006 [P] Add `assign_message_seq_to_turn_captures(session, conv_id, seq)` to `backend/app/db/repository.py` — set `message_seq=seq` on this conversation's `message_seq IS NULL` `Artifact` and `CapturedGraph` rows (shared by US2 + US5)

**Checkpoint**: Schema + capture-linkage ready — user stories can begin.

---

## Phase 3: User Story 1 - Personal, friend & guild context (Priority: P1) 🎯 MVP

**Goal**: A single global profile (self, friends, one main guild) that Barnaby uses as standing context,
scoping self/friend/guild-referential questions to the saved identities (agent-inferred) while answering
population-level questions normally.

**Independent Test**: Add self + a friend + a main guild; "how are my parses?" / "how is our guild doing?"
resolve to saved identities without retyping; a population question is not narrowed; clearing the profile
leaves all behavior unchanged.

### Tests for User Story 1

- [X] T007 [P] [US1] `backend/tests/test_profile.py` — profile CRUD, single-`self` enforcement, one-main-guild replacement (FR-002/003)
- [X] T008 [P] [US1] `backend/tests/test_profile_context.py` — preamble built from a profile; empty when no profile (FR-006); includes scoping rule + capped guides

### Implementation for User Story 1

- [X] T009 [P] [US1] Add `CharacterIn`, `CharacterOut`, `GuildIn`, `GuildOut`, `ProfileOut` to `backend/app/schemas.py` (per contracts/rest.md)
- [X] T010 [US1] Add profile repository functions to `backend/app/db/repository.py`: `get_profile`, `upsert_self`, `add_friend`, `delete_friend`, `set_guild`, `delete_guild` (enforce single self row + single guild)
- [X] T011 [P] [US1] Create `backend/app/services/profile_context.py` — `build_preamble(profile)` producing the capped "KNOWN PLAYER CONTEXT" block (data-model.md); returns "" when empty
- [X] T012 [US1] Add optional `context_preamble` param to `stream_response` in `backend/app/agent_runner.py`, prepended to the model `Content` only (never persisted/shown)
- [X] T013 [US1] In `backend/app/api/ws.py` `_handle_turn`, load the profile and pass `build_preamble(...)` into `stream_response` (persist only `turn.content`)
- [X] T014 [US1] Append the "KNOWN PLAYER CONTEXT" usage section to `INSTRUCTION` in `wcl_agent/agent.py` (scoping rule per contracts/agent-tools.md)
- [X] T015 [US1] Create `backend/app/api/profile.py` router: `GET /api/profile`, `PUT /api/profile/self`, `POST /api/profile/friends`, `DELETE /api/profile/friends/{id}`, `PUT /api/profile/guild`, `DELETE /api/profile/guild`
- [X] T016 [US1] Mount the profile router in `backend/app/main.py`
- [X] T017 [P] [US1] Add `Character`, `Guild`, `Profile` types to `frontend/src/types.ts` and profile CRUD calls to `frontend/src/api/restClient.ts`
- [X] T018 [US1] Create `frontend/src/components/ProfilePanel.tsx` (edit self/friends/guild; show `guide_status`)
- [X] T019 [US1] Wire the Profile panel entry point into `frontend/src/components/Sidebar.tsx` and load/open it from `frontend/src/App.tsx`

**Checkpoint**: Profile is editable and demonstrably steers answers; MVP shippable.

---

## Phase 4: User Story 2 - Interactive plots & artifacts (Priority: P1)

**Goal**: Barnaby declares charts via `create_chart`; the backend renders them to interactive Plotly
figures inline, persists the chart spec, and re-renders on reload.

**Independent Test**: Ask for a DPS-over-time plot or a spec comparison → an interactive chart renders
inline (hover/zoom); no broken chart mid-stream; reopening the conversation re-renders it.

### Tests for User Story 2

- [X] T020 [P] [US2] `backend/tests/test_charts.py` — `chart_spec_to_plotly` and `chart_spec_to_matplotlib` from a ChartSpec; validation/bounds
- [X] T021 [P] [US2] `backend/tests/test_artifacts.py` — `create_chart` tool result captured + persisted; `GET /api/conversations/{id}` returns artifacts mapped to `message_seq`

### Implementation for User Story 2

- [X] T022 [P] [US2] Add `create_chart` tool to `wcl_agent/tools.py` (validate `kind`/`series_json`/bounds; return normalized `ChartSpec`; no plotly dep) per contracts/agent-tools.md
- [X] T023 [US2] Register `create_chart` in `wcl_agent/agent.py` `TOOLS` and append the "CHARTS" INSTRUCTION section
- [X] T024 [P] [US2] Add `ChartSpec`, `ArtifactOut`, `ArtifactFrame` to `backend/app/schemas.py` (per contracts/)
- [X] T025 [P] [US2] Create `backend/app/services/charts.py` — `chart_spec_to_plotly(spec)` → `{data,layout}` and `chart_spec_to_matplotlib(spec)` → ReportLab `Image` (bound points/series)
- [X] T026 [US2] Add `add_artifact` + `list_artifacts` to `backend/app/db/repository.py`
- [X] T027 [US2] Create `backend/app/services/artifacts.py` — `capture_artifact_from_tool(name, ok, result)` validating the `create_chart` payload into a `ChartSpec`
- [X] T028 [US2] In `backend/app/api/ws.py` `_handle_tool_end`, on successful `create_chart`: persist the artifact (+commit), build the figure, emit `ArtifactFrame`; at turn end call `assign_message_seq_to_turn_captures` (T006)
- [X] T029 [US2] Include persisted artifacts in `ConversationDetail` in `backend/app/api/conversations.py` (figure rebuilt from stored spec)
- [X] T030 [US2] Add the `artifact` frame to the `Frame` union in `frontend/src/api/wsClient.ts`; add `ChartArtifact` + `Message.artifacts` to `frontend/src/types.ts`
- [X] T031 [P] [US2] Create `frontend/src/components/PlotlyArtifact.tsx` — lazy-loaded `react-plotly.js` wrapper (reduced-motion aware)
- [X] T032 [US2] In `frontend/src/App.tsx`, accumulate per-turn artifacts (`pendingArtifactsRef`) and attach to the agent message on `done`; clear on `error`
- [X] T033 [US2] Render per-message artifacts in `frontend/src/components/MessageList.tsx`; map reloaded artifacts by `message_seq` in `frontend/src/api/restClient.ts` `getConversation`

**Checkpoint**: Interactive charts render live and on reload, independent of other stories.

---

## Phase 5: User Story 3 - Math/LaTeX rendering (Priority: P1)

**Goal**: Inline and block math typeset cleanly in chat (streaming-safe) and in the PDF.

**Independent Test**: Ask for a rotation-as-formula → inline + block math typeset (no raw `$$`/`\text{}`);
"$5" is not math; the PDF renders math legibly.

### Tests for User Story 3

- [X] T034 [P] [US3] Extend `backend/tests/test_pdf_report.py` — a message with a block equation renders without raw `$$` source (image/legible)

### Implementation for User Story 3

- [X] T035 [US3] In `frontend/src/components/StreamMarkdown.tsx`, add `remark-math` to `remarkPlugins` and append `rehype-katex` to the rehype pipeline (validate the installed Streamdown forwards `remarkPlugins`; fallback per research R5)
- [X] T036 [P] [US3] Import KaTeX CSS in `frontend/src/index.css` (or `styles.css`)
- [X] T037 [US3] Make `backend/app/services/pdf_report.py` math-aware — block `$$…$$` → matplotlib mathtext image flowable; inline math → unwrap `\text{}`/delimiters to italic (FR-016)

**Checkpoint**: Math renders correctly in chat and PDF, no regressions to prose/tables/links.

---

## Phase 6: User Story 4 - Faster repeat analysis via caching (Priority: P2)

**Goal**: An in-process two-tier TTL cache at `WCLClient.query` removes duplicate WCL calls (latency +
API-point savings) transparently for all tools.

**Independent Test**: A follow-up reusing the same report/boss/filters is faster and spends no extra
rate-limit points; automated cache test passes.

### Tests for User Story 4

- [X] T038 [P] [US4] `backend/tests/test_wcl_cache.py` — hit/miss by query+variables; report vs leaderboard TTL; `rateLimitData` bypass; deep-copy isolation (per contracts/caching.md)

### Implementation for User Story 4

- [X] T039 [P] [US4] Create `wcl_agent/cache.py` — `TTLCache` (LRU + lazy expiry), `cache_key(query, variables)`, tier classifier (report-scoped vs leaderboard vs rateLimit bypass), env-tunable TTLs
- [X] T040 [US4] Integrate the cache into `WCLClient.query` in `wcl_agent/wcl_client.py` (consult before network; store with tier TTL; deep-copy on read/write; bypass `rateLimitData`)

**Checkpoint**: Repeat lookups are cached; no behavior change on cache miss.

---

## Phase 7: User Story 5 - Per-message analytic PDF report (Priority: P2)

**Goal**: A per-message "Download report" exports one agent reply + its originating question + its
charts/graphs, excluding other messages.

**Independent Test**: Trigger the per-message report on a reply with a table/prose/link/chart → PDF has
that reply + its question + the chart, excludes other messages, renders cleanly.

### Tests for User Story 5

- [X] T041 [P] [US5] `backend/tests/test_message_report.py` — endpoint returns a PDF scoped to one message (its question + its captures), 404 on unknown message, excludes other messages (FR-023/026)

### Implementation for User Story 5

- [X] T042 [US5] Add `GET /api/conversations/{conv_id}/messages/{message_id}/report.pdf` to `backend/app/api/reports.py` — resolve message→seq, gather that agent message + nearest preceding user message + `captured_graphs`/`artifacts` with `message_seq==seq`; render via `render_report_pdf`
- [X] T043 [US5] Ensure `backend/app/services/pdf_report.py` renders chart-spec artifacts (via `chart_spec_to_matplotlib`) in both per-message and conversation reports (depends on T025)
- [X] T044 [US5] Add `downloadMessageReport(convId, messageId)` to `frontend/src/api/restClient.ts`
- [X] T045 [US5] Add a per-message "Download report" control to agent replies in `frontend/src/components/MessageList.tsx` and wire the handler in `frontend/src/App.tsx`

**Checkpoint**: Both conversation-level and per-message PDFs work and include artifacts.

---

## Phase 8: User Story 6 - Auto-fetched spec guide on lock-in (Priority: P2)

**Goal**: Locking a character/guild starts a non-blocking background task that resolves the active spec
(WCL) and compiles a guide via the web-search-capable guide model, persisted for context.

**Independent Test**: Locking a character returns < ~1s (`pending`); shortly after `guide_status:
"ready"` and an improvement question reflects it; a bogus name still saves (`failed`) and answers degrade
gracefully.

### Tests for User Story 6

- [X] T046 [P] [US6] `backend/tests/test_guide.py` — guide lifecycle `pending→ready`; failure path → `failed` with entry still saved; idempotent re-lock (mock WCL resolve + `stream_response`)

### Implementation for User Story 6

- [X] T047 [P] [US6] Add `set_character_guide(...)` (and guild summary setter) to `backend/app/db/repository.py`
- [X] T048 [US6] Create `backend/app/services/guide.py` — `resolve_active_spec(name,server,region)` (WCL characterData), `run_guide_task(...)` generating via `stream_response` on `settings.wcl_guide_model`, persist status transitions; in-flight-set idempotency; guild variant compiles a progression summary
- [X] T049 [US6] In `backend/app/api/profile.py`, schedule `asyncio.create_task(run_guide_task(...))` on `PUT self` / `POST friend` / `PUT guild` (status→`pending`, return immediately)

**Checkpoint**: Guides populate in the background and feed the US1 preamble.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T050 [P] Reduced-motion + bundle check: confirm `PlotlyArtifact` is lazy-loaded and honors `prefers-reduced-motion`; verify `npm run build` bundle is acceptable (`plotly.js-dist-min`)
- [X] T051 [P] Update `.env.example` and `documentation/ai_guide.md` with the guide model + cache env vars
- [X] T052 Run `uv run pytest -q` and `cd frontend && npm run build`; fix any regressions (esp. `test_api`, `test_pdf_report`)
- [ ] T053 Execute `specs/005-guild-context-artifacts/quickstart.md` end-to-end (all six stories + regression)

---

## Dependencies & Execution Order

### Phase dependencies
- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: after Setup; blocks all stories (T004/T005 provide the tables; T006 the capture-linkage).
- **User stories (Phases 3–8)**: after Foundational. US1/US2/US3/US4 are independent of each other. US5 depends on US2's chart renderer (T025) for artifact-in-PDF; US6 depends on US1 (profile tables/endpoints + preamble consumption).
- **Polish (Phase 9)**: after the desired stories.

### Key cross-story dependencies
- T043/T042 (US5 artifact-in-PDF) depend on T025 (US2 `charts.py`). US5's text-only report works without US2; chart inclusion needs US2.
- T049 (US6 scheduling) depends on T015 (US1 profile endpoints); T048 guide output is consumed by T011 (US1 preamble) — US6 enriches US1.
- T028/T033 rely on T006 (foundational message-seq linkage) and T026 (artifact repo).

### Within a story
- Tests may be written first (they will fail pre-implementation).
- Models → repository → services → API/tool → frontend.

### Parallel opportunities
- Setup T001/T002/T003 all [P].
- Foundational T006 [P] alongside T004/T005 ordering (T006 references the Artifact model from T004).
- Across stories once Foundational is done: US1, US2, US3, US4 can proceed in parallel (different files).
- Within stories, [P] tasks touch distinct files (e.g. US1 T007/T008/T009/T011/T017; US2 T020/T021/T022/T024/T025/T031).

---

## Parallel Example: User Story 2

```bash
# Tests (write first):
Task: "backend/tests/test_charts.py"            # T020
Task: "backend/tests/test_artifacts.py"         # T021
# Independent implementation files:
Task: "create_chart tool in wcl_agent/tools.py" # T022
Task: "ChartSpec/ArtifactOut/ArtifactFrame in backend/app/schemas.py"  # T024
Task: "backend/app/services/charts.py"          # T025
Task: "frontend/src/components/PlotlyArtifact.tsx"  # T031
```

---

## Implementation Strategy

### MVP first (US1)
1. Phase 1 Setup → Phase 2 Foundational → Phase 3 US1.
2. **STOP & validate**: profile steers answers; population questions unaffected. Demo.

### Incremental delivery
US1 (personalization) → US2 (interactive charts) → US3 (math) → US4 (caching) → US5 (per-message PDF) →
US6 (auto guides). Each is independently testable and additive; US5 chart-in-PDF and US6 guide richness
land fully once US2 and US1 respectively are in.

---

## Notes
- `[P]` = different files, no incomplete dependency.
- Run `gitnexus_impact` before editing `stream_response`, `_handle_tool_end`, `_handle_turn`,
  `WCLClient.query`, `build_agent`/`INSTRUCTION`, `render_report_pdf`, and `main.lifespan`;
  `gitnexus_detect_changes` before commit (constitution Principle VI).
- Keep `wcl_agent` standalone (no backend/DB imports): the cache and `create_chart` live there dependency-light.
- Commit after each task or logical group.
