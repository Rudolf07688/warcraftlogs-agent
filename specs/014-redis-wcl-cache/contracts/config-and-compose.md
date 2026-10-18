# Contract: Configuration and Docker Compose

**Feature**: 014-redis-wcl-cache · FR-014, FR-023, FR-024

## Environment variables (`.env.example`, backend `Settings`, read by `wcl_agent` via `os.getenv`)

| Variable | Default | Meaning |
|---|---|---|
| `REDIS_URL` | *(unset → cache disabled)*; `.env.example`: `redis://localhost:6379/0`; compose sets `redis://redis:6379/0` for the backend | Cache location |
| `WCL_CACHE_ENABLED` | `true` | Master switch (FR-014) |
| `WCL_CACHE_TTL_CHAR_ID` | `86400` | per-family TTL override, seconds |
| `WCL_CACHE_TTL_CHAR_OVERVIEW` | `600` | |
| `WCL_CACHE_TTL_CHAR_REPORTS` | `300` | |
| `WCL_CACHE_TTL_REPORT_SUMMARY` | `86400` | finished reports only |
| `WCL_CACHE_TTL_REPORT_PLAYER` | `86400` | finished reports only |
| `WCL_CACHE_TTL_WORLD_ZONES` | `3600` | |
| `WCL_CACHE_UNFINISHED_TTL` | `120` | reports still in progress |
| `WCL_CACHE_JITTER` | `0.10` | TTL × U(1, 1+jitter) |
| `WCL_CACHE_LOCK_MS` | `90000` | loader lock lifetime (longer than the 75 s WCL query timeout; was 10000 — PERF-006) |
| `WCL_CACHE_LOCK_WAIT_MS` | `2000` | how long losers poll |
| `WCL_NEG_CACHE_TTL` | `60` | "not found" marker lifetime |
| `WCL_METRICS_RETENTION_DAYS` | `35` | daily counter hash TTL |

(`oauth_token` has no TTL override: it always follows the token's `expires_in − 60`.)

Removed: `WCL_CACHE_TTL_REPORT_S`, `WCL_CACHE_TTL_LEADERBOARD_S`, `WCL_CACHE_MAX_BYTES`.

## `docker-compose.yml`

```yaml
services:
  redis:
    image: redis:8-alpine
    # Disposable cache: bounded memory, LRU eviction, no persistence (feature 014).
    command: ["redis-server", "--maxmemory", "256mb", "--maxmemory-policy", "allkeys-lru",
              "--save", "", "--appendonly", "no"]
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  backend:
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
```

No volume: recreating the container empties the cache, which is a supported state.

## Python dependencies

- runtime: `redis>=6` (`redis.asyncio`)
- test extra: `fakeredis>=2.30`
