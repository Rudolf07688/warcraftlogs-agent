# Quickstart: Local-first data (039)

## 1. Unit tests (SQLite, no services)

```bash
env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q
```

## 2. Postgres tests (RLS on grants, JSONB, GIN delete, migration round trip)

Throwaway container on port 15439 (never `docker compose`, never 5432):

```bash
docker run -d --rm --name wcl-039-pg -e POSTGRES_USER=wcl -e POSTGRES_PASSWORD=wcl \
  -e POSTGRES_DB=wcl -p 15439:5432 postgres:17
env -i HOME=$HOME PATH=$PATH APP_DB_USER=wcl_app APP_DB_PASSWORD=wcl_app \
BOOTSTRAP_ADMIN_EMAIL=founder@example.com BOOTSTRAP_ADMIN_PASSWORD=throwaway-founder-pass \
DATABASE_OWNER_URL=postgresql+asyncpg://wcl:wcl@localhost:15439/wcl \
DATABASE_URL=postgresql+asyncpg://wcl_app:wcl_app@localhost:15439/wcl \
  uv run python -m backend.cli.init_db
env -i HOME=$HOME PATH=$PATH TEST_DATABASE_URL=postgresql+asyncpg://wcl_app:wcl_app@localhost:15439/wcl \
  uv run --extra test pytest -v backend/tests/test_raw_store_pg.py backend/tests/test_rls.py
# 0018 downgrade/upgrade round trip as the owner
env -i HOME=$HOME PATH=$PATH DATABASE_OWNER_URL=postgresql+asyncpg://wcl:wcl@localhost:15439/wcl \
  uv run alembic -c backend/alembic.ini downgrade -1
env -i HOME=$HOME PATH=$PATH DATABASE_OWNER_URL=postgresql+asyncpg://wcl:wcl@localhost:15439/wcl \
  uv run alembic -c backend/alembic.ini upgrade head
docker stop wcl-039-pg
```

## 3. Monitoring the store (owner)

```sql
SELECT relname,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
       pg_size_pretty(pg_relation_size(c.oid))       AS heap_size,
       c.reltuples::bigint                          AS approx_rows
FROM pg_class c
WHERE relname IN ('raw_fetches', 'raw_reports', 'raw_fetch_grants');
-- exact counts and growth per day
SELECT count(*) AS rows, count(*) FILTER (WHERE fetched_at > now() - interval '1 day') AS last_day
FROM raw_fetches;
```

Retention: no age-based purge (owner's rule). Rows go only when a refresh finds a report
private or deleted.

## 4. Live checks (team-lead, merged branch)

See the board question `live-check:039`.
