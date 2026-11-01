# Data model: Clean-up and KB debt

Only one schema change (sc-324). No new table or column.

## Migration 0020 `0020_raw_fetch_summary_index` (down_revision `0019_kb_chunks`)

```sql
CREATE INDEX ix_raw_fetches_summaries ON raw_fetches (fetched_at DESC)
  WHERE operation_name IN ('ReportSummary', 'ReportsBatch');
```

Downgrade drops it. Declared on `RawFetch.__table_args__` too (with `postgresql_where` and
`sqlite_where`), so SQLite test schemas built from the models carry it.

## In-process state (no schema)

- `fetch_persistence._tombstones`: code → seen-gone time; now also fed by summaries that find a
  report private (sc-322).
- `raw_fetch_reads.Breaker.timeouts`: consecutive timeouts (sc-323).
- `cache._Load.external`: the load went to WCL (sc-326).
