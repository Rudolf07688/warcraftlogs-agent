---
description: "Task list for Chat Follow-ups & UX Enhancements"
---

# Tasks: Chat Follow-ups & UX Enhancements

**Input**: Design documents from `/specs/003-chat-followups-ux/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Backend slices (US1, US2) include pytest tasks (requested in plan/research).
Frontend slices (US3, US5, US6) and the persona voice (US4) are verified via quickstart
manual steps — there is no frontend test harness (YAGNI, per research).

**Organization**: Tasks grouped by user story for independent implementation/testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US6 (maps to spec.md user stories)

## Path Conventions

Web app: backend code in `backend/app/` and `wcl_agent/`; tests in `backend/tests/`;
frontend in `frontend/src/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm a green baseline before changing anything.

- [X] T001 Confirm environment and baseline: `uv sync`, `cd frontend && npm install`, then `uv run pytest -q` passes on `main` before edits (establishes the pre-change baseline).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared utility used by the two preference-based stories (US5, US6). Does NOT block US1–US4.

- [X] T002 Create typed localStorage preference helper in `frontend/src/uiPrefs.ts` (get/set/clamp for keys `wcl.ui.sidebarWidth` default 260 clamped [200,480], and `wcl.ui.background` default = new image id; corrupt/unknown values fall back safely) per `contracts/ui-config.md`.

**Checkpoint**: Foundation ready — user stories can begin (US1 is the MVP target).

---

## Phase 3: User Story 1 - Suggested follow-up questions (Priority: P1) 🎯 MVP

**Goal**: After each answer, show up to 3 clickable, context-relevant follow-up question buttons that re-prompt the agent.

**Independent Test**: Ask an analytical question → 0–3 relevant buttons appear → click one → it is submitted verbatim and answered; a greeting shows no buttons; never >3.

### Tests for User Story 1 ⚠️ (write first, ensure they FAIL)

- [X] T003 [P] [US1] Unit test `generate_followups` in `backend/tests/test_suggestions.py`: returns ≤3 items, dedups/trims, returns `[]` for trivial/greeting/error answers.
- [X] T004 [P] [US1] WS flow test in `backend/tests/test_api.py`: a normal analytical turn emits a `suggestions` frame (≤3) immediately before `done`; a trivial turn emits none; `error` turns emit no suggestions.

### Implementation for User Story 1

- [X] T005 [US1] Run `gitnexus_impact({target: "_handle_turn", direction: "upstream"})` (and on `stream_response`); report blast radius before editing `backend/app/api/ws.py`.
- [X] T006 [US1] Add `SuggestionsFrame` (type `"suggestions"`, `suggestions: list[str]` max_length 3) to `backend/app/schemas.py` per `contracts/websocket.md`.
- [X] T007 [P] [US1] Create `backend/app/suggestions.py` with async `generate_followups(model, question, answer) -> list[str]`: small structured (non-streaming) call, dedup/trim, hard-cap 3, `[]` when trivial; non-blocking (`asyncio.to_thread` if the call is sync).
- [X] T008 [US1] In `backend/app/api/ws.py` `_handle_turn`, after streaming completes and before `DoneFrame`, call `generate_followups` and send a `SuggestionsFrame` only when non-empty (depends on T006, T007).
- [X] T009 [P] [US1] Add `{ type: "suggestions"; suggestions: string[] }` to the `Frame` union in `frontend/src/api/wsClient.ts` and `suggestions?: string[]` to `Message` in `frontend/src/types.ts`.
- [X] T010 [P] [US1] Create `frontend/src/components/FollowUps.tsx`: renders up to 3 buttons, truncates long labels (submits full text), disabled while streaming.
- [X] T011 [US1] In `frontend/src/App.tsx` handle the `suggestions` frame: attach to the latest agent turn's state, clear on new turn (FR-005), wire button click to `sendText`, disable while `streaming` (depends on T009, T010).
- [X] T012 [US1] Render `FollowUps` under the latest agent message in `frontend/src/components/MessageList.tsx` and add button styles to `frontend/src/styles.css`.

**Checkpoint**: US1 fully functional and independently testable (MVP).

---

## Phase 4: User Story 2 - Reliable parallel tool execution + shared scratch (Priority: P2)

**Goal**: Independent tool lookups run concurrently; every complete result (incl. large) is reliably collected via a per-turn shared scratch store; one failure doesn't abort the turn.

**Independent Test**: A multi-lookup question runs faster than sequential, reflects all successful results; a large output is captured intact; one failing tool leaves others usable and is reported.

### Tests for User Story 2 ⚠️ (write first, ensure they FAIL)

- [X] T013 [P] [US2] Create `backend/tests/test_parallel_tools.py`: (a) two tools' combined wall-clock < sum of individual delays (concurrency); (b) a large tool payload round-trips through the scratch store intact (no truncation); (c) one failing tool yields an error-shaped result while the others' results remain usable (no turn abort).

### Implementation for User Story 2

- [X] T014 [US2] Run `gitnexus_impact({target: "stream_response", direction: "upstream"})` and on `_handle_tool_end`; report blast radius before editing `backend/app/agent_runner.py` / `backend/app/api/ws.py`.
- [X] T015 [P] [US2] Create `backend/app/scratch.py`: per-turn `tempfile` store — create(turn_id), write(call_id, result), read(call_id), and cleanup(turn_id); keyed by `call_id` per `data-model.md`.
- [X] T016 [US2] In `backend/app/agent_runner.py` `stream_response`, write each tool's full `function_response` result to the per-turn scratch store keyed by `call_id` (reusing the existing `pending_args` correlation) and preserve the complete payload in the yielded `tool_end` record.
- [X] T017 [US2] In `backend/app/api/ws.py` `_handle_turn`: create the scratch store at turn start and `cleanup` in a `finally`; have the raid/graph capture services read the full result from scratch by `call_id`; confirm a single failing tool surfaces as an error-shaped result (no whole-turn abort) (depends on T015, T016).

**Checkpoint**: US1 + US2 both work independently.

---

## Phase 5: User Story 3 - Correct response panel sizing (Priority: P2)

**Goal**: Response panels size to content and available width instead of a fixed pixel cap.

**Independent Test**: Long and short answers size correctly (scroll, no fixed gaps); resizing the window reflows the panels.

### Implementation for User Story 3

- [X] T018 [US3] In `frontend/src/styles.css`, replace the fixed `.message` (`max-width: 820px`) and `.message.agent` (`max-width: 860px`) caps with a responsive width (e.g. `max-width: min(860px, 100%)`), and confirm `.message-list` (`flex: 1; overflow-y: auto`) still owns vertical scroll so long answers expand without clipping (US3, FR-010/011/012).

**Checkpoint**: US1 + US2 + US3 independently functional.

---

## Phase 6: User Story 4 - Barnaby the innkeeper persona (Priority: P3)

**Goal**: Assistant is "Barnaby", a blunt-but-funny innkeeper who calls out mistakes, without losing data-grounding.

**Independent Test**: "Who are you?" → identifies as Barnaby; reviewing a weak parse → names the mistake with humor; numbers stay accurate.

### Implementation for User Story 4

- [X] T019 [US4] Run `gitnexus_impact({target: "build_agent", direction: "upstream"})`; report blast radius before editing the prompt in `wcl_agent/agent.py`.
- [X] T020 [US4] Edit the single-source `Personality` block in `wcl_agent/agent.py`: name the assistant "Barnaby" (tavern/innkeeper, guild MC), blunt and funny, explicitly calls out mistakes in good humor; keep the existing "base every answer only on tool data" rules intact (FR-013/014/015).

**Checkpoint**: Persona live across all model variants.

---

## Phase 7: User Story 5 - Resizable side panel (Priority: P3)

**Goal**: Drag to resize the sidebar; width clamped and persisted across sessions.

**Independent Test**: Drag resizes smoothly and reflows chat; extremes clamp and keep the handle reachable; reload restores width.

### Implementation for User Story 5

- [X] T021 [P] [US5] In `frontend/src/styles.css`, change `.app` grid column to `var(--sidebar-width, 260px) 1fr` and add resizer/handle styles.
- [X] T022 [US5] Add a drag resizer on the sidebar/main boundary in `frontend/src/App.tsx` (and `frontend/src/components/Sidebar.tsx` handle): on drag update `--sidebar-width` within [200,480], persist + restore via `uiPrefs` (T002) (FR-016/017/018).

**Checkpoint**: Sidebar resize persists.

---

## Phase 8: User Story 6 - Togglable background image (Priority: P3)

**Goal**: New image is the default background; previous one retained; switchable via config; legible; graceful fallback.

**Independent Test**: New image shows by default and is legible; toggling switches background and persists; a missing image falls back to solid color.

### Implementation for User Story 6

- [X] T023 [P] [US6] Background image `background_2.jpg` copied into source assets (`frontend/public/assets/`) so Vite builds include it; previous background retained as the "Classic" option.
- [X] T024 [P] [US6] Create `frontend/src/config.ts` with the `BACKGROUNDS` registry (new Morgan Howell image `default: true`, classic/previous, and `none`/solid) per `contracts/ui-config.md`.
- [X] T025 [US6] Apply the selected background + legibility scrim in `frontend/src/styles.css` and `frontend/src/App.tsx`, reading/persisting the choice via `uiPrefs` (T002) with a solid-color fallback on image load failure (FR-019/020/021) (depends on T023, T024).
- [X] T026 [US6] Create `frontend/src/components/BackgroundToggle.tsx` and mount it (e.g. in the chat header) to switch backgrounds at runtime (depends on T024, T025).

**Checkpoint**: All six user stories independently functional.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [ ] T027 [P] Update `README.md` / `AGENTS.md` only if user-facing behavior notes are needed (follow-ups, background toggle, resizable panel).
- [X] T028 Run `uv run pytest -q` — all backend tests green.
- [ ] T029 Walk through `specs/003-chat-followups-ux/quickstart.md` — verify all six stories manually.
- [X] T030 Run `gitnexus_detect_changes()` before committing to confirm only expected symbols/flows changed (per CLAUDE.md).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none — start immediately.
- **Foundational (Phase 2)**: after Setup. Blocks only US5 and US6 (shared `uiPrefs`).
- **US1 (Phase 3)**: after Setup — the MVP; independent of all other stories.
- **US2 (Phase 4)**: after Setup — independent (touches agent_runner/ws tool path, not US1's suggestion path).
- **US3 (Phase 5)**: after Setup — CSS-only, fully independent.
- **US4 (Phase 6)**: after Setup — prompt-only, fully independent.
- **US5 (Phase 7)**: after Foundational (needs T002).
- **US6 (Phase 8)**: after Foundational (needs T002).
- **Polish (Phase 9)**: after the desired stories are complete.

### User Story Dependencies

All six stories are independently testable. No story depends on another's completion.
US5 and US6 share `uiPrefs.ts` (T002) but are otherwise independent of each other.

### Within Each User Story

- Tests (US1, US2) written first and failing before implementation.
- Backend: schema/model → service/module → wiring into ws/agent_runner.
- Frontend: types → component → integration (App/MessageList) → styles.
- Run `gitnexus_impact` before editing any existing symbol (T005, T014, T019).

### Parallel Opportunities

- US1, US2, US3, US4 can all proceed in parallel after Setup (different files/paths).
- US5 and US6 can proceed in parallel after T002.
- Within stories, [P] tasks touch distinct files (e.g. T003/T004 tests; T009/T010 FE types vs component; T023/T024 asset vs config).

---

## Parallel Example: User Story 1

```bash
# Tests first (different files):
Task: "Unit test generate_followups in backend/tests/test_suggestions.py"   # T003
Task: "WS suggestions-frame flow test in backend/tests/test_api.py"          # T004

# Then independent impl files:
Task: "Create backend/app/suggestions.py generate_followups"                 # T007
Task: "Add suggestions to Frame union + Message type (wsClient.ts, types.ts)"# T009
Task: "Create frontend/src/components/FollowUps.tsx"                          # T010
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → 2. (US1 needs no Foundational) → 3. Phase 3 US1 → **STOP & validate** → demo.

### Incremental Delivery

Setup → US1 (MVP) → US2 → US3 → US4 → (T002 Foundational) → US5 → US6 → Polish.
Each story ships value without breaking the previous ones.

### Parallel Team Strategy

After Setup: Dev A → US1, Dev B → US2, Dev C → US3+US4; after T002: Dev D → US5+US6.

---

## Notes

- [P] = different files, no incomplete-task dependencies.
- Constitution: run `gitnexus_impact` before editing existing symbols; `gitnexus_detect_changes` before commit (T030); warn on HIGH/CRITICAL risk.
- Commit after each task or logical group; never commit secrets.
- Frontend has no test harness — US3/US5/US6 verified via quickstart (T029).
