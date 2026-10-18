# Spec: Redis Cache for the Warcraft Logs AI Chat Tools

Redis sits between the agent tools and the Warcraft Logs API, using cache-aside with TTLs. Hit rate is tracked per key family with small application-level counters.

## 1. Scope

**Goals**
- Cut Warcraft Logs API calls and latency for repeated lookups.
- Stay under the API rate limit.
- Show hit rate per key family.

**Non-goals**
- Caching LLM answers.
- Background sync or precomputed projections.
- Redis Cluster hash tags, revisioned keys, or generation counters.

## 2. What gets cached

Only these 6 key families are in scope. Adding a seventh needs a measured reason (see Review process).

| Family | Key | Value | TTL | Why |
|---|---|---|---|---|
| `char_id` | `wcl:v1:char_id:{region}:{realm}:{name_lc}` | `{id, name, realm, region, class}` | 24h | Name-to-ID lookup is needed by nearly every question. |
| `char_overview` | `wcl:v1:char:{id}:overview` | Normalized gear, progress and parse summary | 10m | Most common question, moderately volatile. |
| `char_reports` | `wcl:v1:char:{id}:reports:{limit}` | List of `{code, title, startTime, zone}` | 5m | Changes when new logs are uploaded. |
| `report_summary` | `wcl:v1:report:{code}:summary` | Fights, bosses, kills and wipes, roster | 24h | Finished reports are effectively immutable. |
| `report_player` | `wcl:v1:report:{code}:player:{id}` | Per-player damage, healing, deaths and top abilities | 24h | Answers most "how did I do" follow-ups. |
| `oauth_token` | `wcl:v1:oauth:token` | Access token | `expires_in - 60s` | Avoids a token request on every call. |

**Rules**
- `v1` is a schema version. Bump it when the normalized shape changes; old keys expire on their own.
- Lowercase and trim names before building keys.
- Never put user IDs or conversation IDs in a Warcraft Logs key. The data is public, so users share entries.
- Store normalized internal models as JSON, never raw GraphQL responses.
- Report keys are cached only for finished reports. If a report is live or incomplete, use a 2m TTL or skip the cache.

**Deliberately not cached**
- Event-level data (casts, buffs, timelines). It is large and rarely repeated. Fetch on demand, aggregate, and cache only the aggregate under `report_player`.
- Rankings across arbitrary filters.
- Final LLM responses.
- Conversation state (store it in your DB, or under a separate `chat:` prefix with its own policy).

## 3. Components

```text
agent tools -> WarcraftLogsService -> CacheClient (get_or_load) -> Redis
                       |                        |
                       |                        +-> CacheMetrics (counters)
                       +-> WclGraphQLClient (OAuth, retries, normalization)
```

### CacheClient

A single `get_or_load` method is the only way tools touch Redis, so nothing can bypass the metrics.

```python
await cache.get_or_load(
    family="char_overview",
    key=f"wcl:v1:char:{cid}:overview",
    ttl=600,
    loader=lambda: wcl.fetch_overview(cid),
)
```

**Behaviour**
1. `GET key`.
2. On a hit, record `hit` and return the decoded value.
3. On a miss, try to acquire a short lock with `SET lock:{key} 1 NX PX 10000`.
4. The lock winner calls the loader, then `SET key value EX ttl+jitter`, then records `miss` and `load_ms`.
5. Callers that lose the lock poll the cache briefly (up to about 2s) and return the winner's value. If nothing appears, they call the loader themselves and record `lock_timeout`.
6. If the loader raises, release the lock, record `error`, and re-raise.
7. If Redis itself fails, record `redis_error`, call the loader directly, and skip writes. The cache must never be a hard dependency.

Use `redis.asyncio` since the stack is async, and build the client once at startup.

**TTL jitter:** `ttl * random.uniform(1.0, 1.1)`. It stops keys written together from expiring together.

**Negative caching:** if Warcraft Logs returns "character not found", cache a `{"_missing": true}` marker for 60s. This stops repeated misses from retyped names. Count it as its own outcome, `neg_hit`.

## 4. Hit-rate tracking

### Why not just use INFO

Redis `INFO stats` gives `keyspace_hits` and `keyspace_misses`. They are server-wide totals, so you cannot tell which key family is performing badly. They also count every `GET`, including lock keys, which skews the ratio. Use INFO for the overall health check and application counters for the per-family view.

### Counter design

One Redis hash per family per UTC day:

```text
wcl:metrics:v1:{family}:{YYYYMMDD}   (hash, TTL 35 days)
  hit            -> int
  miss           -> int
  neg_hit        -> int
  lock_timeout   -> int
  error          -> int
  redis_error    -> int
  load_ms_sum    -> int
  load_count     -> int
```

- Increment after each call, fire-and-forget, with `HINCRBY`.
- Set `EXPIRE` when the hash is first created.
- Pipeline the increments with the cache write to avoid extra round trips.
- Keep them under the `wcl:metrics:` prefix, separate from cache families. If Redis is wiped you lose history but not correctness.

### Derived metrics

```text
hit_rate    = (hit + neg_hit) / (hit + neg_hit + miss)
avg_load_ms = load_ms_sum / load_count
```

Calculate rates over a window (today, last 7 days) rather than all-time totals, because all-time numbers hide recent regressions.

### Stats endpoint

`GET /internal/cache-stats?days=7` (auth-protected, internal only):

```json
{
  "window_days": 7,
  "families": {
    "char_overview": {
      "hits": 1840, "misses": 212, "hit_rate": 0.897,
      "avg_load_ms": 640, "errors": 3,
      "status": "ok"
    },
    "report_player": {
      "hits": 95, "misses": 310, "hit_rate": 0.235,
      "avg_load_ms": 1900, "errors": 0,
      "status": "review"
    }
  },
  "redis": {"keyspace_hit_rate": 0.91, "evicted_keys": 0, "used_memory_mb": 38}
}
```

(Numbers above are illustrative only.) The `redis` block comes from `INFO stats` and `INFO memory`: `keyspace_hits`, `keyspace_misses`, `evicted_keys` and `used_memory`.

### Status thresholds

| Family type | Target hit rate | `review` below |
|---|---|---|
| `char_id`, `oauth_token` | above 95% | 90% |
| `char_overview`, `char_reports` | above 80% | 60% |
| `report_summary`, `report_player` | above 70% | 40% |

A family below roughly 40% is a candidate for removal.

### Optional: Prometheus

If Prometheus or Grafana is already running, emit the same events as counters alongside the Redis hashes:

```text
wcl_cache_requests_total{family="char_overview", outcome="hit|miss|neg_hit|error"}
wcl_cache_load_seconds{family="char_overview"}   (histogram)
```

Hit rate then becomes a one-line PromQL ratio per family. The Redis hash plus the endpoint is enough to start.

## 5. Warcraft Logs client details

- Use OAuth client credentials and cache the token under `oauth_token`.
- Request only the fields needed in each GraphQL query.
- Record API cost on every real API call. The API exposes a `rateLimitData` object; add it to a query and log the points spent. This shows whether caching is protecting your quota.
- Retry with backoff on 429 and 5xx, maximum 2 retries.
- Keep a `WCL_CACHE_ENABLED` flag so you can disable caching and compare behaviour.

## 6. Failure behaviour

| Failure | Behaviour |
|---|---|
| Redis down | Bypass the cache and call the API directly. Log and count `redis_error`. |
| Warcraft Logs down | Return a tool error the agent can explain (no stale serving in v1). |
| Corrupt cached JSON | Delete the key, treat as a miss, count `error`. |
| Character not found | Negative-cache for 60s. |

## 7. Invalidation

TTL only, with one exception. When a user explicitly asks to refresh ("check again"), the tool passes `force_refresh=True` to bypass the read, reload, and overwrite the key. Because Redis is a shared cache of public data, rate-limit this per user, for example 1 refresh per character per minute.

## 8. Config

```text
REDIS_URL
WCL_CACHE_ENABLED=true
WCL_CACHE_TTL_{FAMILY}   # per-family override, seconds
WCL_CACHE_JITTER=0.10
WCL_CACHE_LOCK_MS=10000
WCL_NEG_CACHE_TTL=60
WCL_METRICS_RETENTION_DAYS=35
```

Redis settings: `maxmemory` set explicitly, `maxmemory-policy allkeys-lru`, no persistence needed. This is a disposable cache.

## 9. Testing

- **Unit:** use `fakeredis` and a stub loader. Cover hit, miss, negative hit, lock contention (10 concurrent callers should result in 1 loader call), loader error, and Redis-down fallback.
- **Metrics:** assert that counters increment for each outcome.
- **Key builders:** test normalization (`Rudolf` and `rudolf ` produce the same key) and that no key contains user-specific data.
- **Load check:** replay a realistic set of 100 chat questions and read the stats endpoint to see per-family hit rates before settling TTLs.

## 10. Rollout

1. Implement `CacheClient`, metrics and the stats endpoint, with the tools unchanged.
2. Wrap `char_id` and `oauth_token` first, then check the numbers.
3. Add `char_overview`, `char_reports`, `report_summary` and `report_player`.
4. Run for a week, then apply the review process.

## 11. Review process (weekly)

- Any family with status `review`: increase the TTL, widen the key by dropping a dimension, or remove the family.
- Rising `evicted_keys`: Redis is too small, or something is storing large values.
- Rising `lock_timeout`: loaders are too slow, or the lock TTL is too short.
- To add a new family, show a repeated, slow or rate-limited call in your logs first.

## 12. Open questions

- Is Redis already provisioned (for example Memorystore), or should this start with a local container? A small single-instance Memorystore is likely enough for a lightweight setup.
- Do users query a few well-known characters (their guild) or arbitrary ones? Mostly arbitrary lookups will lower hit rates for the `char_*` families; this is the biggest unknown.
- Should "latest raid" questions tolerate 5 minutes of staleness? If you need real-time answers during a live raid night, `char_reports` needs a shorter TTL.
