# Contract: datastores.yaml aliases (058)

Dashboards D9–D11 and the alerts read only these (plus existing aliases such as `cache:hit_ratio`).
Evaluated every minute. Rates are per second over 5 m.

| Alias | Labels | Meaning |
|---|---|---|
| `pg:connections:count` | `state` | backends by state (pg_stat_activity) |
| `pg:connections:max` | | `max_connections` |
| `pg:transactions:rate5m` | `outcome` (commit/rollback) | TPS |
| `pg:cache_hit_ratio:5m` | | blks_hit / (hit + read) |
| `pg:statement_seconds:rate5m` | `queryid` | statement execution time per second |
| `pg:statement_calls:rate5m` | `queryid` | calls per second |
| `pg:locks:count` | `mode` | locks held |
| `pg:longest_transaction:seconds` | | oldest open transaction age |
| `pg:dead_tuples:count` | `relname` | dead tuples per table (bloat signal) |
| `pg:autovacuum:count` | | running autovacuum workers |
| `pg:wal_bytes:rate5m` | | WAL written per second |
| `pg:deadlocks:rate5m` | | deadlocks per second |
| `pg:vector_index:bytes` | `table`, `index` | vector index size |
| `pg:vector_table:rows` | `table` | live rows in tables with a vector column |
| `redis:memory:used_bytes`, `redis:memory:max_bytes` | | memory and limit |
| `redis:evictions:rate5m`, `redis:commands:rate5m` | | evictions and ops per second |
| `redis:hit_ratio:5m` | | keyspace hits / (hits + misses) |
| `redis:clients:connected` | | connected clients |
| `redis:command_latency:avg5m` | `cmd` | mean seconds per command |
| `redis:slowlog:length` | | slowlog entries |
| `infra:container_cpu:rate5m`, `infra:container_memory:bytes` | `compose_service` | per container |
| `meta:exporter_failures:increase2m` | `signal` | Alloy send/enqueue failures + receiver refusals |
| `meta:export_queue:ratio` | `exporter` | queue fill (size / capacity) |
| `meta:ingest:rate5m` | `backend` (loki/tempo/mimir) | lines, spans, samples per second |
| `meta:active_series:count`, `meta:active_series:budget` | | Mimir in-memory series, and 50000 |
| `alert:build_spend_usd_per_day:threshold` | | build spend alert threshold (USD/day) |
