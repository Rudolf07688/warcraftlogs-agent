# Quickstart: 043 knowledge base store and embedding

## 1. Unit tests (SQLite, no services, embedder faked)

```bash
env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q
```

## 2. Postgres tests (pgvector image, migration 0019, RLS, cascades)

Throwaway container on port 15443 (never `docker compose`, never 5432). The image is
`pgvector/pgvector:pg17-trixie`, which replaces `postgres:17` in every recipe from now on. Use the
`-trixie` tag: plain `pg17` is Debian 12 (glibc 2.36) while `postgres:17` is Debian 13 (glibc
2.41), and a database created under one and opened under the other warns about a collation
version mismatch (text indexes may sort differently).

```bash
docker run -d --rm --name wcl-043-pg -e POSTGRES_USER=wcl -e POSTGRES_PASSWORD=wcl \
  -e POSTGRES_DB=wcl -p 15443:5432 pgvector/pgvector:pg17-trixie
env -i HOME=$HOME PATH=$PATH APP_DB_USER=wcl_app APP_DB_PASSWORD=wcl_app \
BOOTSTRAP_ADMIN_EMAIL=founder@example.com BOOTSTRAP_ADMIN_PASSWORD=throwaway-founder-pass \
DATABASE_OWNER_URL=postgresql+asyncpg://wcl:wcl@localhost:15443/wcl \
DATABASE_URL=postgresql+asyncpg://wcl_app:wcl_app@localhost:15443/wcl \
  uv run python -m backend.cli.init_db
env -i HOME=$HOME PATH=$PATH TEST_DATABASE_URL=postgresql+asyncpg://wcl_app:wcl_app@localhost:15443/wcl \
  uv run --extra test pytest -v backend/tests/test_kb_store_pg.py backend/tests/test_kb_chat_pg.py \
  backend/tests/test_rls.py backend/tests/test_raw_store_pg.py
# 0019 downgrade / upgrade round trip as the owner
A() { env -i HOME=$HOME PATH=$PATH DATABASE_OWNER_URL=postgresql+asyncpg://wcl:wcl@localhost:15443/wcl \
  uv run alembic -c backend/alembic.ini "$@"; }
A downgrade -1 && A upgrade head && A downgrade -1 && A upgrade head
docker stop wcl-043-pg
```

## 3. Old-volume compatibility (sc-111 AC1), on a copy, never the compose volume

```bash
docker volume create wcl-043-old && docker volume create wcl-043-copy
docker run -d --rm --name wcl-043-old -e POSTGRES_USER=wcl -e POSTGRES_PASSWORD=wcl \
  -e POSTGRES_DB=wcl -v wcl-043-old:/var/lib/postgresql/data postgres:17
# wait for ready, then write a marker
docker exec wcl-043-old psql -U wcl -d wcl -c "CREATE TABLE marker(v text); INSERT INTO marker VALUES ('kept');"
docker stop wcl-043-old
docker run --rm -v wcl-043-old:/from -v wcl-043-copy:/to alpine sh -c 'cp -a /from/. /to'
docker run -d --rm --name wcl-043-new -e POSTGRES_USER=wcl -e POSTGRES_PASSWORD=wcl \
  -e POSTGRES_DB=wcl -v wcl-043-copy:/var/lib/postgresql/data pgvector/pgvector:pg17-trixie
docker exec wcl-043-new psql -U wcl -d wcl -c "SELECT v FROM marker; CREATE EXTENSION vector; SELECT extversion FROM pg_extension WHERE extname='vector';"
docker stop wcl-043-new && docker volume rm wcl-043-old wcl-043-copy
```

## 4. Backfill (owner, after the merge)

```bash
uv run python -m backend.cli.kb_backfill            # counts + estimated cost, writes nothing
uv run python -m backend.cli.kb_backfill --limit 20 --confirm   # cheap trial
uv run python -m backend.cli.kb_backfill --confirm  # the rest; safe to interrupt and rerun
```

## 5. Watching the store (owner)

```sql
SELECT kind, count(*), count(embedding) AS embedded FROM kb_chunks GROUP BY kind;
SELECT count(*), count(embedding) FROM kb_chat_chunks;   -- as the owner role (RLS bypass)
```
