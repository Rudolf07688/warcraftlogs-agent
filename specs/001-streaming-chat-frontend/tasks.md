---
description: "Task list for Streaming Chat Frontend"
---

# Tasks: Streaming Chat Frontend

**Input**: Design documents from `/specs/001-streaming-chat-frontend/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not mandated by the spec. A small optional backend test task is included in
Polish; skip if not wanted.

**Organization**: Tasks are grouped by user story (US1–US4) for independent delivery.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: User story the task belongs to (US1–US4)

## Path Conventions

- Existing agent core (reused unchanged): `wcl_agent/`
- Backend: `backend/app/...`, tests in `backend/tests/`
- Frontend: `frontend/src/...`
- Orchestration: `docker-compose.yml`, `.env.example` at repo root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and scaffolding for backend, frontend, and local orchestration.

- [X] T001 Bump Python to 3.14: set `.python-version` to `3.14`, `requires-python = ">=3.14"` in `pyproject.toml`, and verify `uv sync` succeeds
- [X] T002 Add backend dependencies via uv in `pyproject.toml`: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `pydantic-settings` (keep existing `google-adk`, `requests`, `pandas`, `python-dotenv`)
- [X] T003 [P] Create backend package skeleton with `__init__.py` files: `backend/app/`, `backend/app/api/`, `backend/app/db/`, `backend/tests/`
- [X] T004 [P] Scaffold the frontend (React + Vite + TypeScript) in `frontend/`: `package.json`, `index.html`, `vite.config.ts`, `tsconfig.json`, `src/main.tsx`
- [X] T005 [P] Add `DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and a `WCL_MODELS`/`WCL_DEFAULT_MODEL` allow-list to `.env.example`
- [X] T006 [P] Create `backend/Dockerfile` (Python 3.14 + uv) and `frontend/Dockerfile` (Node + Vite)
- [X] T007 Create `docker-compose.yml` with `db` (`postgres:17`, named volume, healthcheck), `backend` (`env_file: .env`, `depends_on: db healthy`, read-only mount of host ADC → `GOOGLE_APPLICATION_CREDENTIALS`), and `frontend`; wire `DATABASE_URL` to the `db` service

**Checkpoint**: `docker compose config` validates; empty backend/frontend images build.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core config, persistence, schemas, app wiring, and the agent-streaming bridge that ALL user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T008 Implement `backend/app/config.py` using `pydantic-settings` to read env vars (`DATABASE_URL`, `WCL_*`, `GOOGLE_*`, model allow-list + default); source-agnostic so local `.env` and Secret Manager both work (FR-017)
- [X] T009 Implement `backend/app/db/session.py`: async engine + `async_sessionmaker` from `DATABASE_URL` (asyncpg)
- [X] T010 Implement `backend/app/db/models.py`: SQLAlchemy `Conversation` and `Message` models per data-model.md (UUID PKs, `role` enum, `seq`, timestamps, cascade, indexes) — depends on T009
- [X] T011 Implement `backend/app/db/repository.py`: async helpers — create/get/list/delete conversation, append message (auto `seq`), list messages ordered, bump `updated_at` — depends on T010
- [X] T012 [P] Implement `backend/app/schemas.py`: Pydantic models for WS frames (client turn; server `meta`/`tool_start`/`tool_end`/`token`/`done`/`error`) and REST bodies per `contracts/` (constitution IV)
- [X] T013 Implement `backend/app/main.py`: FastAPI app + lifespan (init engine, create tables on startup), CORS for the local frontend origin, router includes, and `GET /health` — depends on T008, T009
- [X] T014 Implement `backend/app/agent_runner.py`: build an ADK `Agent` for a given model id (reusing `wcl_agent` tools), cache one `Runner` per model, and expose an async generator that maps `Runner.run_async` events → stream frames; run the sync WCL tools via `asyncio.to_thread` so parallel calls overlap — depends on T008
- [X] T015 Enable parallel tool calls: set ADK `RunConfig` for parallel function calling and reinforce "retrieve independent Warcraft Logs data concurrently" in the agent instruction used by `agent_runner.py` (FR-005) — depends on T014

**Checkpoint**: `GET /health` returns ok against the compose `db`; agent_runner streams frames for a hardcoded message in a scratch test.

---

## Phase 3: User Story 1 - Stream a conversation with the agent (Priority: P1) 🎯 MVP

**Goal**: User sends a question and the agent's answer appears incrementally; multi-lookup questions retrieve data concurrently.

**Independent Test**: Ask "How are hunters performing on Heroic Ula'tek?" and confirm the reply begins < 2s and visibly streams in; a compare-all-specs question overlaps lookups.

- [X] T016 [US1] Implement WebSocket `GET /ws/chat` in `backend/app/api/ws.py`: validate the client turn, create-or-load the conversation, rebuild the ADK session from stored messages, stream frames from `agent_runner`, and persist the user message then the final agent message — depends on T011, T012, T014
- [X] T017 [US1] Include the ws router in `backend/app/main.py` and reject a second concurrent turn on the same socket with an `error` frame (`code: "busy"`)
- [X] T018 [P] [US1] Implement `frontend/src/api/wsClient.ts`: open the socket, send a turn, parse frames, and surface token/tool/done/error callbacks
- [X] T019 [US1] Implement `frontend/src/components/ChatWindow.tsx`, `MessageList.tsx`, and `Composer.tsx`: send on submit, append `token` text live to the in-progress agent message, show a working indicator until streaming starts — depends on T018
- [X] T020 [US1] Wire a minimal `frontend/src/App.tsx` (single in-memory conversation) to demonstrate end-to-end streaming — depends on T019

**Checkpoint**: Streaming chat works end-to-end via `docker compose up` (MVP deliverable).

---

## Phase 4: User Story 2 - Select the AI model (Priority: P2)

**Goal**: User picks the model; it applies to subsequent messages.

**Independent Test**: Select a model, send a message (confirm it is used), switch model, confirm the next message uses the new one.

- [X] T021 [US2] Implement `GET /api/models` in `backend/app/api/models.py` returning the allow-list + default from config — depends on T008
- [X] T022 [US2] In `backend/app/api/ws.py`, validate the turn's `model` against the allow-list (error frame `invalid_model`) and pass it to the per-model runner cache — depends on T016, T021
- [X] T023 [P] [US2] Implement `frontend/src/api/restClient.ts` `getModels()` and a `frontend/src/components/ModelSelect.tsx` dropdown
- [X] T024 [US2] Wire the selected model into the ws turn payload and apply it from the next message onward — depends on T023, T018

**Checkpoint**: Model selection changes the model used for the next response.

---

## Phase 5: User Story 3 - Revisit previous chats from a sidebar (Priority: P2)

**Goal**: Sidebar lists prior conversations; selecting one reopens full history; persists across restarts.

**Independent Test**: Hold a chat, start a new one, see both listed; restart backend; confirm both persist and reopen with full history.

- [X] T025 [US3] Implement `backend/app/api/conversations.py`: `GET /api/conversations` (list, most-recent-first), `POST` (create), `GET /{id}` (with messages), `DELETE /{id}` — depends on T011, T012
- [X] T026 [US3] Include the conversations router in `backend/app/main.py`
- [X] T027 [P] [US3] Add conversation methods (list/get/create/delete) to `frontend/src/api/restClient.ts`
- [X] T028 [US3] Implement `frontend/src/components/Sidebar.tsx`: list conversations, "New chat", select, and delete — depends on T027
- [X] T029 [US3] Load a selected conversation's messages into `ChatWindow`, and create a conversation on first message when none is active — depends on T028, T020

**Checkpoint**: Conversations persist and are browsable across restarts.

---

## Phase 6: User Story 4 - Basic, dark-mode chat interface (Priority: P3)

**Goal**: Simple dark-themed layout (sidebar + message area + input).

**Independent Test**: Load the app; confirm dark theme, readable chat area, scrolling that keeps the latest message in view.

- [X] T030 [P] [US4] Add dark theme via CSS variables and base layout (sidebar + chat + composer) in `frontend/src/styles.css` (imported in `main.tsx`)
- [X] T031 [US4] Make the message area scrollable and auto-scroll to the latest message in `frontend/src/components/MessageList.tsx`
- [X] T032 [P] [US4] Style empty/loading/error states (working indicator, disconnected banner, agent-error message) across the frontend components

**Checkpoint**: A clean, dark, basic UI over the functional stack.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Hardening, docs, and validation across all stories.

- [X] T033 [P] Error-handling pass: WebSocket reconnect/disconnect UX in `frontend/src/api/wsClient.ts` + friendly `agent_error`/`upstream_error` messaging (spec Edge Cases, SC-007)
- [X] T034 [P] (Optional) Backend tests in `backend/tests/` with pytest-asyncio + httpx: `/health`, `/api/models`, conversation CRUD, and a `/ws/chat` streaming smoke test
- [X] T035 [P] Update `README.md` and ensure `specs/001-streaming-chat-frontend/quickstart.md` matches the final run steps (`docker compose up`)
- [ ] T036 Validate the full stack against Success Criteria SC-001–SC-007 using quickstart.md (streaming latency, parallel speedup, persistence across restart, model switch, single-command bring-up, interruption handling)
- [X] T037 [P] Document the design-for-later Cloud Run + Cloud SQL + Secret Manager deployment (ADC service account, env-var secret source, WebSocket session affinity) in `documentation/` per research.md §9

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately.
- **Foundational (Phase 2)**: depends on Setup — **BLOCKS all user stories**.
- **User Stories (Phase 3–6)**: all depend on Foundational.
  - US1 (P1) is the MVP and has no dependency on other stories.
  - US2 (P2) and US3 (P2) depend only on Foundational; they build on US1's UI shell
    in practice but are independently testable.
  - US4 (P3) is styling over the existing UI.
- **Polish (Phase 7)**: after the desired stories are complete.

### Story Dependencies

- **US1**: Foundational only → MVP.
- **US2**: Foundational (+ reuses the ws turn from US1) — independently testable.
- **US3**: Foundational (+ reuses the ChatWindow from US1) — independently testable.
- **US4**: existing frontend components (US1) — cosmetic, independent.

### Within Each Story

- Backend endpoint before the frontend that calls it; models/repository before endpoints (done in Foundational).

### Parallel Opportunities

- Setup: T003, T004, T005, T006 can run in parallel (different trees).
- Foundational: T012 (schemas) parallel with T009–T011 (db) once T008 exists.
- US1: T018 (wsClient) parallel with backend T016/T017.
- US2: T023 (frontend) parallel with backend T021.
- US3: T027 (frontend restClient) parallel with backend T025.
- US4: T030 and T032 parallel.
- Polish: T033, T034, T035, T037 parallel.

---

## Parallel Example: User Story 1

```bash
# Backend and frontend client in parallel once Foundational is done:
Task: "T016 [US1] Implement WebSocket /ws/chat in backend/app/api/ws.py"
Task: "T018 [P] [US1] Implement frontend/src/api/wsClient.ts"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1: Setup → 2. Phase 2: Foundational → 3. Phase 3: US1.
4. **STOP and VALIDATE**: streaming chat works end-to-end via `docker compose up`.
5. Demo the MVP.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → streaming chat (MVP) → demo.
3. US2 → model selection → demo.
4. US3 → persistent history sidebar → demo.
5. US4 → dark/basic polish → demo.
6. Polish → hardening + deployment notes.

## Notes

- Tests (T034) are optional — the spec did not mandate TDD; include if desired.
- Keep config env-var based and Google auth via ADC so the future Cloud Run move
  needs no code changes (clarified decisions; research.md §9).
- The existing `wcl_agent/` package is reused unchanged (constitution: DRY).
