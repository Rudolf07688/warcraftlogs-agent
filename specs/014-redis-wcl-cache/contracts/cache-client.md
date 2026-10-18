# Contract: Shared Cache Client (`wcl_agent/cache.py`)

**Feature**: 014-redis-wcl-cache

Internal module contract. `wcl_agent` stays standalone (no backend imports); with no
`REDIS_URL` the cache is disabled and every lookup goes straight to its loader.

---

## Public surface

```python
class CacheFamily(StrEnum): ...            # the seven families (data-model.md)

async def get_or_load(
    family: CacheFamily,
    key: str,
    model: type[M],
    loader: Callable[[], Awaitable[M | None]],
    *,
    ttl: int | Callable[[M], int] | None = None,  # seconds, a function of the loaded value, or None → family default
    force_refresh: bool = False,
) -> M | None
    """The only way code reads or writes cached WCL data. None = 'not found' (negative-cached)."""

async def get_many_or_load(
    family: CacheFamily, keys_: Sequence[str], model: type[M],
    batch_loader: Callable[[list[int]], Awaitable[list[M | None]]], *, ttl=None,
) -> list[M | None]
    """Batched form for background batch work: one MGET, ONE loader call for all misses,
    one pipelined write. No stampede lock. Same outcomes, memo and fail-open (PERF-001)."""

async def try_claim_refresh(user_id: str, char_id: int) -> bool
    """SET chat:refresh:{user_id}:{char_id} NX EX 60. True = refresh allowed. Redis down → True."""

def set_refresh_actor(user_id: str | None) -> None   # ContextVar, set by ws.py per turn
def get_refresh_actor() -> str | None

async def read_stats(days: int) -> CacheStats       # metrics hashes + INFO, see cache-stats-api.md
async def aclose_redis() -> None                    # called by wcl_client.aclose_clients()

keys.char_id(region, realm, name) -> str            # and the other builders in data-model.md
```

Removed: `TTLCache`, `get_cache`, `cache_key`, `ttl_for`, `is_report_scoped`,
`is_rate_limit`, `report_ttl`, `leaderboard_ttl`, `max_bytes`, `set_scope_prefix`,
`get_scope_prefix`. `_env_int` stays (used by `context_trim`, `wcl_client`).

---

## Guarantees of `get_or_load`

| # | Guarantee | Req |
|---|---|---|
| C1 | **Hit**: valid stored JSON → `model.model_validate_json`, outcome `hit`, no loader call. | FR-001 |
| C2 | **Negative hit**: stored `{"_missing": true}` → returns `None`, outcome `neg_hit`, no loader call. | FR-006 |
| C3 | **Miss**: lock winner calls `loader()` once, writes `SET key EX ttl·U(1,1+jitter)` (no jitter for `oauth_token`, so it never outlives the token), outcome `miss` + `load_ms`, deletes the lock. `None` from the loader writes the marker with `WCL_NEG_CACHE_TTL`. | FR-002, FR-006 |
| C4 | **Contention**: N concurrent misses on one key → exactly 1 loader call. Callers in the same process join the in-flight lookup directly (PERF-006) and count as `hit`; callers in other processes poll for up to `lock_wait_ms` (2s) and return the winner's value as `hit`. Losers that time out call the loader themselves, record `lock_timeout`, and do not write. | FR-010, SC-003 |
| C5 | **Loader error**: lock deleted, outcome `error`, exception re-raised unchanged, nothing written. | FR-011 |
| C6 | **Corrupt value**: JSON/validation failure → `DEL key`, outcome `error`, then continue as a miss. | FR-013 |
| C7 | **Redis failure** (connect, timeout, any `RedisError`): outcome `redis_error` (process counter, flushed later), loader called directly, no writes; for 5s after a failure Redis is not contacted again on that loop. Callers never see a Redis exception. | FR-012, SC-004 |
| C8 | **Disabled** (`WCL_CACHE_ENABLED=false` or no `REDIS_URL`): loader called directly; no Redis traffic; no metrics. | FR-014 |
| C9 | **Force refresh**: skips the read, still takes the lock, overwrites the key. | FR-015 |
| C10 | **Metrics never block or fail a request**: outcomes are counted in-process and flushed in one pipeline every 2 s (and on shutdown); a failed flush keeps its counts for the next one (PERF-007). |
| C13 | **Memo** (PERF-003): `char_id` (1 h) and `world_zones` (5 min) are also kept in-process in front of Redis — with or without Redis. Memo hits make no Redis call and are not counted. `force_refresh` bypasses it. Memoised values are shared instances: read-only. | FR-019 |
| C11 | **Keys**: every `wcl:` key comes from a `keys.*` builder; none contains user/tenant/conversation ids. | FR-008, FR-003 |
| C12 | **Cancellation**: a cancelled caller holding the lock deletes it (`finally`) so others are not blocked for the full `lock_ms`. | — |

---

## WCL client changes (`wcl_agent/wcl_client.py`, amends 013's `wcl-async-client.md`)

| # | Change | Req |
|---|---|---|
| W1 | `query(query, variables)` — the `cache=` kwarg and all result caching are removed (G2 of 013 is withdrawn). | FR-025 |
| W2 | Single-flight (013 G3/G4) stays, keyed by `sha256(query + canonical variables)`. | — |
| W3 | Retry 429/5xx at most 2 times, backoff `0.5·2ⁿ s` + jitter, `Retry-After` honoured (≤10s), inside the existing query timeout. | FR-017 |
| W4 | Every request carries `rateLimitData { pointsSpentThisHour }` in its top-level selection; it is stripped from the returned payload and logged as `wcl_cost op=… points_this_hour=… delta=…`. | FR-016, FR-026 |
| W5 | Token: process memo with expiry, then `get_or_load(OAUTH_TOKEN, ttl=expires_in−60)`; a 401 drops the memo and reloads with `force_refresh=True`. | FR-001 |
| W6 | `aclose_clients()` also closes each loop's Redis client. | — |

---

## Call-site contract (who uses which family)

| Caller | Family | Notes |
|---|---|---|
| `wcl_agent.report_tools.resolve_character(name, server, region)` (new) | char_id | returns `CharacterRef \| None`; both character tools and recent raids call it first |
| `report_tools.get_character_zone_rankings(..., force_refresh=False)` | char_overview | queries `character(id:)`; not-found answered from char_id |
| `report_tools.get_character_encounter_rankings(..., force_refresh=False)` | char_overview | same |
| `recent_raids.fetch_listed_reports` | char_id + char_reports | `resolve_characters` + `get_many_or_load`: at most one aliased request each (PERF-001) |
| `report_tools.load_report_summary(code)` / `load_report_summaries(codes)` | report_summary | used by `get_report_fights`, `get_report_metadata`; the batched form by `recent_raids.fetch_report_details` (one aliased request per 10 uncached codes, per-code fallback on a GraphQL error) |
| `report_tools.get_report_table` with `source_id > 0` | report_player | `source_id == 0` stays uncached |
| `wcl_client.AsyncWCLClient._token` | oauth_token | W5 |
| `wcl_agent.menu.load_world_zones()` (new, shared; `patch` imports `menu`) | world_zones | used by `current_patch`, `raid_zone_ids`, `tools.find_encounter`, `menu` |

Tool return shapes seen by the agent are unchanged, except the character tools may add
`"refresh": "done" | "skipped_recent"` when `force_refresh=True`.
