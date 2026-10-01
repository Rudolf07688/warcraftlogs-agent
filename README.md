# Warcraft Logs Agent App

An interactive terminal chat app that lets you pick a raid encounter and then ask
an AI agent to pull and analyze [Warcraft Logs](https://www.warcraftlogs.com)
ranking data for it.

Example session:

```
Selected: The Venomous Abyss > Ula'tek > Heroic

You: How well are hunters performing?
  [calling get_selected_encounter...]
  [calling get_spec_options...]
  [calling get_rankings_distribution...]
Agent: On Heroic Ula'tek this season, across 500 logged Hunter parses ...
```

## How it works

- **Frontend:** a terminal menu (`main.py`) that lists live zones/encounters/
  difficulties, then a chat REPL.
- **Agent:** built with [Google ADK](https://adk.dev) driven by **Gemini**
  (`wcl_agent/`). It calls tools that query the Warcraft Logs v2 GraphQL API,
  compute score percentiles / spec breakdowns, and report back.
- **Data:** the current-season ranking leaderboard for the selected fight
  (top-of-distribution; not a rolling last-7-days window).

## Setup

1. **Create a Warcraft Logs API client** at
   <https://www.warcraftlogs.com/api/clients/> and copy the `client_id` /
   `client_secret`.
2. **Set up Gemini via Vertex AI** using your gcloud Application Default
   Credentials (no API key stored in the repo):
   ```bash
   gcloud auth application-default login
   ```
   Make sure the Vertex AI API is enabled on your project.
3. **Configure env:**
   ```bash
   cp .env.example .env
   # edit .env: WCL keys + GOOGLE_CLOUD_PROJECT
   # (GOOGLE_CLOUD_LOCATION defaults to the global endpoint)
   ```
4. **Install deps with uv** (Python >= 3.10):
   ```bash
   uv sync
   ```

> Prefer an AI Studio API key instead of Vertex? Set
> `GOOGLE_GENAI_USE_VERTEXAI=FALSE` and `GOOGLE_API_KEY=...` in `.env`.

## Run

```bash
uv run python main.py
```

Pick a zone → encounter → difficulty from the menu, then chat. Try:

- `How well are hunters performing?`
- `Which hunter spec is strongest here?`
- `What DPS do I need for a 95th percentile parse?`

Type `exit` to quit.

## Web app (streaming chat)

A browser frontend + FastAPI backend surface the same agent as a live, streaming
chat (incremental responses, model selector, dark UI, conversation history), with
state persisted in PostgreSQL. Everything runs locally via Docker Compose.

```bash
cp .env.example .env         # fill WCL keys, GOOGLE_CLOUD_PROJECT, POSTGRES_*
gcloud auth application-default login   # Vertex ADC (mounted into the backend)
docker compose up --build
```

- Frontend: <http://localhost:5173>  •  Backend API: <http://localhost:8000>
  (`/health`, `/api/models`, `/api/conversations`, `/api/raids`, WebSocket
  `/ws/chat`, PDF export `/api/conversations/{id}/report.pdf`)

Architecture:

- **Backend** (`backend/`): FastAPI + asyncio. WebSocket streams agent tokens;
  REST handles conversations/models/raids/reports. Reuses `wcl_agent/` and builds
  the agent per selected model. SQLAlchemy async + Postgres for state; ADK
  `DatabaseSessionService` persists agent session context in the same database.
- **Frontend** (`frontend/`): React + Vite (basic, dark). Sidebar of past chats
  **and tracked raids**, model dropdown, chat box with tokens appearing as they
  stream, and a per-conversation **Download PDF** button.

### Enhancements (feature 002)

- **Tracked raids** — every report you successfully pull data for is recorded and
  listed in the sidebar (most-recent first). Click one to open a new chat that
  auto-investigates that raid. Stored in Postgres (`tracked_raids`).
- **Durable sessions** — the ADK agent session is persisted, so conversation
  *context* (not just the transcript) survives a backend restart. Interrupted
  replies are saved as `partial` rather than lost.
- **Web search** — Gemini models use native Google Search grounding (via a
  `web_search` sub-agent tool); the UI shows a "used web search" indicator.
  Anthropic/other models degrade gracefully with no web access.
- **Validated model list** — the model dropdown is discovered and probed at
  startup; only responsive models are offered, with a fallback + "degraded" notice
  if Vertex is unreachable. Configure candidates with `WCL_GEMINI_MODELS` /
  `WCL_ANTHROPIC_MODELS` (see `.env.example`).
- **PDF export** — download any conversation as a PDF with the written analysis
  plus the graphs the agent fetched (rendered with matplotlib + reportlab).

See `specs/001-streaming-chat-frontend/quickstart.md` and
`specs/002-agent-enhancements/quickstart.md` for walkthroughs, and
`documentation/deployment.md` for the Cloud Run / Cloud SQL / Secret Manager plan.

Run the backend tests:

```bash
uv run pytest backend/tests/ -q
```

## Quick checks

```bash
# Verify imports resolve
uv run python -c "import google.adk, requests, pandas"

# Smoke-test the WCL API (no LLM) — prints your hourly points budget
uv run python -c "from dotenv import load_dotenv; load_dotenv(); \
from wcl_agent.wcl_client import check_rate_limit; print(check_rate_limit())"
```

## Notes

- Warcraft Logs v2 is a GraphQL API using OAuth2 client credentials
  (`https://www.warcraftlogs.com/api/v2/client`). Requests cost "points"; the
  agent can call a `check_rate_limit` tool to see the remaining budget.
- Class/spec filters use PascalCase, space-free names (e.g. `Hunter` /
  `Marksmanship`) — handled for you in `wcl_agent/constants.py`.
- The agent uses `gemini-3.6-flash` by default; change it with `WCL_DEFAULT_MODEL`
  (shared by the backend config and the `wcl_agent` CLI, so they can't drift). The
  web app's selectable list comes from `WCL_GEMINI_MODELS` / `WCL_ANTHROPIC_MODELS`
  probed at startup. ADK drives Claude on Vertex natively (registered in
  `wcl_agent/agent.py`).
