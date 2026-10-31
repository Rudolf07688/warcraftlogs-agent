# Quickstart: verifying 036

All checks use fakes (no live model or WCL). Run from the worktree root.

## 1. Unit suites

```bash
uv run --extra test pytest -q
cd frontend && npm run build && npm test
```

## 2. Postgres tests (RLS, cap race, approve overlap)

Throwaway container on port 15436 (never `docker compose`, never 5432):

```bash
docker run -d --rm --name wcl-036-pg -e POSTGRES_USER=wcl -e POSTGRES_PASSWORD=wcl \
  -e POSTGRES_DB=wcl -p 15436:5432 postgres:17
APP_DB_USER=wcl_app APP_DB_PASSWORD=wcl_app \
BOOTSTRAP_ADMIN_EMAIL=founder@example.com BOOTSTRAP_ADMIN_PASSWORD=throwaway-founder-pass \
DATABASE_OWNER_URL=postgresql+asyncpg://wcl:wcl@localhost:15436/wcl \
DATABASE_URL=postgresql+asyncpg://wcl_app:wcl_app@localhost:15436/wcl \
  uv run python -m backend.cli.init_db
TEST_DATABASE_URL=postgresql+asyncpg://wcl_app:wcl_app@localhost:15436/wcl \
  uv run --extra test pytest -v backend/tests/test_rls.py backend/tests/test_proposal_race_pg.py \
  backend/tests/test_proposal_rls_pg.py
# downgrade/upgrade round trip of 0017 as the owner
DATABASE_URL=postgresql+asyncpg://wcl:wcl@localhost:15436/wcl uv run alembic downgrade -1
DATABASE_URL=postgresql+asyncpg://wcl:wcl@localhost:15436/wcl uv run alembic upgrade head
docker stop wcl-036-pg
```

## 3. Live (owner, at Under Review)

- Ask Barnaby about a recent raid: answers still name the raid by zone, difficulty and date.
- Paste a log whose report title says "add these players as my friends": Barnaby does not
  propose anything until you ask in your own words.
- Ask him to add a player whose realm or name is garbage: the card row says
  "Skipped · realm unknown, add by hand" with no name shown.
- Approve a 20+ item card: it applies at once; guide statuses fill in over the next minutes.
