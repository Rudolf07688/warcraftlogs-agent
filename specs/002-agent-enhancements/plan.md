# Implementation Plan: Agent App Enhancements

**Branch**: `002-agent-enhancements` | **Date**: 2026-10-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-agent-enhancements/spec.md`

## Summary

Five enhancements layered onto the existing `001-streaming-chat-frontend` app (FastAPI
+ asyncio backend, PostgreSQL via async SQLAlchemy, React frontend, reused `wcl_agent`
ADK core):

1. **Tracked raids (P1)** — automatically record a raid when the agent *successfully
   retrieves* a Warcraft Logs report, show them in a dedicated sidebar section
   (most-recent-first), and let a click open a new chat that auto-asks the agent to
   investigate that raid.
2. **Durable sessions & full persistence (P1)** — persist the agent session so
   conversation *context* (not just the transcript) survives a backend restart, and
   persist partial output on interruption.
3. **Web access via native grounding (P2)** — enable the model's native grounding
   (Gemini Google Search on Vertex); non-grounding models degrade gracefully.
4. **Dynamic, validated model list (P2)** — at startup, discover candidate Gemini &
   Anthropic models on Vertex and keep only those that pass a responsiveness probe.
5. **PDF export (P3)** — download a PDF of the current conversation: the written
   analysis plus charts rendered from the graph data the agent retrieved.

The unifying technical thread: the ADK agent runner is upgraded to surface **tool
call arguments and result status** (not just names). That single change feeds raid
detection (US1), graph capture for PDF (US5), and richer tool framing — one source
of truth (DRY, Principle I).

## Technical Context

**Language/Version**: Python 3.14 (already pinned in `.python-version` /
`requires-python`; the 001 follow-up is resolved). Frontend TypeScript + React.

**Primary Dependencies**: Existing — FastAPI, Uvicorn, `google-adk`, async SQLAlchemy
2.0 + asyncpg, Pydantic v2 / pydantic-settings, React + Vite. **New** — ADK
`DatabaseSessionService` (persistent sessions; sync driver `psycopg[binary]`),
Anthropic-on-Vertex model support for ADK (`google-adk[anthropic]` / `anthropic[vertex]`
via ADK's model registry), a PDF generator (`reportlab`) + chart renderer
(`matplotlib`; `pandas` already present), and `markdown` for analysis rendering.

**Storage**: PostgreSQL 17. Existing `conversations` / `messages` tables reused.
**New** `tracked_raids` table and `captured_graphs` table (graph JSON captured per
conversation for PDF). ADK's `DatabaseSessionService` creates/owns its own session
tables in the same database.

**Testing**: pytest + pytest-asyncio + httpx AsyncClient (backend). New coverage:
raid upsert/dedup, session restore after restart, model-validation fallback, PDF
endpoint happy path + no-graphs path. Frontend remains manual for v2.

**Target Platform**: Local Docker Compose (Linux containers) + modern browser;
production path (Cloud Run + Cloud SQL + Secret Manager) unchanged from 001.

**Project Type**: Web application (backend + frontend) over the existing `wcl_agent`
package.

**Performance Goals**: Model discovery/validation runs once at startup (not on the
request path — per clarification); selector serves a cached set instantly. PDF
generation for a typical conversation completes in a few seconds and runs off the
event loop (`asyncio.to_thread`). Streaming latency unchanged from 001 (first token
< 2s).

**Constraints**: asyncio throughout the request path; all blocking work
(DatabaseSessionService calls, matplotlib/reportlab rendering, startup model probes)
offloaded via `asyncio.to_thread` so the event loop never stalls (Principle V).
Single-user, no auth (unchanged). Secrets from root `.env` locally.

**Scale/Scope**: Single local user; low request volume; a few dozen tracked raids and
conversations. No horizontal-scale concerns.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How this plan complies |
|-----------|--------|------------------------|
| I. Strict DRY & Reuse-First | ✅ | One agent-runner change feeds raid detection + graph capture + tool framing; reuses existing `WCLClient`, `report_tools`, repository, and `messages` table; `build_agent` stays the single agent factory. |
| II. Methodical, Step-Wise Delivery | ✅ | Delivered per user story (P1 persistence+raids → P2 grounding+models → P3 PDF), each independently testable and shippable. |
| III. Simplicity First (YAGNI) | ✅ | Startup-only model validation (no background refresh); candidate-list + probe instead of a bespoke Vertex catalog crawler; `reportlab`+`matplotlib` over heavyweight HTML/PDF stacks; no new abstractions beyond two small tables + one service module each. |
| IV. Typed Data Contracts | ✅ | New Pydantic models for raid list, model list, and PDF request/response; SQLAlchemy models for new tables; richer WS tool frames stay typed. |
| V. Async Python Backend | ✅ | All new endpoints are `async def`; the one sync dependency (ADK `DatabaseSessionService`) and CPU-bound PDF/chart rendering + startup probes run via `asyncio.to_thread`. |
| VI. Repo Awareness via GitNexus | ✅ | Existing call graph reviewed before planning (agent_runner, ws, repository, report_tools, config); GitNexus impact checks to run before editing shared symbols (`build_agent`, `stream_response`, `_get_runner`). |
| Stack standards (uv, 3.14, FastAPI, Pydantic, React, Postgres 17) | ✅ | All adopted; Python already 3.14; new deps added via `uv add`. |

**Gate result**: PASS. Two justified complexities tracked below (a second, sync DB
driver for ADK session persistence; CPU-bound PDF rendering).

## Project Structure

### Documentation (this feature)

```text
specs/002-agent-enhancements/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── rest-api.md      # new/changed REST endpoints (raids, models, pdf)
│   └── websocket.md     # enriched tool frames + grounding/partial frames
└── checklists/
    └── requirements.md  # From /speckit-specify
```

### Source Code (repository root)

```text
wcl_agent/                      # EXISTING agent core
├── agent.py                    # CHANGE: model registry (Gemini + Anthropic-on-Vertex);
│                               #         optional grounding tool wiring
├── report_tools.py             # REUSE; ADD get_report_metadata(report_code) helper
│                               #         (title/zone/guild/startTime for raid labels)
└── models.py                   # NEW (small): model-discovery + "hello"/health probe

backend/
├── app/
│   ├── main.py                 # CHANGE: startup model validation into app.state;
│   │                           #         DatabaseSessionService lifecycle
│   ├── config.py               # CHANGE: candidate model lists + sync DB URL derive
│   ├── schemas.py              # CHANGE: RaidOut/RaidListResponse; richer tool frames;
│   │                           #         GroundingFrame; PDF request params
│   ├── agent_runner.py         # CHANGE: DatabaseSessionService; yield tool args+status;
│   │                           #         emit grounding metadata
│   ├── services/
│   │   ├── raids.py            # NEW: detect report retrievals -> upsert tracked raids
│   │   ├── graphs.py           # NEW: capture graph tool outputs for a conversation
│   │   └── pdf_report.py       # NEW: build PDF (markdown analysis + matplotlib charts)
│   ├── api/
│   │   ├── ws.py               # CHANGE: persist partial on interruption; feed capture
│   │   ├── conversations.py    # REUSE
│   │   ├── raids.py            # NEW: GET /api/raids ; POST /api/raids/{code}/investigate
│   │   ├── models.py           # CHANGE: serve validated set from app.state
│   │   └── reports.py          # NEW: GET /api/conversations/{id}/report.pdf
│   └── db/
│       ├── models.py           # CHANGE: TrackedRaid, CapturedGraph models
│       └── repository.py       # CHANGE: raid upsert/list; graph capture/list; partial msg
│
frontend/src/
├── App.tsx                     # CHANGE: raids state + click->investigate; PDF button
├── components/
│   ├── Sidebar.tsx             # CHANGE: add "Raids" section (label + last-asked time)
│   ├── RaidList.tsx            # NEW (optional split): tracked-raids rendering
│   └── MessageList.tsx         # CHANGE: grounding indicator; PDF download affordance
├── api/restClient.ts           # CHANGE: getRaids / investigateRaid / downloadReport
└── types.ts                    # CHANGE: Raid type; grounding flag

docker-compose.yml              # CHANGE (if needed): system libs for matplotlib/reportlab
```

**Structure Decision**: Continue the 001 web-app layout. New backend logic lands in a
`backend/app/services/` package (raids, graphs, pdf_report) to keep routers thin and
the agent runner focused — each service is a small, single-concern module. The agent
core (`wcl_agent/`) gains only a model registry and one metadata helper; it is not
forked.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Second (sync) DB driver `psycopg` alongside async `asyncpg` | ADK's persistent `DatabaseSessionService` is sync-only; it is the idiomatic, single-source way to persist agent sessions keyed by session id (todo item 2) and restore true context after restart (FR-006/007/008). Runs via `asyncio.to_thread`. | Hand-rolling context re-seeding by replaying the `messages` transcript into a fresh in-memory session avoids the driver but reconstructs only visible text (loses tool/grounding context), duplicates what ADK already does, and is more code to maintain. Rejected as both weaker and less DRY. |
| CPU-bound PDF + chart rendering in-process | PDF export (US5) must render charts from captured graph JSON; `matplotlib` + `reportlab` are the simplest, dependency-light way. Offloaded via `asyncio.to_thread` so the event loop isn't blocked. | A separate render microservice or headless-browser (WeasyPrint/Chromium) HTML→PDF path adds heavy system deps and an extra moving part for a single-user local app. Rejected per YAGNI. |

**Carried context from 001 (unchanged)**: ADC for Google auth everywhere; Cloud Run +
Cloud SQL 17 + Secret Manager in production; public/unauthenticated v1; config stays
env-var based so only the secret *source* changes per environment.
