# Data Model: Shared Warcraft Logs Cache (feature 014)

All cached values are Pydantic models (Principle IV) serialised with `model_dump_json()`.
Internal config is dataclasses. Models live in `wcl_agent/cache_models.py` unless noted.

## Cache configuration (internal, dataclasses / enums — `wcl_agent/cache.py`)

```python
class CacheFamily(StrEnum):
    CHAR_ID = "char_id"; CHAR_OVERVIEW = "char_overview"; CHAR_REPORTS = "char_reports"
    REPORT_SUMMARY = "report_summary"; REPORT_PLAYER = "report_player"
    OAUTH_TOKEN = "oauth_token"; WORLD_ZONES = "world_zones"

class Outcome(StrEnum):
    HIT = "hit"; MISS = "miss"; NEG_HIT = "neg_hit"; LOCK_TIMEOUT = "lock_timeout"
    ERROR = "error"; REDIS_ERROR = "redis_error"

@dataclass(frozen=True)
class FamilyConfig:
    default_ttl_s: int       # overridable by WCL_CACHE_TTL_{FAMILY}
    review_below: float      # hit-rate threshold for status "review"
```

| Family | default_ttl_s | review_below |
|---|---|---|
| char_id | 86400 | 0.90 |
| oauth_token | 0 (always passed: `expires_in − 60`) | 0.90 |
| world_zones | 3600 | 0.90 |
| char_overview | 600 | 0.60 |
| char_reports | 300 | 0.60 |
| report_summary | 86400 | 0.40 |
| report_player | 86400 | 0.40 |

`CacheSettings` (frozen dataclass, read from env once per loop client): `enabled`
(`WCL_CACHE_ENABLED` and `REDIS_URL` set), `redis_url`, `jitter` (0.10), `lock_ms` (10000),
`lock_wait_ms` (2000), `neg_ttl_s` (60), `metrics_retention_days` (35), `unfinished_ttl_s` (120).

## Key builders (`wcl_agent/cache.py`, `keys` namespace)

| Builder | Key | Normalisation |
|---|---|---|
| `char_id(region, realm, name)` | `wcl:v1:char_id:{region}:{realm_slug}:{name}` | region upper→lower; realm via `_server_slug` (moved from `report_tools` to `wcl_agent/normalize.py`); name `strip().lower()` |
| `char_zone(id, zone, metric, diff)` | `wcl:v1:char:{id}:overview:zone:{zone or 0}:{metric}:{diff or 0}` | — |
| `char_enc(id, enc, metric, diff)` | `wcl:v1:char:{id}:overview:enc:{enc}:{metric}:{diff or 0}` | — |
| `char_reports(id, limit)` | `wcl:v1:char:{id}:reports:{limit}` | — |
| `report_summary(code)` | `wcl:v1:report:{code}:summary` | code `strip()` (case-sensitive) |
| `report_player(code, source, data_type, fight, ability, hostility)` | `wcl:v1:report:{code}:player:{source}:table:{data_type}:{fight}:{ability}:{hostility}` | — |
| `OAUTH_TOKEN` | `wcl:v1:oauth:token` | — |
| `WORLD_ZONES` | `wcl:v1:world:zones` | — |
| lock | `lock:{key}` | — |
| metrics | `wcl:metrics:v1:{family}:{YYYYMMDD}` | UTC date |
| refresh limit | `chat:refresh:{user_id}:{char_id}` | the only key with a user id; never under `wcl:` |

**Rule (tested)**: no builder under `wcl:` accepts a user, tenant or conversation id.

## Cached value models

### CharacterRef — family `char_id`
| Field | Type | Notes |
|---|---|---|
| id | int | WCL character id |
| name | str | canonical capitalisation from WCL |
| realm | str | server slug |
| region | str | e.g. `"eu"` |
| class_id | int \| None | |

Not found → `{"_missing": true}` marker (no model instance); `get_or_load` returns `None`.

### CharacterRankings — family `char_overview`
| Field | Type | Notes |
|---|---|---|
| name | str | |
| scope | `Literal["zone","encounter"]` | which ranking query produced it |
| rankings | `Any` (JSON) | WCL's `zoneRankings` / `encounterRankings` JSON scalar, unchanged |

The tool wraps it with `_acap` and `with_envelope` **after** the cache, so size capping and
provenance never enter the stored value.

### CharacterReports — family `char_reports`
| Field | Type |
|---|---|
| reports | `list[RecentReport]` |

`RecentReport`: `code: str`, `title: str`, `start_time_ms: int`, `end_time_ms: int`,
`zone_id: int | None`, `zone_name: str | None`, `guild_name: str | None`.
`recent_raids.fetch_listed_reports` maps these to its existing `ListedReport` (unchanged).

### ReportSummary — family `report_summary`
| Field | Type | Notes |
|---|---|---|
| code | str | |
| title | str \| None | |
| start_time_ms | int | |
| end_time_ms | int | drives finished/unfinished TTL |
| zone_id / zone_name | int \| None / str \| None | |
| guild_name | str \| None | |
| players | `dict[int, PlayerRef]` | `PlayerRef`: `name`, `class_name` |
| fights | `list[FightSummary]` | `id, name, encounter_id, difficulty, kill, average_item_level, size, player_ids` |

Derived (pure functions, no extra query):
- `get_report_fights` result (today's shape, unchanged for the agent),
- `get_report_metadata` result (title, zone, guild, start_time_ms),
- `recent_raids._details_from` input (end time, zone id, encounter fights).

`is_finished(summary, now)` → `now − end_time_ms ≥ FINAL_AFTER (2h)`; write TTL is the family
default when finished, else `unfinished_ttl_s`.

### PlayerTable — family `report_player`
| Field | Type |
|---|---|
| data | `Any` (JSON) — WCL `table` JSON scalar for one source |

Finished/unfinished TTL uses the report's `ReportSummary` when already cached; otherwise the
loader also reads `endTime` in the same query (one extra scalar field, no extra request).

### OAuthToken — family `oauth_token`
| Field | Type |
|---|---|
| access_token | str |
| expires_at | float (epoch s) |

### WorldZones — family `world_zones`
| Field | Type |
|---|---|
| zones | `list[dict[str, Any]]` — the `worldData.zones` list as today's helpers (`current_patch_from_zones`, `raid_zone_ids_from`, `menu`, `find_encounter`) already consume it |

Kept as plain dicts on purpose: four existing pure helpers take this list; re-typing it is a
separate refactor with no user value (Principle III).

## Metrics

### Daily counter hash (Redis)
`wcl:metrics:v1:{family}:{YYYYMMDD}` → `hit, miss, neg_hit, lock_timeout, error, redis_error,
load_ms_sum, load_count` (ints). TTL `metrics_retention_days`.

### Response models (`backend/app/schemas.py`, Pydantic)

```python
class FamilyStats(BaseModel):
    hits: int; misses: int; neg_hits: int; lock_timeouts: int
    errors: int; redis_errors: int
    hit_rate: float | None          # None when no lookups in window
    avg_load_ms: float | None
    status: Literal["ok", "review", "no_data"]

class RedisHealth(BaseModel):
    keyspace_hit_rate: float | None; evicted_keys: int; used_memory_mb: float

class CacheStats(BaseModel):
    window_days: int
    enabled: bool                    # WCL_CACHE_ENABLED and REDIS_URL set
    available: bool                  # Redis reachable now
    families: dict[str, FamilyStats] # all seven families, always present
    redis: RedisHealth | None
```

Derivations: `hit_rate = (hit + neg_hit) / (hit + neg_hit + miss)`;
`avg_load_ms = load_ms_sum / load_count`; `status = "no_data"` if denominator 0, `"review"` if
`hit_rate < review_below`, else `"ok"`.

## State transitions — one `get_or_load` call

```text
disabled ─────────────────────────────► loader() → return            (no metrics)
GET key ── value ok ───────────────────► HIT → return
        ── _missing marker ────────────► NEG_HIT → return None
        ── corrupt ── DEL ──┐
        ── none ────────────┤
force_refresh ──────────────┴► SET lock NX ── won ──► loader()
                                                      ├ ok → SET key (+jitter) [+metrics MISS, load_ms] → DEL lock → return
                                                      ├ None → SET marker neg_ttl → MISS → DEL lock → return None
                                                      └ raises → DEL lock → ERROR → re-raise
                                         ── lost ─► poll GET ≤ lock_wait_ms ── value → HIT → return
                                                                             └ timeout → loader() → LOCK_TIMEOUT (no write)
any Redis exception ───────────────────► REDIS_ERROR → loader() → return (no writes)
```
