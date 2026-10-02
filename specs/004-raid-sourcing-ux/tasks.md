---
description: "Task list for Raid Sourcing, Tracking & Report UX (incl. US6 fantasy polish)"
---

# Tasks: Raid Sourcing, Tracking & Report UX

**Input**: Design documents from `/specs/004-raid-sourcing-ux/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Backend behavior is covered by pytest (matching the existing suite). Agent-prompt
behavior (US1) and all UI (US4 picker, US5 inject, and all of US6) are verified via
`quickstart.md` — including a reduced-motion pass and a ~60 fps spot check.

**Organization**: Tasks are grouped by user story (priority order). US6 (fantasy polish) is P1 but
depends on the Foundational frontend stack migration, so it is sequenced after the functional
stories; its backend sub-tasks are independent and can be pulled earlier.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US6 maps to the spec's user stories
- Every task includes an exact file path

## Path Conventions

Web app: `backend/` (FastAPI), `frontend/` (React/Vite), `wcl_agent/` (ADK agent package).

---

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Confirm baseline: `uv sync`, `cd frontend && npm install`, then `uv run pytest -q` passes on the current tree (pre-change baseline).

---

## Phase 2: Foundational (Blocking Prerequisites) — Frontend stack migration

**Purpose**: Migrate the frontend to the US6 stack (React 19 + Tailwind v4 + shadcn/ui +
streaming-safe renderer) and keep the app building & streaming. **Blocks all frontend work**
(US6 and the frontend portions of US1/US2/US4/US5). Backend-only slices (US2 backend, US3, US4
backend, US5 backend) do NOT depend on this phase and may proceed in parallel.

**⚠️ Highest-risk phase.** Complete and verify (T009) before layering feature/visual UI on top.

- [X] T002 Upgrade React 18→19: bump `react`, `react-dom`, `@types/react`, `@types/react-dom` in `frontend/package.json`; reconcile the root render API in `frontend/src/main.tsx` and fix any type breakages.
- [X] T003 Add Tailwind v4: install `tailwindcss@4` + `@tailwindcss/vite`; register the plugin in `frontend/vite.config.ts`; create `frontend/src/index.css` with `@import "tailwindcss"` + an `@theme inline` token block; import it from `frontend/src/main.tsx`.
- [X] T004 Initialize shadcn/ui: add `frontend/components.json`, `frontend/src/lib/utils.ts` (`cn()`), and deps (`class-variance-authority`, `clsx`, `tailwind-merge`).
- [X] T005 Define the single fixed fantasy theme in `frontend/src/index.css`: color/font/glow/texture tokens on `:root` and the `@theme inline` mapping; wire a display font (e.g. Cinzel) and a readable body font (e.g. Alegreya Sans) per `contracts/ui-polish.md`.
- [X] T006 Install `streamdown`; create `frontend/src/components/StreamMarkdown.tsx` (Streamdown + remark-gfm behavior, memoized completed blocks) to replace `frontend/src/components/Markdown.tsx`; swap all usages in `frontend/src/components/MessageList.tsx`; delete `Markdown.tsx`.
- [X] T007 Install `use-stick-to-bottom`; replace the manual scroll logic in `frontend/src/components/MessageList.tsx` with it (with a "back to bottom" control).
- [X] T008 Remove the Phase-2 background toggle (FR-027): delete `frontend/src/components/BackgroundToggle.tsx`; drop the background registry from `frontend/src/config.ts` (keep one fixed background constant) and the background preference from `frontend/src/uiPrefs.ts` (keep sidebar width); set the fixed background in `frontend/src/index.css`/`App.tsx`; remove toggle wiring from `frontend/src/App.tsx`.
- [X] T009 Verify Foundational: `cd frontend && npm run build` succeeds and `npm run dev` streams a response; confirm existing features (follow-up suggestions, grounding note, resizable sidebar, raids list) still work on React 19 + Tailwind.

**Checkpoint**: App builds and streams on the new stack. Frontend story work can begin.

---

## Phase 3: User Story 1 - Cited Warcraft Logs source links (Priority: P1) 🎯 MVP

**Goal**: Barnaby cites a clickable WCL URL for data he pulls; links open in a new tab; no fabricated links.

**Independent Test**: Ask about a specific report+fight → the answer has a working WCL link that opens the correct fight in a new tab; a general-knowledge answer has none.

- [X] T010 [US1] Run `gitnexus_impact({target: "build_agent", direction: "upstream"})`; report blast radius before editing the prompt in `wcl_agent/agent.py`.
- [X] T011 [US1] Add a `SOURCE LINKS` section to the single-source `INSTRUCTION` in `wcl_agent/agent.py` (URL format `https://www.warcraftlogs.com/reports/<code>[#fight=<id>][&type=<metric>&source=<id>]`, scoping rules, one link per distinct source, never fabricate for non-WCL content) per `contracts/agent-output.md` (FR-001…005).
- [X] T012 [US1] Add a custom new-tab link `a` component (`target="_blank" rel="noopener noreferrer"`) to `frontend/src/components/StreamMarkdown.tsx` (FR-003).
- [X] T013 [P] [US1] Add link styling (legible over the theme backdrop) in `frontend/src/index.css`.

**Checkpoint**: Source links appear and open correctly.

---

## Phase 4: User Story 2 - Accurate, de-duplicated raid list (Priority: P1)

**Goal**: Each raid shows once with its own date/time + boss(es); concurrent first references never duplicate.

**Independent Test**: Reference the same report in two chats → one sidebar entry showing the raid's real date/time (and boss when known).

### Tests for User Story 2

- [X] T014 [P] [US2] Create `backend/tests/test_encounters.py`: `encounters_from_tool` returns a distinct boss list from a `get_report_fights` result (deduped by `encounterID`, trash/null excluded, `kill=true` if any pull was a kill).
- [X] T015 [P] [US2] Create/extend `backend/tests/test_raids.py`: concurrent first-time upserts of the same `report_code` converge to one row; re-reference merges encounters without duplicating.

### Implementation for User Story 2

- [X] T016 [US2] Run `gitnexus_impact` on `upsert_tracked_raid` and `_handle_tool_end` (upstream); report blast radius before editing `backend/app/db/repository.py` and `backend/app/api/ws.py`.
- [X] T017 [US2] Add the nullable `encounters` JSON column to `TrackedRaid` in `backend/app/db/models.py`.
- [X] T018 [US2] Add an idempotent `ALTER TABLE tracked_raids ADD COLUMN IF NOT EXISTS encounters JSONB` to the `main.py` lifespan startup block in `backend/app/main.py`.
- [X] T019 [P] [US2] Add `EncounterOut` and extend `RaidOut` with `encounters: list[EncounterOut] = []` in `backend/app/schemas.py`.
- [X] T020 [US2] Create `backend/app/services/encounters.py` with `encounters_from_tool(name, ok, result)` → distinct `[{encounter_id, name, difficulty, kill}]`.
- [X] T021 [US2] Make `upsert_tracked_raid` race-safe (Postgres `INSERT … ON CONFLICT (report_code) DO UPDATE`; catch `IntegrityError` → update for SQLite) and accept/merge an `encounters` list in `backend/app/db/repository.py` (depends on T017).
- [X] T022 [US2] Wire encounter capture into `backend/app/services/raids.py` so a successful `get_report_fights` persists merged distinct encounters via the upsert (depends on T020, T021).
- [X] T023 [P] [US2] Add an `Encounter` interface and `Raid.encounters` to `frontend/src/types.ts`.
- [X] T024 [US2] Update `frontend/src/components/Sidebar.tsx` to display the raid's own date **and** time from `report_started_at` (fallback `first_seen_at`/`last_asked_at` when null) plus a compact boss summary, themed (depends on T023, Foundational).

**Checkpoint**: Raid list shows correct date/time + boss, no duplicates.

---

## Phase 5: User Story 3 - PDF report that renders correctly (Priority: P2)

**Goal**: The PDF renders tables, headings, bulleted/numbered lists, wrapped long tokens, and graphs. *(Fully backend — independent of the Foundational migration.)*

**Independent Test**: Export a conversation with a table, lists, a long token, and a graph → all render legibly.

### Tests for User Story 3

- [X] T025 [P] [US3] Create `backend/tests/test_pdf_report.py`: `render_report_pdf` on content with a GFM table, headings, a bulleted list, a numbered list, a long unbroken token, and one captured graph returns non-empty `%PDF` bytes without raising.

### Implementation for User Story 3

- [X] T026 [US3] Run `gitnexus_impact` on `render_report_pdf` and `download_report` (upstream); report blast radius before editing `backend/app/services/pdf_report.py` and `backend/app/api/reports.py` (addresses analyze finding C1).
- [X] T027 [US3] Extend `_markdown_flowables` in `backend/app/services/pdf_report.py`: parse GFM pipe tables into a ReportLab `Table` (header style, cells as wrapping `Paragraph`s), recognize numbered (`1.`) and intro-line-plus-bullet lists, and set `wordWrap="CJK"` on body/cell styles (FR-011…014).
- [X] T028 [US3] Include each answer's originating user question as a context heading, by passing user messages through in `backend/app/api/reports.py` and rendering them in `render_report_pdf`.

**Checkpoint**: PDF renders all constructs correctly.

---

## Phase 6: User Story 4 - Boss focus checkboxes (Priority: P2)

**Goal**: Distinct bosses from a report's fight list render as checkboxes; selected bosses fold into the next prompt.

**Dependency note**: Reuses US2's `encounters_from_tool` (T020). Frontend tasks depend on Foundational.

**Independent Test**: Ask for a report's fights → boss checkboxes appear (repeats collapsed); select two + send → the next answer is scoped to those bosses.

### Tests for User Story 4

- [X] T029 [P] [US4] Extend `backend/tests/test_api.py`: a WS turn whose `get_report_fights` succeeds emits an `encounters` frame (deduped, non-empty); a turn with no qualifying encounters emits none.

### Implementation for User Story 4

- [X] T030 [P] [US4] Add `EncountersFrame` (`type:"encounters"`, `report_code`, `encounters: list[EncounterOut]`) to `backend/app/schemas.py` (per `contracts/websocket.md`).
- [X] T031 [US4] In `backend/app/api/ws.py` `_handle_tool_end`, after the `tool_end` for a successful `get_report_fights`, build the distinct list via `encounters_from_tool` and send an `EncountersFrame` only when non-empty (depends on T020, T030).
- [X] T032 [P] [US4] Add `{ type: "encounters"; report_code: string; encounters: Encounter[] }` to the `Frame` union in `frontend/src/api/wsClient.ts`.
- [X] T033 [US4] Create `frontend/src/components/EncounterPicker.tsx`: a themed checkbox group of distinct bosses, readable on narrow and wide widths (depends on Foundational).
- [X] T034 [US4] In `frontend/src/App.tsx` handle the `encounters` frame (attach to the surfacing turn), track checkbox selection, fold selected boss names into the next outgoing message text (visible, e.g. a trailing `(Focus on: …)`), reset per turn (FR-016…020; depends on T032).
- [X] T035 [US4] Render `EncounterPicker` under the sourcing agent turn in `frontend/src/components/MessageList.tsx` and add checkbox styles to `frontend/src/index.css` (depends on T033, T034).

**Checkpoint**: Boss checkboxes appear and focus the next prompt.

---

## Phase 7: User Story 5 - Warm Barnaby greeting on a new chat (Priority: P3)

**Goal**: A new chat shows a warm Barnaby greeting without user input, generated once at startup and cached.

**Independent Test**: Click New chat → greeting appears without typing; second+ new chats show it in < ~1s; the hidden kickoff is never shown.

### Tests for User Story 5

- [X] T036 [P] [US5] Create `backend/tests/test_greeting.py`: `get_greeting` returns a cached value on a hit, and a generation failure yields an empty/omitted greeting without raising.

### Implementation for User Story 5

- [X] T037 [US5] Create `backend/app/greeting.py` with async `get_greeting(app, model) -> str`: read/write `app.state.greeting_cache`, generating on miss by collecting `token` records from `stream_response` over a disposable session (`"greeting-<model>"`) with the hidden `"Greetings, Barnaby!"` kickoff.
- [X] T038 [P] [US5] Add `GreetingResponse { greeting: str }` to `backend/app/schemas.py`.
- [X] T039 [US5] Create `backend/app/api/greeting.py` (`GET /api/greeting?model=`, returns empty greeting on failure, never 500s) and mount its router in `backend/app/main.py` (depends on T037, T038).
- [X] T040 [US5] Prime the default model's greeting at startup in the `backend/app/main.py` lifespan, off the event loop (depends on T037).
- [X] T041 [P] [US5] Add `getGreeting(model?)` to `frontend/src/api/restClient.ts`.
- [X] T042 [US5] In `frontend/src/App.tsx` `newChat()`, fetch the greeting and inject it as a display-only agent message (no conversation row; kickoff never shown); if the user types first or the fetch fails, open a clean chat and ignore a late greeting (FR-021…025; depends on T041, Foundational).

**Checkpoint**: New chats greet promptly with graceful fallback.

---

## Phase 8: User Story 6 - High-fantasy UX polish (Priority: P1, app-wide)

**Goal**: One cohesive fixed fantasy theme, smooth inscribed streaming, spellcasting tool cards, ambient effects — reduced-motion aware and ~60 fps.

**Dependency note**: Requires the Foundational migration (Phase 2). Backend sub-tasks (T043–T047) are independent of Foundational and may be pulled earlier.

**Independent Test**: Load the app → one theme, smooth jitter-free streaming with no broken markdown, spell cards through summoning→casting→resolved/fizzled (incl. parallel + cached-fast cases), reduced-motion disables animation, streaming stays smooth.

### Backend (tool-call telemetry for resolved spell chips)

- [X] T043 [US6] Run `gitnexus_impact` on `stream_response` and `_handle_tool_end` (upstream); report blast radius before editing `backend/app/agent_runner.py` and `backend/app/api/ws.py`.
- [X] T044 [US6] Add optional `summary: str | None` and `ms: int | None` to `ToolEndFrame`, and an optional `ToolProgressFrame` (`id, done, total, note?`), in `backend/app/schemas.py` (per `contracts/websocket.md`).
- [X] T045 [US6] Time each tool call in `backend/app/agent_runner.py` `stream_response` and include elapsed `ms` (and the raw result for summarizing) in the `tool_end` record.
- [X] T046 [P] [US6] Create `backend/app/services/tool_summary.py`: a short (≤140 char) human-readable summary from a tool result (e.g. "DamageDone — 23 abilities, 1 player").
- [X] T047 [US6] Forward `summary` + `ms` on the `tool_end` frame in `backend/app/api/ws.py` `_handle_tool_end` (depends on T044, T045, T046).

### Frontend (streaming inscription)

- [X] T048 [P] [US6] Create `frontend/src/hooks/useSmoothText.ts`: adaptive rAF token-smoothing buffer (per `research.md` R9).
- [X] T049 [P] [US6] Create `frontend/src/lib/rehypeWordSpans.ts`: wrap words in `.ink` spans (skip code/pre).
- [X] T050 [US6] Integrate smoothing + ink-in + ember caret + completion flourish into `frontend/src/components/StreamMarkdown.tsx` / `MessageList.tsx`, with CSS keyframes (`ink-in`, `flicker`, sheen) in `frontend/src/index.css` (depends on T048, T049).

### Frontend (spellcasting tool cards)

- [X] T051 [P] [US6] Create `frontend/src/lib/spells.ts`: `SPELLS` registry mapping every real tool name (16 WCL tools + `web_search`) to icon/hue/verb/flavor, plus `DEFAULT_SPELL` (per `contracts/ui-polish.md`).
- [X] T052 [P] [US6] Create `frontend/src/components/RuneCircle.tsx` (pure-SVG rotating runes).
- [X] T053 [P] [US6] Create `frontend/src/components/CastBar.tsx` (indeterminate → determinate via `motion`).
- [X] T054 [US6] Create `frontend/src/components/SpellCard.tsx` (+ summoning orb): summoning → casting (RuneCircle + CastBar + rotating flavor) → resolved (burst → compact chip with `summary`+`ms`) / fizzled (shake + reason), minimum ~600 ms display (depends on T051, T052, T053).
- [X] T055 [US6] Add `tool_progress` + `tool_end` `summary`/`ms` to the `Frame` union in `frontend/src/api/wsClient.ts` and per-call spell state types in `frontend/src/types.ts` (depends on T044).
- [X] T056 [US6] In `frontend/src/App.tsx`, derive per-tool-call spell state from `tool_start`/`tool_progress`/`tool_end` frames, including parallel-call tracking keyed by call id (depends on T055).
- [X] T057 [US6] Render stacked/staggered `SpellCard`s (and persisted resolved chips) in `frontend/src/components/MessageList.tsx` using `motion` `layout` (depends on T054, T056).

### Frontend (ambient world + accessibility)

- [X] T058 [P] [US6] Create `frontend/src/components/Ambient.tsx`: drifting blurred gradients + capped `@tsparticles/react` (+ `@tsparticles/slim`) + grain/vignette overlays (install the particle deps).
- [X] T059 [US6] Mount `Ambient` and apply reduced-motion handling (`useReducedMotion()` / `prefers-reduced-motion`) across ink/rotation/particles/bursts, and pause particles on `document.hidden`, in `frontend/src/App.tsx` + `frontend/src/index.css` (FR-034, SC-010; depends on T058).
- [X] T060 [US6] Add a game-icons.net CC BY 3.0 attribution line (footer/about) in `frontend/src/App.tsx` (FR-035).

**Checkpoint**: The whole app presents one cohesive fantasy theme with smooth streaming and spell cards; reduced-motion and 60 fps hold.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T061 [P] Update `README.md` / `AGENTS.md`: source links, raid date/boss, boss checkboxes, greeting, and the new theme/stack (React 19 + Tailwind v4 + shadcn; background toggle removed).
- [X] T062 Run `uv run pytest -q` — all backend tests (US2–US6) green.
- [X] T063 `cd frontend && npm run build`; perform the reduced-motion pass and a ~60 fps streaming spot check per `quickstart.md`.
- [ ] T064 Walk through `specs/004-raid-sourcing-ux/quickstart.md` — verify US1–US6 manually.
- [X] T065 Run `gitnexus_detect_changes()` before committing to confirm only expected symbols/flows changed (per CLAUDE.md).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)**: none.
- **Foundational (P2, stack migration)**: blocks all **frontend** work (US6 and the frontend parts of US1/US2/US4/US5). Backend-only slices do not depend on it.
- **US1–US5**: backend parts depend only on Setup; frontend parts depend on Foundational. **US4 also depends on US2's `encounters_from_tool` (T020).**
- **US6**: backend sub-tasks (T043–T047) depend only on Setup; frontend sub-tasks depend on Foundational.
- **Polish (P9)**: after the desired stories are complete.

### Recommended order

Setup → **Foundational** → US1 → US2 → US3 → US4 → US5 → US6 → Polish. In priority terms the P1s
are US1, US2, US6; US6's visual layer is sequenced last only because it rides the Foundational
migration. Pull backend slices (US2/US3/US4-backend/US5-backend/US6-backend) in parallel with the
Foundational migration if staffed.

### Within each story

- Tests (where present) before implementation.
- Models/schemas before services; services before endpoints/frame emission; backend before the frontend that consumes it.

### Parallel opportunities

- US2 tests T014, T015 together; T019 (schema) + T023 (types) alongside.
- US4: T030 (schema) + T032 (Frame union) + T033 (component) + T029 (test) can start together.
- US5: T036 (test) + T038 (schema) + T041 (restClient) together.
- US6 backend: T046 parallel with T044/T045 setup. US6 frontend new files T048, T049, T051, T052, T053, T058 are all `[P]`.

### Same-file sequencing (do NOT parallelize across these)

- `backend/app/schemas.py`: T019 (US2), T030 (US4), T038 (US5), T044 (US6).
- `backend/app/main.py`: T018 (US2), T039/T040 (US5).
- `backend/app/api/ws.py`: T031 (US4), T047 (US6).
- `frontend/src/App.tsx`: T008 (Found), T034 (US4), T042 (US5), T056/T059/T060 (US6).
- `frontend/src/components/MessageList.tsx`: T006/T007 (Found), T035 (US4), T050/T057 (US6).
- `frontend/src/components/StreamMarkdown.tsx`: T006 (Found), T012 (US1), T050 (US6).
- `frontend/src/index.css`: T003/T005 (Found), T013 (US1), T035 (US4), T050/T059 (US6).
- `frontend/src/types.ts`: T023 (US2), T055 (US6).
- `frontend/src/api/wsClient.ts`: T032 (US4), T055 (US6).

---

## Implementation Strategy

### MVP first

Setup → Foundational → **US1** (source links) is the fastest demoable increment on the new stack.
US2 and US6 are the other P1s. US3 (PDF) is pure backend and can ship independently at any time.

### Incremental delivery

Setup → Foundational (verify build+stream) → US1 → US2 → US3 → US4 (after US2) → US5 → US6 →
Polish, validating each story against `quickstart.md` before moving on.

### Risk note

The Foundational phase (React 18→19 + Tailwind v4 + shadcn + renderer swap) is the single
highest-risk, highest-churn effort. Keep it isolated and green (T009) before building feature or
visual UI on top; if it slips, the backend-only slices (US2/US3/US4-backend/US5-backend) still
deliver value independently.

## Notes

- `[P]` = different files, no incomplete-task dependency.
- Per CLAUDE.md: run `gitnexus_impact` before each backend symbol edit (T010, T016, T026, T043) and `gitnexus_detect_changes` before committing (T065). Frontend TS may be outside the index — apply the same care manually.
- Commit after each task or logical group.
