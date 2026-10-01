# Implementation Plan: Streaming Chat Frontend

**Branch**: `001-streaming-chat-frontend` | **Date**: 2026-10-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-streaming-chat-frontend/spec.md`

## Summary

Add a browser frontend and an async backend that surface the existing Warcraft
Logs agent as a live, streaming chat. A **React** single-page app (basic, dark,
with a conversation sidebar, model selector, and chat box) talks to a **FastAPI +
asyncio** backend over a **WebSocket**, so agent replies render incrementally as
they are generated. The backend wraps the existing `wcl_agent` core, builds the
agent with a **caller-selected model**, executes Warcraft Logs **tool calls
concurrently**, and persists conversations/messages in **PostgreSQL 17**. The whole
stack runs locally via **Docker Compose**, sourcing secrets from the root `.env`.
Scope is intentionally basic (single user, no auth) per direction — "we'll improve
later".

## Technical Context

**Language/Version**: Backend Python 3.14 (per constitution); Frontend TypeScript +
React. (See Complexity Tracking: repo currently pins 3.13 — reconcile to 3.14.)

**Primary Dependencies**: FastAPI, Uvicorn, `google-adk` (existing agent), SQLAlchemy
2.0 async + asyncpg, Pydantic v2 + pydantic-settings; React + Vite; existing
`wcl_agent` package (reused verbatim as the agent core).

**Storage**: PostgreSQL 17 (conversations + messages; app state over time).

**Testing**: pytest + pytest-asyncio + httpx AsyncClient for the backend
(happy-path + streaming contract). Frontend manual for v1 (basic UI). Tests kept
light — spec did not mandate TDD.

**Target Platform**: Local Docker Compose (Linux containers) + modern browser.

**Project Type**: Web application (frontend + backend) layered on the existing
Python agent package.

**Performance Goals**: First streamed token visible < 2s for typical questions
(SC-001); concurrent WCL retrieval ≥ 40% faster than sequential for 3+ lookups
(SC-003); incremental rendering perceivable (SC-002).

**Constraints**: asyncio throughout the request path (FastAPI async handlers,
non-blocking I/O); WebSocket streaming; single-user, no auth (v1); keep frontend
basic; secrets only from root `.env`.

**Scale/Scope**: Single local user; a handful of concurrent conversations; low
request volume. No horizontal-scale concerns in v1.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How this plan complies |
|-----------|--------|------------------------|
| I. Strict DRY & Reuse-First | ✅ | Reuses the `wcl_agent` core, single `WCLClient`, and the existing tool set unchanged; one source of truth for queries/constants. |
| II. Methodical, Step-Wise Delivery | ✅ | Delivered by user story (P1 streaming → P2 model select / history → P3 UI polish), each independently testable. |
| III. Simplicity First (YAGNI) | ✅ | Single user, no auth, plain React (no heavy UI lib), own minimal DB schema; deeper async/scale deferred. |
| IV. Typed Data Contracts | ✅ | Pydantic models for all WS frames + REST bodies; SQLAlchemy models for persistence; dataclasses for internal config. |
| V. Async Python Backend | ✅ | FastAPI async endpoints + WebSocket; async DB (asyncpg); blocking WCL calls offloaded via `asyncio.to_thread` so parallel tool calls truly overlap. |
| VI. Repo Awareness via GitNexus | ✅ | Existing code paths (`wcl_agent/agent.py`, `tools.py`, `report_tools.py`, `cli.py`) reviewed before reuse; GitNexus available for impact checks during implementation. |
| Stack standards (uv, 3.14, FastAPI, Pydantic, React, Postgres 17) | ⚠️ | All adopted; **Python 3.14** pin reconciliation is the one open item (see Complexity Tracking). |

**Gate result**: PASS (no unjustified violations). One tracked follow-up: Python
3.13 → 3.14 pin.

## Project Structure

### Documentation (this feature)

```text
specs/001-streaming-chat-frontend/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (WS + REST contracts)
│   ├── websocket.md
│   └── rest-api.md
└── checklists/
    └── requirements.md  # From /speckit-specify
```

### Source Code (repository root)

```text
wcl_agent/               # EXISTING agent core — reused unchanged (agent, tools, client)

backend/                 # NEW — FastAPI service wrapping the agent
├── app/
│   ├── main.py          # FastAPI app + lifespan (DB pool, model/runner cache)
│   ├── config.py        # pydantic-settings (reads root .env)
│   ├── schemas.py       # Pydantic: WS frames + REST request/response models
│   ├── agent_runner.py  # Build agent for a model + stream ADK events -> async gen
│   ├── api/
│   │   ├── ws.py        # WebSocket /ws/chat (streaming)
│   │   ├── conversations.py  # REST CRUD for conversations/messages
│   │   └── models.py    # REST: list selectable models; GET /health
│   └── db/
│       ├── session.py   # async engine/session factory
│       ├── models.py    # SQLAlchemy: Conversation, Message
│       └── repository.py# data-access helpers
├── tests/               # pytest-asyncio (streaming + CRUD happy paths)
└── Dockerfile

frontend/                # NEW — basic React (Vite + TS), dark mode
├── src/
│   ├── main.tsx / App.tsx
│   ├── api/ (restClient.ts, wsClient.ts)
│   └── components/ (Sidebar, ChatWindow, MessageList, Composer, ModelSelect)
├── index.html
├── package.json
└── Dockerfile

docker-compose.yml       # NEW — db (postgres:17) + backend + frontend; env_file: .env
```

**Structure Decision**: Web-app layout (`backend/` + `frontend/`) layered on the
existing root `wcl_agent/` package, which the backend imports directly (DRY). The
agent core is **not** forked or copied.

## Complexity Tracking

> Only the one constitution follow-up; no architectural violations to justify.

| Item | Why | Resolution |
|------|-----|-----------|
| Python pin 3.13 → 3.14 | Constitution mandates 3.14; repo pinned 3.13 earlier for wheel caution. | **Decided (clarified): Python 3.14.** During Setup bump `.python-version`/`requires-python` to 3.14 and verify `uv sync` + the backend image build. |
| Blocking WCL calls under async | Existing tools use sync `requests`; true async (httpx) is more work. | v1 keeps sync tools but runs them via `asyncio.to_thread` so parallel tool calls overlap and the event loop isn't blocked. Native async client deferred (documented in research.md). |

**Deployment decisions (clarified 2026-10-01)** — design for these now (see
research.md §6): ADC for Google auth in all environments (mounted ADC locally,
attached **service account** on Cloud Run); production on **Cloud Run** with **Cloud
SQL for PostgreSQL 17** and secrets from **Google Secret Manager**; the public
Cloud Run deployment is intentionally **unauthenticated for v1** (accepted risk).
Config is env-var based so only the secret *source* changes between environments.
