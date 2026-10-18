# Contract: Cache Statistics Endpoint

**Feature**: 014-redis-wcl-cache · FR-018–FR-022, US3

## `GET /api/admin/cache-stats`

**Auth**: session cookie; `require_platform_admin` (403 `{"code":"forbidden"}` otherwise,
401 when not signed in). Read-only GET, so no CSRF token.

**Query**: `days` — int, 1–35, default 7 (422 outside range). Window = today (UTC) and the
previous `days − 1` UTC days.

**200** — `CacheStats` (data-model.md):

```json
{
  "window_days": 7,
  "enabled": true,
  "available": true,
  "families": {
    "char_id":        {"hits": 410, "misses": 22, "neg_hits": 6, "lock_timeouts": 0, "errors": 0, "redis_errors": 0, "hit_rate": 0.95, "avg_load_ms": 180.0, "status": "ok"},
    "report_player":  {"hits": 95, "misses": 310, "neg_hits": 0, "lock_timeouts": 1, "errors": 0, "redis_errors": 0, "hit_rate": 0.235, "avg_load_ms": 1900.0, "status": "review"},
    "world_zones":    {"hits": 0, "misses": 0, "neg_hits": 0, "lock_timeouts": 0, "errors": 0, "redis_errors": 0, "hit_rate": null, "avg_load_ms": null, "status": "no_data"}
  },
  "redis": {"keyspace_hit_rate": 0.91, "evicted_keys": 0, "used_memory_mb": 38.2}
}
```

(Numbers illustrative; all seven families are always present.)

**Degraded**:
- Cache disabled → `enabled: false`, `available: false`, families all `no_data`, `redis: null`.
- Redis unreachable → `enabled: true`, `available: false`, families all `no_data`, `redis: null`. Still 200.
- Redis wiped → only history since the wipe (US3 scenario 4).
- Redis refuses `INFO` (some managed services) → families as normal, `redis: null`.

**Status rule**: `no_data` when `hits + neg_hits + misses == 0`; `review` when
`hit_rate < review_below` (0.90 char_id/oauth_token/world_zones, 0.60 char_overview/char_reports,
0.40 report_summary/report_player); else `ok`.

No frontend page in this feature; operators call it from the browser/devtools or `curl`
with their session cookie (quickstart.md).
