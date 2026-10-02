# Caching Contract — feature 005 (US4)

An in-process cache wraps the single Warcraft Logs query chokepoint. Transparent to all tools.

## Location
`wcl_agent/cache.py` provides a `TTLCache`; `WCLClient.query` consults it before issuing a network
request. Because every tool (and `run_wcl_graphql`) calls `query`, one change caches them all (DRY).

## Behavior
```
query(query_str, variables):
    if is_rate_limit(query_str):            # rateLimitData → never cache
        return live()
    key = sha256(query_str + " " + json.dumps(variables, sort_keys=True, default=str))
    hit = cache.get(key)                    # lazy-expires on read
    if hit is not None:
        return deepcopy(hit)                # callers never mutate the stored entry
    result = live()                         # network + token auth as today
    ttl = TTL_REPORT if is_report_scoped(query_str, variables) else TTL_LEADERBOARD
    cache.set(key, deepcopy(result), ttl)
    return result
```

## Tiers (freshness windows)
| Tier | Matches | Default TTL | Env |
|------|---------|-------------|-----|
| Immutable (report-scoped) | query references `reportData` / `report(` or a `code` variable | 86400 s (~24h) | `WCL_CACHE_TTL_REPORT_S` |
| Volatile (leaderboard/rankings/other) | everything else (`characterRankings`, `worldData`, `characterData` rankings, …) | 3600 s (~1h) | `WCL_CACHE_TTL_LEADERBOARD_S` |
| Bypass | `rateLimitData` | — (always live) | — |

## Keying rules (FR-020)
- Key includes the full query string **and** all variables (sorted), so different encounter/difficulty/
  metric/pages/class/spec/report/fight/source arguments never collide.
- `None` vs absent variables are normalized by `json.dumps` with `sort_keys`.

## Guarantees
- A hit performs **no** network I/O and spends **zero** WCL API points (FR-018, SC-005).
- Entries expire by their tier window; an expired key refetches (FR-019) — stale leaderboard data is
  never served beyond ~1h.
- Deep-copy on read/write isolates cached entries from caller mutation.
- LRU bound (default 512 entries) caps memory.

## Non-goals (YAGNI)
- No cross-restart / cross-process persistence (single-process scale). The cache sits behind a small
  interface, so a persistent backend could be slotted in later without touching callers.
- Does not cache `create_chart` (no WCL call) or final agent answers (clarified: cache tool results).

## Testing
`backend/tests/test_wcl_cache.py` (or `wcl_agent` test): monkeypatch the HTTP layer to count calls;
assert (1) identical query+variables hits the cache (one network call, two returns), (2) different
variables miss, (3) report-scoped vs leaderboard get the right TTL, (4) `rateLimitData` always bypasses,
(5) a returned dict mutated by the caller does not corrupt the next hit.
