---
description: "Task list for Agent App Enhancements"
---

# Tasks: Agent App Enhancements

**Input**: Design documents from `/specs/002-agent-enhancements/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Light test tasks are included per story because plan.md and quickstart.md
explicitly call for targeted backend tests (raid dedup, session restore, model
validation, PDF). They are happy-path + key-edge coverage, not full TDD.

**Organization**: Tasks are grouped by user story. Stories are logically independent and
independently testable, but several share files (`agent_runner.py`, `ws.py`, `main.py`,
`schemas.py`, `db/models.py`, `App.tsx`) — those edits are sequenced, not parallel.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1–US5 (user story phases only)

## Path Conventions

Web app layout from plan.md: backend at `backend/`, frontend at `frontend/`, reused
agent core at `wcl_agent/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencies and environment for all new work.

- [X] T001 Add backend dependencies via `uv add "psycopg[binary]" "google-adk[anthropic]" reportlab matplotlib markdown` and run `uv sync` (updates `pyproject.toml` + `uv.lock`)
- [X] T002 [P] Add matplotlib/reportlab runtime system libs (e.g. libfreetype/libpng) to `backend/Dockerfile` if the base image lacks them
- [X] T003 [P] Add new env vars (`WCL_GEMINI_MODELS`, `WCL_ANTHROPIC_MODELS`, `WCL_DEFAULT_MODEL`) to `.env.example`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared backbone every story builds on — config, the enriched agent-runner
tool stream, and the report-metadata helper.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Extend `backend/app/config.py`: add `gemini_models`/`anthropic_models` candidate properties and a `sync_database_url` derived from `DATABASE_URL` (`postgresql+asyncpg` → `postgresql+psycopg`)
- [X] T005 Refactor `backend/app/agent_runner.py` `stream_response` into the shared backbone: for each ADK event, capture `function_call.args` (incl. `report_code`) and `function_response` `status`/raw result, and yield tool records carrying that detail (keeps one source of truth for raid detection, graph capture, and grounding) — GitNexus impact-check `stream_response` first
- [X] T006 [P] Add `get_report_metadata(report_code)` helper to `wcl_agent/report_tools.py` (one GraphQL call for `title`/`zone.name`/`guild.name`/`startTime`), reusing `get_client`

**Checkpoint**: Foundation ready — user stories can begin.

---

## Phase 3: User Story 1 - Tracked raids + one-click re-investigate (Priority: P1) 🎯 MVP

**Goal**: Auto-record raids on successful report retrieval, list them (most-recent-first)
in a dedicated sidebar section, and let a click open a new chat that auto-investigates.

**Independent Test**: Ask about a report → it appears in Raids with a timestamp; ask
about a second → both listed newest-first; re-ask the first → no duplicate, jumps to top;
click it → new chat auto-investigates; restart backend → list persists.

### Implementation for User Story 1

- [X] T007 [P] [US1] Add `TrackedRaid` model (unique `report_code`, label/zone/guild/report_started_at/first_seen_at/last_asked_at/last_conversation_id) in `backend/app/db/models.py`
- [X] T008 [US1] Add `upsert_tracked_raid` (insert-or-touch by `report_code`) and `list_tracked_raids` (order by `last_asked_at DESC`) to `backend/app/db/repository.py`
- [X] T009 [US1] Create `backend/app/services/raids.py`: from backbone tool records, detect successful report-scoped retrievals, resolve the label via `get_report_metadata` (`asyncio.to_thread`), and upsert the raid
- [X] T010 [US1] Add `RaidOut`, `RaidListResponse`, `InvestigateRequest`, `InvestigateResponse`, and optional `RaidTrackedFrame` to `backend/app/schemas.py`
- [X] T011 [US1] Create `backend/app/api/raids.py` with `GET /api/raids` and `POST /api/raids/{report_code}/investigate` (creates an **empty** conversation, returns server-owned `kickoff_prompt` without persisting any message); register the router in `backend/app/main.py`
- [X] T012 [US1] In `backend/app/api/ws.py`, route backbone tool records to the raids service (upsert on success) and emit optional `raid_tracked`. No kickoff special-casing: the investigate prompt arrives as a normal first turn and persists through the standard path
- [X] T013 [P] [US1] Add `Raid` type and `getRaids`/`investigateRaid` to `frontend/src/types.ts` and `frontend/src/api/restClient.ts`
- [X] T014 [US1] Add a "Raids" section (label + last-asked time, newest-first) to `frontend/src/components/Sidebar.tsx` (optionally split into `frontend/src/components/RaidList.tsx`)
- [X] T015 [US1] Wire raid click → `investigateRaid` → open new chat and stream the kickoff turn over the WS in `frontend/src/App.tsx`
- [X] T016 [P] [US1] Backend test: raid upsert/dedup + ordering + investigate endpoint in `backend/tests/test_raids.py`

**Checkpoint**: Raids are tracked, listed, persistent, and one-click re-investigable.

---

## Phase 4: User Story 2 - Durable sessions & complete persistence (Priority: P1)

**Goal**: Persist the agent session so conversation *context* survives a restart, and
persist partial output on interruption.

**Independent Test**: Hold a context-building chat → restart backend → reopen: full
history shows AND a context-dependent follow-up is answered correctly; interrupt a reply
→ it is stored as `partial`, never shown as complete.

### Implementation for User Story 2

- [X] T017 [US2] Add `status` column (`complete`|`partial`, default `complete`) to the `Message` model in `backend/app/db/models.py`, **and** add an idempotent startup migration in `backend/app/main.py` lifespan (after `create_all`): `ALTER TABLE messages ADD COLUMN IF NOT EXISTS status VARCHAR(10) NOT NULL DEFAULT 'complete'` — `create_all` does not ALTER the existing `messages` table from 001
- [X] T018 [US2] Swap `InMemorySessionService` → ADK `DatabaseSessionService` (using `settings.sync_database_url`, blocking calls via `asyncio.to_thread`) in `backend/app/agent_runner.py`, and manage its lifecycle in `backend/app/main.py` lifespan — GitNexus impact-check the runner first
- [X] T019 [US2] Persist accumulated tokens as a `partial` agent message on stream error/disconnect in `backend/app/api/ws.py`; extend `add_message` with a `status` param in `backend/app/db/repository.py`
- [X] T020 [P] [US2] Distinguish partial/interrupted replies visually in `frontend/src/components/MessageList.tsx` and `frontend/src/types.ts`
- [X] T021 [P] [US2] Backend test: session restore after restart (context continuity) + partial persistence in `backend/tests/test_persistence.py`

**Checkpoint**: Sessions, messages, and responses durably persist; context restores.

---

## Phase 5: User Story 3 - Web access via native grounding (Priority: P2)

**Goal**: Gemini models use native Google Search grounding; non-grounding models degrade
gracefully; grounding usage is surfaced in the UI.

**Independent Test**: With Gemini, ask a current/external question → answer uses web info
and the UI shows the grounding indicator; switch to Anthropic → answers from available
data with a note, no error.

### Implementation for User Story 3

- [X] T022 [US3] Make `build_agent(model)` model-aware in `wcl_agent/agent.py`: Gemini → WCL tools + grounding (built-in `google_search`, or a grounding-only search **sub-agent as a tool** if the model rejects the combined toolset); Anthropic/other → WCL tools only — GitNexus impact-check `build_agent` first
- [X] T023 [US3] Detect `grounding_metadata` in `backend/app/agent_runner.py` and emit a `grounding` frame; add `GroundingFrame` to `backend/app/schemas.py`; no-op gracefully when unsupported
- [X] T024 [P] [US3] Add a grounding indicator in `frontend/src/components/MessageList.tsx` and the `Frame` type in `frontend/src/api/wsClient.ts`
- [X] T025 [P] [US3] Backend test: grounding frame emitted for a grounding model; non-grounding model degrades without error in `backend/tests/test_grounding.py`

**Checkpoint**: Agent can use the web on supported models; others degrade cleanly.

---

## Phase 6: User Story 4 - Dynamic, validated model selection (Priority: P2)

**Goal**: Model list is discovered + responsiveness-validated once at startup; unavailable
models are excluded; a fallback keeps the selector non-empty.

**Independent Test**: Selector matches validated candidates; a bogus id is excluded after
restart; simulated Vertex-unreachable shows a fallback set + degraded notice (never empty).

### Implementation for User Story 4

- [X] T026 [US4] Create `wcl_agent/models.py`: build candidate set (Gemini + Anthropic-on-Vertex) and validate each via health-check or a minimal "hello" probe (Gemini genai/Vertex client; Anthropic Vertex client)
- [X] T027 [US4] Run validation once in `backend/app/main.py` lifespan (via `asyncio.to_thread`), store `{models, default, degraded}` in `app.state` (the `default` = `WCL_DEFAULT_MODEL` if validated, else first validated model — the single runtime source of truth), with a documented fallback set when discovery fails
- [X] T028 [US4] Serve the validated set (+`degraded`) from `app.state` in `backend/app/api/models.py` (update `ModelsResponse`), and validate requested models against `app.state` in `backend/app/api/ws.py` and `backend/app/api/conversations.py`
- [X] T029 [US4] Register the Anthropic-on-Vertex model class in the `build_agent` model registry in `wcl_agent/agent.py` (maps Anthropic ids → Claude model; Gemini ids pass through), **and** reconcile the pre-existing default drift: align `agent.DEFAULT_MODEL` with `config` so `build_agent`'s fallback matches the runtime `app.state.default` (backend always passes an explicit validated model; the constant is last-resort only)
- [X] T030 [P] [US4] Show the `degraded` notice in `frontend/src/components/ModelSelect.tsx` (and surface the flag via `getModels` in `frontend/src/api/restClient.ts`)
- [X] T031 [P] [US4] Backend test: validation keeps responsive models, excludes a bogus id, and fallback is never empty in `backend/tests/test_models.py`

**Checkpoint**: Only responsive, real models are offered; selector never empty.

---

## Phase 7: User Story 5 - Download a PDF report with graphs (Priority: P3)

**Goal**: Capture graph JSON during a conversation and render a downloadable PDF (header +
written analysis + charts) on demand.

**Independent Test**: In a conversation where the agent fetched graphs, Download PDF →
PDF has header, analysis, and rendered charts; in a graph-less conversation the PDF still
generates (analysis only); a render failure shows a clear error.

### Implementation for User Story 5

- [X] T032 [P] [US5] Add `CapturedGraph` model (conversation FK cascade, message_seq, report_code, data_type, fight_id, source_id, `graph_json` JSONB) in `backend/app/db/models.py`
- [X] T033 [US5] Add `add_captured_graph` and `list_captured_graphs` (ordered by message_seq, created_at) to `backend/app/db/repository.py`
- [X] T034 [US5] Create `backend/app/services/graphs.py`: from backbone tool records, capture successful `get_report_graph` payloads for the conversation
- [X] T035 [US5] Wire graph capture into the turn flow in `backend/app/api/ws.py`
- [X] T036 [US5] Create `backend/app/services/pdf_report.py`: build the PDF (header with raid label + date, agent-message analysis via `markdown`→reportlab, captured graphs → matplotlib PNGs) entirely under `asyncio.to_thread`
- [X] T037 [US5] Add `GET /api/conversations/{id}/report.pdf` in `backend/app/api/reports.py` (streaming `application/pdf`, `404` unknown, `500 pdf_generation_failed` on render error); register the router in `backend/app/main.py`
- [X] T038 [P] [US5] Add a Download PDF button + `downloadReport` client in `frontend/src/App.tsx` and `frontend/src/api/restClient.ts`
- [X] T039 [P] [US5] Backend test: PDF happy path + no-graphs path + failure → clear error in `backend/tests/test_reports.py`

**Checkpoint**: Users can export a faithful PDF of any analyzed conversation.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T040 [P] Update `.env.example`, `README.md`, and `documentation/` for the new env vars and five features
- [ ] T041 Run `quickstart.md` end-to-end (`docker compose up --build`) validating all five stories — ⚠️ requires live Vertex ADC + WCL creds; validated via full test suite (32 passing), frontend prod build, and backend OpenAPI load instead
- [X] T042 Run `gitnexus_detect_changes()` before committing to confirm only expected symbols/flows changed

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup; **blocks all user stories** (T005 backbone + T004 config + T006 metadata helper).
- **User Stories (Phases 3–7)**: all depend on Foundational.
  - P1 first (US1, US2), then P2 (US3, US4), then P3 (US5).
- **Polish (Phase 8)**: after the desired stories are complete.

### User Story Dependencies

- **US1 (P1)**: needs the backbone (T005) + metadata helper (T006). Independent of other stories.
- **US2 (P1)**: needs the backbone (shares `agent_runner.py`). Independent of US1.
- **US3 (P2)**: needs the backbone (grounding emission). Independent; shares `agent.py` with US4.
- **US4 (P2)**: independent; `app.state` model set is consumed by `ws.py`/`conversations.py`.
- **US5 (P3)**: needs the backbone (graph capture). Independent of US1–US4.

### Shared-file sequencing (NOT parallel across stories)

- `backend/app/agent_runner.py`: T005 → T018 (US2) → T023 (US3).
- `backend/app/api/ws.py`: T012 (US1) → T019 (US2) → T028 (US4) → T035 (US5).
- `backend/app/main.py`: T011 (US1) → T018 (US2) → T027 (US4) → T037 (US5).
- `backend/app/db/models.py`: T007 (US1) → T017 (US2) → T032 (US5).
- `backend/app/db/repository.py`: T008 (US1) → T019 (US2) → T033 (US5).
- `backend/app/schemas.py`: T010 (US1) → T023 (US3) → T028 (US4).
- `wcl_agent/agent.py`: T022 (US3) → T029 (US4).
- `frontend/src/App.tsx`: T015 (US1) → T038 (US5).

### Within Each User Story

- Models → repository → service → endpoint/WS → frontend → test.

### Parallel Opportunities

- Setup: T002, T003 in parallel.
- Foundational: T006 parallel with T004/T005.
- Within a story, `[P]` tasks touch distinct files (e.g. US1: T007, T013, T016).
- Across stories, after Foundational, backend and frontend `[P]` tasks for different
  stories can proceed if staffed — but respect the shared-file sequencing above.

---

## Parallel Example: User Story 1

```bash
# After Foundational, launch the independent-file US1 tasks together:
Task: "T007 Add TrackedRaid model in backend/app/db/models.py"
Task: "T013 Add Raid type + getRaids/investigateRaid in frontend/src/{types.ts,api/restClient.ts}"
Task: "T016 Backend test raid upsert/dedup in backend/tests/test_raids.py"
# Then sequence T008 → T009 → T010 → T011 → T012 (backend chain), and T014 → T015 (frontend).
```

---

## Implementation Strategy

### MVP First

1. Phase 1 Setup → Phase 2 Foundational.
2. Phase 3 (US1) → **STOP and validate** the raid-history flow independently. This is the
   headline MVP.
3. Recommended coherent P1 release: also complete Phase 4 (US2) so history/context is
   durable before demoing.

### Incremental Delivery

Foundation → US1 (MVP) → US2 → US3 → US4 → US5, validating and demoing after each. Each
story adds value without breaking the previous ones.

### Notes

- `[P]` = different files, no dependency on incomplete tasks.
- Honor the shared-file sequencing table — it's where cross-story coupling actually lives.
- Run GitNexus impact analysis before editing `stream_response`, `build_agent`, and other
  shared symbols (constitution Principle VI); run `detect_changes` before commit.
- Commit after each task or logical group.
