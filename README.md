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
- The agent uses `gemini-2.5-flash` by default; change the `model` in
  `wcl_agent/agent.py` (ADK can also drive Claude/OpenAI via its LiteLLM
  connector).
