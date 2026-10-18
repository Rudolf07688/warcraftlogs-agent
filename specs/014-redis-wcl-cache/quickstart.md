# Quickstart: Shared Warcraft Logs Cache (feature 014)

## 1. Run it

```bash
uv sync --extra test
docker compose up --build            # db + redis + backend + frontend
docker compose ps                    # redis: healthy; backend started after it
```

Host-side runs (CLI, pytest against a real Redis) use `REDIS_URL=redis://localhost:6379/0`
from `.env`. Unset `REDIS_URL` (or `WCL_CACHE_ENABLED=false`) to run with no cache.

## 2. Verify each story

**US5 – stack wiring**
```bash
docker compose exec redis redis-cli CONFIG GET maxmemory-policy   # allkeys-lru
docker compose exec redis redis-cli CONFIG GET save               # ""
```

**US1 – hits and quota**
1. Sign in, ask "How is <name> on <realm> <region> doing this tier?" twice.
2. `docker compose exec redis redis-cli --scan --pattern 'wcl:v1:*'` shows `char_id`,
   `char:{id}:overview:...`, `world:zones` keys and **no** tenant/user ids.
3. Backend logs: the second turn has no `wcl_cost` line for the character query.
4. Ask about a misspelt name twice within 60s → one WCL request, then `neg_hit`.

**US2 – cache down**
```bash
docker compose stop redis
# ask a character question → correct answer, no error in the chat
docker compose start redis
```
`/api/admin/cache-stats` afterwards shows `redis_errors > 0` for the families used.

**US3 – statistics** (signed in as a platform admin, in the browser or with the session cookie)
```bash
curl -s --cookie "__Host-session=<cookie>" 'http://localhost:5173/api/admin/cache-stats?days=7' | jq
```
A non-admin gets 403.

**US4 – forced refresh**: ask about a character, then "check again" → fresh fetch
(`wcl_cost` line); "check again" a second time within a minute → the agent says it just refreshed.

## 3. Tests

```bash
uv run pytest backend/tests/test_wcl_cache.py backend/tests/test_cache_stats.py -q
uv run pytest -q                      # whole suite; fakeredis, no real Redis needed
```

Required unit coverage (design doc §9): hit, miss, negative hit, 10 concurrent callers → 1
loader call, loader error, Redis down, corrupt value, disabled, force refresh, counters per
outcome, key normalisation (`"Rudolf"` == `"rudolf "`), no user data in keys.

## 4. Load check (SC-002, before settling TTLs)

Replay 100 realistic questions twice (benchmark harness, `wcl_agent/benchmark.py`), once with
`WCL_CACHE_ENABLED=false` and once with it on; compare the summed `wcl_cost delta` in the
logs and read per-family hit rates from the stats endpoint.

## 5. Security notes

- Redis holds the WCL bearer token (`wcl:v1:oauth:token`). The compose port mapping is for
  local development only; a production Redis must not be reachable from outside the backend's
  network.
- Only `chat:refresh:*` keys contain a user id; they expire after 60s.
