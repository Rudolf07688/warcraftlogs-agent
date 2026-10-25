# Data model: Fetch persistence foundation

## `raw_fetches` (global, no RLS)

One row per distinct Warcraft Logs GraphQL query (query text + variables). The latest
successful response wins.

| Column | Type (Postgres / SQLite tests) | Null | Notes |
|---|---|---|---|
| `query_key` | `String(64)` | no | **Primary key.** sha256 hex of the query text plus the sorted variables: the client's single-flight key (`_flight_key`). |
| `operation_name` | `String(120)` | yes | `query <Name>` from the query text; NULL for anonymous queries (e.g. the rate-limit probe). |
| `params` | JSONB / JSON | no | The GraphQL variables exactly as sent (`{}` when none). |
| `report_code` | `String(32)` | yes | The single report code when the query names exactly one report. Btree index `ix_raw_fetches_report_code`. |
| `report_codes` | JSONB / JSON | no | Every report code the query names, in order, deduplicated; `[]` when none. Server default `'[]'`. GIN index `ix_raw_fetches_report_codes` (Postgres only). |
| `fetched_at` | `timestamptz` | no | When the response arrived (UTC). |
| `payload` | JSONB / JSON | no | The response body as the caller receives it (`data`, and `extensions` if any), without the client-injected `data._cost`. |

### Rules

- **Identity**: `query_key`. An identical fetch (same query text, same variables) maps to
  the same row.
- **Upsert**: `INSERT … ON CONFLICT (query_key) DO UPDATE SET operation_name, params,
  report_code, report_codes, fetched_at, payload = excluded.* WHERE raw_fetches.fetched_at
  < excluded.fetched_at`. The newest fetch wins. A stale write never overwrites a
  newer one.
- **Finished report** (used by sc-129, not by this feature): a report whose `endTime` is
  at least `FINAL_AFTER` (2 h) before `fetched_at`, per `normalize.is_finished`.
- **Report-code invariant**: `report_code IS NOT NULL` ⇔ `jsonb_array_length(report_codes) = 1`,
  and then `report_code = report_codes->>0`. This is enforced by the writer, not by a
  constraint (keep the schema simple).
- **Tenancy**: none. Warcraft Logs data is public (decision 6). The runtime role gets
  `SELECT, INSERT, UPDATE, DELETE`.

### Example queries (for sc-129 / sc-130)

```sql
-- every stored fetch about one report, including batch rows
SELECT query_key, operation_name, fetched_at FROM raw_fetches WHERE report_codes ? 'aBcD1234';
-- one query's stored answer
SELECT payload, fetched_at FROM raw_fetches WHERE query_key = :key;
```

## In-process value: `FetchedResponse` (`wcl_agent.client.wcl_client`)

Frozen dataclass handed from the client to the sink.

| Field | Type | Notes |
|---|---|---|
| `query_key` | `str` | `_flight_key(query, variables)`, computed once in `query()`. |
| `query` | `str` | The query text as the caller wrote it (without the injected cost field). |
| `variables` | `dict[str, Any]` | Shallow copy of the variables sent. |
| `content` | `bytes` | Raw response body (still holding `data._cost`). Its `len()` is what counts toward the byte bound. |
| `fetched_at` | `datetime` | UTC, taken right after the response passed the error checks. |
