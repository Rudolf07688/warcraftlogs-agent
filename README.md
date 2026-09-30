# Warcraft Logs Agent App

A small Python starter app to fetch and analyze Warcraft Logs data for encounters like Heroic Ula'tek in The Venomous Abyss.

## What this app does

- Authenticates against Warcraft Logs using OAuth2 client credentials
- Runs GraphQL queries against the public v2 API
- Normalizes ranking/spec data into pandas DataFrames
- Lets you ask an LLM-driven agent questions over fetched parse/ranking data
- Supports saving raw JSON and CSV outputs for later analysis

## What you need to do manually

1. Create a Warcraft Logs API client in your account:
   - Log in to Warcraft Logs
   - Open the client management page
   - Create a client and copy your `client_id` and `client_secret`
2. Export these environment variables before running:
   - `WCL_CLIENT_ID`
   - `WCL_CLIENT_SECRET`
   - optionally `OPENAI_API_KEY` if you want the agent mode
3. Decide whether you want:
   - public API only, enough for public rankings/statistics
   - user auth later, if you want private reports
4. Install Python 3.11+ and dependencies.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export WCL_CLIENT_ID=your_client_id
export WCL_CLIENT_SECRET=your_client_secret
export OPENAI_API_KEY=your_openai_key   # optional
python app.py fetch-rankings --zone 53 --difficulty 4 --encounter 3492 --metric dps --out data/ulatek_rankings.json
python app.py summarize --input data/ulatek_rankings.json
```

## Notes

- Warcraft Logs public API uses OAuth 2.0 client credentials and the v2 API is GraphQL.
- Public API endpoint: `https://www.warcraftlogs.com/api/v2/client`
- Token endpoint: `https://www.warcraftlogs.com/oauth/token`
- Private-report access requires a user authorization flow instead of simple client credentials.

