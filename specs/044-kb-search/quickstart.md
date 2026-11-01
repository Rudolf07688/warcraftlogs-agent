# Quickstart: Knowledge base search (044)

## SQLite suite (default)

```bash
cd /home/rudolf/dev/wcl-worktrees/dev-b
env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q
env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q \
  backend/tests/test_name_resolver.py backend/tests/test_kb_search.py \
  backend/tests/test_kb_search_prompt.py backend/tests/test_kb_eval.py
```

## Postgres-only tests (visibility, bypass attempts, eval)

Throwaway pgvector container on port 15444 (never `docker compose`, never 5432). Recipe from
`specs/039-local-first-data/quickstart.md` §2 with the image and port swapped:

```bash
docker run -d --rm --name wcl-044-pg -e POSTGRES_USER=wcl -e POSTGRES_PASSWORD=wcl \
  -e POSTGRES_DB=wcl -p 15444:5432 pgvector/pgvector:pg17
# migrate as the owner role, test as the runtime role (039 quickstart §2 for the role setup)
env -i HOME=$HOME PATH=$PATH DATABASE_URL=postgresql+asyncpg://wcl:wcl@localhost:15444/wcl \
  uv run alembic -c backend/alembic.ini upgrade head
env -i HOME=$HOME PATH=$PATH TEST_DATABASE_URL=postgresql+asyncpg://wcl_app:wcl_app@localhost:15444/wcl \
  uv run --extra test pytest -q backend/tests/test_kb_search_pg.py backend/tests/test_kb_eval.py \
  backend/tests/test_raw_store_visibility.py backend/tests/test_raw_store_pg.py
docker stop wcl-044-pg   # disk is tight: always stop it
```

## Eval

```bash
# CI mode (stand-in or recorded embeddings; reports recall@k per mode and latency)
env -i HOME=$HOME PATH=$PATH TEST_DATABASE_URL=… uv run python -m backend.evals.kb run --k 8

# team-lead only, live (real embedder; capped at ~300 texts): writes backend/evals/kb/embeddings.json
uv run python -m backend.evals.kb record
# team-lead only, live (cheapest chat model, capped): filter accuracy + local-answer rate
uv run python -m backend.evals.kb live --max-questions 30
```

## Owner live check (team-lead, sprint end)

1. After 043's pipeline has embedded a report: in a new chat ask "what did Vagxsu do on Heroic
   Ula'tek in report <code>?" and see a `search_knowledge` card with compact hits, and no full
   table in the turn.
2. Ask "how should an arms warr open on ulatek?" and see guide hits with `class_name=Warrior`,
   `spec=Arms`.
3. In chat B, ask about something said in chat A of the same workspace: a chat hit. Delete chat
   A and repeat: no hit.
4. Stop the embedder credentials (or set an invalid model) and search again: the result says
   keyword-only.
