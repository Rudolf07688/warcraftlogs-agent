# Contract 3: fetch_visible_clause (raw_fetches.py)

```python
def fetch_visible_clause(
    raw_fetch_id: ColumnElement[str] | str, *, tenant_id: uuid.UUID | None, since: datetime
) -> ColumnElement[bool]
```
`raw_fetch_id` is a `raw_fetches.query_key` (column or value; 043 #31). True iff the row exists,
its `report_codes` is non-empty, every code is 1..`MAX_CODE` long, and every code is either
`raw_reports.visibility = 'public'` with `checked_at >= since`, or granted to `tenant_id` with
`granted_at >= since`. `tenant_id=None` → public only. Works on SQLite and Postgres. Freshness is
not part of it. On Postgres grants are RLS'd: the caller's transaction carries the tenant scope.
`read_visible_fetch` uses it; 044 joins `kb_chunks.raw_fetch_id` through it.
