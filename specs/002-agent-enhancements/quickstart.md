# Quickstart: Agent App Enhancements

Builds on the `001` local stack (Docker Compose: Postgres 17 + backend + frontend,
sourcing the root `.env`). This covers what's new in `002` and how to verify each story.

## Prerequisites (unchanged from 001)

- Root `.env` with `WCL_CLIENT_ID`, `WCL_CLIENT_SECRET`, and Google ADC available
  (mounted gcloud ADC locally) for Vertex access.
- `uv` installed; Docker + Docker Compose.

## New configuration (`.env` / `.env.example`)

```bash
# Model discovery candidates (validated at startup; research §5)
WCL_GEMINI_MODELS=gemini-3.6-flash,gemini-3.6-flash
WCL_ANTHROPIC_MODELS=claude-sonnet-4@vertex
WCL_DEFAULT_MODEL=gemini-3.6-flash

# Sync DB URL for ADK DatabaseSessionService is DERIVED from DATABASE_URL
# (postgresql+asyncpg://… -> postgresql+psycopg://…); no separate var needed.
```

## New dependencies

```bash
uv add "psycopg[binary]" "google-adk[anthropic]" reportlab matplotlib markdown
uv sync
```

- If the backend image is slim, ensure matplotlib's runtime libs (freetype/libpng) are
  present in `backend/Dockerfile`.

## Run the stack

```bash
docker compose up --build
# frontend: http://localhost:5173   backend: http://localhost:8000/health
```

On startup the backend probes candidate models and logs the validated set
(`GET /api/models` reflects it, with `degraded: true` if Vertex was unreachable).

## Verify by user story

### US1 — Tracked raids + one-click investigate (P1)

1. Ask the agent a question that makes it pull a specific report (e.g. "Deep-dive report
   `aBcD1234wXyZ` — who died on the last pull?").
2. Confirm the raid appears in the sidebar **Raids** section with a label and a
   last-asked time (`GET /api/raids` returns it).
3. Ask about a second report; confirm both listed, most-recent first.
4. Ask about the first report again; confirm **no duplicate** and it jumps to the top.
5. Click a raid → a **new chat** opens and the agent starts investigating it
   automatically.
6. `docker compose restart backend` → the Raids list is still present (persisted).

### US2 — Durable sessions & persistence (P1)

1. Hold a multi-turn chat that builds context (e.g. establish an encounter, then ask a
   dependent follow-up).
2. `docker compose restart backend`.
3. Reopen the conversation: full history shows, **and** a follow-up relying on earlier
   turns is answered correctly (context restored, not just transcript).
4. Interrupt a reply (kill the backend mid-stream): on reconnect the partial reply is
   stored as `partial`, not shown as a completed answer.

### US3 — Web access via grounding (P2)

1. With a Gemini model selected, ask something current/external ("What changed for
   hunters in the latest patch?").
2. Confirm the answer uses web info and the UI shows the grounding indicator.
3. Switch to an Anthropic model and ask the same: the agent answers from available data
   and notes web info wasn't available (graceful) — no error.

### US4 — Dynamic, validated models (P2)

1. Open the model selector: the list matches the validated Gemini/Anthropic candidates.
2. Add a bogus model id to `WCL_GEMINI_MODELS`, restart: it is **excluded** (failed the
   probe).
3. Simulate Vertex unreachable (bad ADC): selector still shows a fallback set and a
   "degraded" notice (never empty).

### US5 — PDF export (P3)

1. In a conversation where the agent fetched graphs (e.g. asked for a DPS-over-time
   graph), click **Download PDF**.
2. Open the PDF: header with raid label + date, the written analysis, and the graph(s)
   rendered as charts.
3. In a graph-less conversation, confirm the PDF still generates (analysis only).

## Tests

```bash
uv run pytest backend/tests -q
```

New backend tests to add: raid upsert/dedup + ordering; session restore after restart
(context continuity); model-validation fallback (`degraded`); investigate-raid endpoint;
PDF endpoint happy-path + no-graphs path + failure → clear error.
