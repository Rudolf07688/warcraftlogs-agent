# Quickstart: verify fetch persistence

All commands run in the worktree. Ports are the sprint's track A ports: app 18018,
Postgres 15418, Redis 16318. Don't use compose or the owner's `.env`.

## 1. Unit tests

```bash
uv run --extra test pytest -q backend/tests/test_raw_fetch_client.py \
  backend/tests/test_raw_fetch_store.py backend/tests/test_raw_fetch_writer.py
uv run --extra test pytest -q      # full suite: same pass/fail/skip counts as base + the new tests
```

| Acceptance | Test |
|---|---|
| AC2 write-through, once per call, none on failure or cache hit | `test_raw_fetch_client.py`, `test_raw_fetch_writer.py::test_write_through_*` |
| AC3 DB down, the fetch still succeeds | `test_raw_fetch_writer.py::test_db_down_*` |
| AC3 + PO condition: a full queue drops without blocking | `test_raw_fetch_writer.py::test_full_queue_*` |
| AC4 upsert | `test_raw_fetch_store.py::test_upsert_*` |
| FR-011 shutdown drain and timeout | `test_raw_fetch_writer.py::test_stop_*` |
| FR-015 report codes | `test_raw_fetch_client.py::test_report_codes_*`, `test_raw_fetch_store.py` |

## 2. Migration up, down, up on real Postgres (AC1, SC-006)

```bash
docker run --rm -d --name wcl020-pg -e POSTGRES_USER=wcl -e POSTGRES_PASSWORD=wcl \
  -e POSTGRES_DB=wcl -p 15418:5432 postgres:16
export DATABASE_URL=postgresql+asyncpg://wcl:wcl@localhost:15418/wcl
export DATABASE_OWNER_URL=$DATABASE_URL APP_DB_USER=wcl
uv run alembic -c backend/alembic.ini upgrade head
uv run alembic -c backend/alembic.ini downgrade -1      # drops raw_fetches
uv run alembic -c backend/alembic.ini upgrade head
docker exec wcl020-pg psql -U wcl -d wcl -c '\d raw_fetches'
```

The table has the 7 columns, PK `query_key`, the btree index on `report_code` and the GIN
index on `report_codes`.

## 3. Upsert and payload decoding on Postgres

Run against the container above. A one-off script calls `upsert_raw_fetch` twice for the
same key with a newer `fetched_at`, and once with an older one. Then check:

```sql
SELECT count(*), max(fetched_at), payload->'data' ? '_cost' AS has_cost FROM raw_fetches GROUP BY payload;
SELECT query_key FROM raw_fetches WHERE report_codes ? 'CODE1';
```

You should see one row, the newest `fetched_at`, `has_cost = false`, and the batch row
found by any of its codes.

## 4. Live app check (optional, needs WCL credentials from the scrum master)

Start the backend on port 18018 against the container. Ask a chat question that fetches
a report, then `SELECT operation_name, report_code, fetched_at FROM raw_fetches ORDER BY
fetched_at DESC LIMIT 5;`. Stop the container: chat tools still answer, and the log shows
one throttled `fetch persistence` warning.
