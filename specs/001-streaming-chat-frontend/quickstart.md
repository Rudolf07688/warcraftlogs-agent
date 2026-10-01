# Quickstart: Streaming Chat Frontend (local)

Goal: bring up the whole stack locally with one command and chat with the agent in
the browser, streaming.

## Prerequisites

- Docker + Docker Compose.
- A populated root `.env` (copy from `.env.example`): `WCL_CLIENT_ID`,
  `WCL_CLIENT_SECRET`, Gemini/Vertex config, and `DATABASE_URL`.
- Gemini auth for containers (pick one):
  - **Vertex + ADC**: run `gcloud auth application-default login` on the host; Compose
    mounts `~/.config/gcloud/application_default_credentials.json` into the backend
    (read-only) and sets `GOOGLE_APPLICATION_CREDENTIALS` to it.
  - **API key (simplest in a container)**: set `GOOGLE_GENAI_USE_VERTEXAI=FALSE` and
    `GOOGLE_API_KEY=…` in `.env`.

## `.env` additions

```
# Postgres (used by backend + the db service)
DATABASE_URL=postgresql+asyncpg://wcl:wcl@db:5432/wcl
POSTGRES_USER=wcl
POSTGRES_PASSWORD=wcl
POSTGRES_DB=wcl
```

(`WCL_*` and `GOOGLE_*` stay as today.)

## Run

```bash
docker compose up --build
```

- `db` (postgres:17) comes up and passes its healthcheck.
- `backend` (FastAPI) waits for the DB, creates tables on first start, serves
  `http://localhost:8000` (REST under `/api`, WebSocket at `/ws/chat`).
- `frontend` serves `http://localhost:5173` (or configured port).

Open the frontend URL, pick a model, type a question (e.g. "How are hunters
performing on Heroic Ula'tek?"), and watch the answer stream in. Start a new chat
and confirm both appear in the sidebar.

## Verify (maps to Success Criteria)

- **SC-001/SC-002**: response starts < 2s and visibly streams in.
- **SC-003**: a 3+ lookup question (e.g. "compare all hunter specs") returns
  noticeably faster than sequential retrieval.
- **SC-004**: `docker compose restart backend` → previous conversations still listed
  with full history.
- **SC-005**: change the model, send a message → new model used.
- **SC-006**: the above all worked from a single `docker compose up`.
- **SC-007**: stop the backend mid-answer → UI shows a disconnected/error state.

## Backend-only dev (without Docker)

```bash
uv sync
# ensure a local Postgres 17 + DATABASE_URL (localhost)
uv run uvicorn backend.app.main:app --reload
# frontend: cd frontend && npm install && npm run dev
```

## Smoke tests

```bash
curl localhost:8000/health
curl localhost:8000/api/models
curl localhost:8000/api/conversations
```
