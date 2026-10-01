# Phase 0 Research: Streaming Chat Frontend

All decisions favor the simplest approach that satisfies the spec (constitution
Principle III). "Improve later" items are explicitly noted.

## 1. Agent ↔ frontend streaming protocol

**Decision**: Use a **WebSocket** endpoint (`/ws/chat`). The client sends one JSON
message per user turn; the server streams JSON frames back
(`token` / `tool_start` / `tool_end` / `done` / `error`). The frontend appends
`token` text to the in-progress agent message so it grows live.

**Rationale**: Explicitly requested; bidirectional and a natural fit for
incremental token delivery; one long-lived connection avoids per-chunk HTTP
overhead. ADK's `Runner.run_async` already yields intermediate events (partial
text + tool-call events) that map cleanly onto stream frames.

**Alternatives considered**: Server-Sent Events (simpler, one-way) — rejected
because the user asked for WebSockets and we want room for client→server control
frames later. Plain HTTP + polling — rejected (no real streaming).

## 2. Driving ADK streaming from FastAPI

**Decision**: In `agent_runner.py`, run the ADK `Runner` with
`RunConfig(streaming_mode=StreamingMode.SSE)` and iterate `run_async(...)`. For
each event: emit partial `event.content.parts[].text` as `token` frames; emit
`function_call` / `function_response` as `tool_start` / `tool_end`; on
`event.is_final_response()` emit `done`. Wrap the whole turn in try/except → `error`
frame.

**Rationale**: Reuses the exact event loop already proven in `wcl_agent/cli.py`
(which inspects `function_call` and `is_final_response`), just redirected from
`print()` to WebSocket frames — DRY.

**Alternatives**: Non-streaming (await full response) — rejected (violates SC-002).

## 3. Dynamic model selection

**Decision**: The agent's model is chosen per request. `agent_runner.py` builds an
ADK `Agent` with `model=<requested id>` and the existing tool list, caching one
`Runner` per model id (small `dict`). `GET /api/models` returns the configured
allow-list (from settings, default includes the current `gemini-3.6-flash`); the
backend accepts any id in the allow-list and passes it straight to ADK.

**Rationale**: ADK accepts a model-id string directly for Gemini/Vertex, so
supporting a new model (e.g. `gemini-3.7-flash`) is configuration-only — meeting
FR-007/FR-008. Caching runners avoids rebuilding the agent each turn.

**Alternatives**: One hardcoded agent (today's `root_agent`) — rejected (no model
switching). LiteLLM multi-provider — deferred; Vertex/Gemini is the current target.

## 4. Parallel Warcraft Logs tool calls

**Decision**: Keep the existing **sync** tools, but have the backend execute tool
calls **off the event loop via `asyncio.to_thread`**, and rely on Gemini **parallel
function calling** (the model emits multiple function calls in one turn) so ADK runs
them concurrently. Net effect: a question needing several WCL lookups fires them in
parallel threads instead of serially.

**Rationale**: Satisfies FR-005 / SC-003 with minimal change — no rewrite of the
15 existing tools. The agent instruction already encourages gathering data; we
reinforce "retrieve independent data in parallel" in the instruction.

**Improve later**: Convert `WCLClient` to an async `httpx.AsyncClient` for true
async I/O and lower overhead than threads. Documented, not done in v1.

## 5. Persistence (PostgreSQL 17)

**Decision**: Own minimal schema via **SQLAlchemy 2.0 async + asyncpg**: two tables
`conversations` and `messages` (see data-model.md). On each user turn the backend
(a) loads the conversation's prior messages from the DB, (b) reconstructs an ADK
in-memory session from them, (c) runs the turn, (d) persists the user message and
the final agent message. Conversations list/open/delete via REST.

**Rationale**: Owning the schema keeps history queryable for the sidebar and
survives restarts (FR-012/SC-004) while staying simple. Reconstructing the ADK
session from stored messages avoids needing a persistent ADK session backend in v1.

**Alternatives**: ADK `DatabaseSessionService` (persist ADK sessions directly) —
deferred; it couples our storage to ADK's internal schema and gives less control
over the sidebar/title data. Revisit if session fidelity (tool traces) must persist.

## 6. Local Docker Compose + root `.env`

**Decision**: `docker-compose.yml` with three services:
- `db`: `postgres:17`, named volume, healthcheck.
- `backend`: FastAPI/uvicorn image built from `backend/Dockerfile`; `env_file: .env`
  (root), `depends_on: db (healthy)`; `DATABASE_URL` points at the `db` service.
- `frontend`: Vite dev server (or built static) from `frontend/Dockerfile`;
  proxies/points to the backend.

Secrets come from the root `.env` via `env_file`. Add `DATABASE_URL` (and keep
`WCL_*`, `GOOGLE_*`) to `.env.example`.

**Google auth = ADC everywhere (clarified)**: ADC lives in `~/.config/gcloud` on the
host, not in `.env`. For local testing, **mount the host ADC file read-only** into the
backend container and set `GOOGLE_APPLICATION_CREDENTIALS` to it:
`~/.config/gcloud/application_default_credentials.json:/gcp/adc.json:ro`. No API key
and no credential file in the repo (FR-016). Documented in quickstart.md.

**Rationale**: One `docker compose up` gives an end-to-end local stack (FR-015 /
SC-006) with secrets sourced only from the root `.env`, and the same ADC code path
works unchanged on Cloud Run via the attached service account.

## 9. Production deployment (Cloud Run) — design-for, build later (clarified)

**Decision**: Architect now so the same code deploys to Cloud Run without rework,
but do not build the deployment in this feature:
- **Auth**: Cloud Run runs as an attached **service account**; ADC picks it up
  automatically (same code path as local) — no key files.
- **Database**: **Cloud SQL for PostgreSQL 17**; connect via `DATABASE_URL` (Cloud
  SQL connector / unix socket). Local dev uses docker Postgres — one SQLAlchemy async
  path, environment-selected URL.
- **Secrets**: WCL and DB secrets come from **Google Secret Manager**, injected as
  env vars into the Cloud Run service. `pydantic-settings` reads env vars regardless
  of source (FR-017), so local `.env` vs Secret Manager is transparent to code.
- **Access control**: the service is **public and unauthenticated for v1** (accepted
  risk, per clarification). Real access control (Cloud Run IAM/IAP or app-level auth)
  is a tracked later improvement.
- **WebSockets on Cloud Run (note)**: supported, but enable **session affinity** and
  set an adequate request timeout for long-lived streams; keep turns well under the
  max request duration. Capture in deployment work, not v1.

**Rationale**: Honors "plan for Cloud Run + service account" while keeping v1 scope
local and basic. The env-var config boundary and uniform ADC are the only design
choices needed now to avoid later rework.

## 7. Frontend (basic, dark)

**Decision**: React + Vite + TypeScript, plain CSS, no component library. Layout:
left **Sidebar** (conversation list + "New chat"), main **ChatWindow**
(MessageList + Composer), top **ModelSelect**. A small `wsClient` manages the
WebSocket and appends streamed tokens; a `restClient` loads conversations/models.
Dark theme via CSS variables, default on.

**Rationale**: Meets US4 / FR-013 with the least machinery; easy to extend later.

**Improve later**: Markdown rendering of agent messages, tool-activity timeline,
light/dark toggle, virtualized message list.

## 8. Resolved unknowns

- No `[NEEDS CLARIFICATION]` remained from the spec. "Keep it basic / no auth /
  single plan" (user input) confirms: **single-user, no authentication, one
  deployment**; history is global to the single user.
- Python version: target **3.14** per constitution; reconcile the repo pin during
  Setup (Complexity Tracking in plan.md).
