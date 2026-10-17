# Data Model: Welcome Page with My Recent Raids

**Feature**: 013-welcome-recent-raids | **Date**: 2026-10-16

There are three new tenant-owned tables in one migration, `0010_recent_raids`. Each gets `tenant_id`, row-level security enabled, and the standard tenant policy:

```sql
tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
```

granted to the runtime role, mirroring `0005_known_entities`. No existing table changes.

---

## 1. `recent_raids`

One row for each Warcraft Logs report in which at least one of the tenant's own characters was logged. Non-raid reports (Mythic+, for example) are stored too, so they are never fetched again, but they are left out of the welcome list.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | uuid PK | no | |
| `tenant_id` | uuid FK → `tenants.id` ON DELETE CASCADE | no | RLS scope |
| `report_code` | varchar(32) | no | WCL report code |
| `title` | varchar(200) | no | Report title (fallback label) |
| `zone_id` | int | yes | WCL zone id |
| `zone_name` | varchar(120) | yes | Raid name shown on the card |
| `guild_name` | varchar(120) | yes | For the tracked-raid label when investigated |
| `started_at` | timestamptz | no | From `startTime` (ms) |
| `ended_at` | timestamptz | no | From `endTime` (ms); moves while the log is live |
| `difficulty` | smallint | yes | Highest raid difficulty among boss fights (WCL ids: 1 LFR, 3 Normal, 4 Heroic, 5 Mythic) |
| `bosses_pulled` | smallint | yes | Distinct boss encounter ids pulled. NULL until details are fetched |
| `bosses_killed` | smallint | yes | Distinct boss encounter ids killed. NULL until details are fetched |
| `is_raid` | bool | no | Zone offers raid difficulties (research R2) |
| `is_final` | bool | no, default false | `ended_at` is more than 2 h before the detail fetch. Details are never fetched again once true |
| `details_fetched_at` | timestamptz | yes | Last detail fetch |
| `first_seen_at` | timestamptz | no, default now() | |

**Constraints and indexes**
- `UNIQUE (tenant_id, report_code)` named `uq_recent_raid_tenant_code`. This is the dedupe key (FR-006, SC-005).
- `INDEX (tenant_id, started_at)` named `ix_recent_raids_tenant_started`, for the newest-first list.

**Validation**
- `bosses_killed ≤ bosses_pulled`.
- `difficulty` is one of {1, 3, 4, 5} or NULL.

**Lifecycle**

```text
(list step sees code) ─► inserted: is_final=false, details NULL
        │
        ▼ detail step
  details filled ──► ended_at older than 2 h? ── yes ─► is_final=true  (never fetched again: FR-012)
        │                                       └─ no ─► stays non-final, details fetched again next refresh
```

---

## 2. `recent_raid_characters`

Links a recent raid to the tenant's own characters that took part. One raid can have several links (FR-006).

| Column | Type | Null | Notes |
|---|---|---|---|
| `raid_id` | uuid FK → `recent_raids.id` ON DELETE CASCADE | no | PK part |
| `character_id` | uuid FK → `user_characters.id` ON DELETE CASCADE | no | PK part. Must be a `role = 'self'` character |
| `tenant_id` | uuid FK → `tenants.id` ON DELETE CASCADE | no | RLS scope |

**Constraints**
- `PRIMARY KEY (raid_id, character_id)`.
- `INDEX (tenant_id, character_id)`.

**Behaviour**
- Removing an own character deletes its links through the cascade, so the list query (which inner-joins the links) stops showing raids no remaining own character attended. That gives FR-016 with no extra code.
- A renamed or transferred character is a new `user_characters` row (edge case), so the same rule applies.

---

## 3. `recent_raid_refresh`

One row per tenant. It records the refresh state, and it is the lock across instances (FR-013, FR-025, FR-026, research R4).

| Column | Type | Null | Notes |
|---|---|---|---|
| `tenant_id` | uuid PK, FK → `tenants.id` ON DELETE CASCADE | no | One row per tenant. RLS scope |
| `status` | varchar(10) | no, default `'idle'` | `idle` · `running` · `succeeded` · `failed` |
| `run_id` | uuid | yes | Set on each claim. Terminal writes must match it |
| `started_at` | timestamptz | yes | When the current or last run was claimed |
| `finished_at` | timestamptz | yes | When the last run recorded an outcome |
| `last_success_at` | timestamptz | yes | Shown as "updated N min ago" |
| `last_error` | varchar(200) | yes | Short, user-safe reason: `wcl_unavailable`, `rate_limited`, `timeout` or `unknown` |
| `character_set` | varchar(64) | yes | sha256 of the sorted `name\|server\|region` of the own characters when the run was claimed |

**State transitions**

```text
          claim (gate open)                 outcome written WHERE run_id = mine
 idle ──────────────────────► running ─────────────────────────────► succeeded | failed
  ▲                            │  ▲                                        │
  │                            │  └── claim again when started_at < now-5m (stale, FR-026)
  └────────────────────────────┴──────── claim again when gate open ◄──────┘
```

The claim gate (all conditions in one `UPDATE … RETURNING`):
- **running but stale** (`started_at < now − 5 min`): always claimable, because the previous run never recorded its outcome; **or**
- **not running, and one of**:
  - `force`, allowed only when `status = 'failed'`;
  - never finished;
  - `finished_at < now − 15 min`;
  - `character_set ≠` the current hash.

---

## 4. Pydantic and dataclass contracts (Principle IV)

**API models** (`backend/app/schemas.py`):

```python
class RecentRaidCharacterOut(BaseModel):
    name: str
    server: str
    region: str

class RecentRaidOut(BaseModel):
    report_code: str
    title: str
    zone_name: str | None
    started_at: datetime
    difficulty: int | None
    bosses_pulled: int | None
    bosses_killed: int | None
    is_final: bool
    characters: list[RecentRaidCharacterOut]   # ≥ 1

class RecentRaidsRefreshOut(BaseModel):
    status: Literal["idle", "running", "succeeded", "failed"]
    last_success_at: datetime | None
    last_error: str | None

class RecentRaidsResponse(BaseModel):
    has_characters: bool
    raids: list[RecentRaidOut]                 # ≤ 20, newest first, is_raid only
    refresh: RecentRaidsRefreshOut
```

**Internal value objects** (`backend/app/services/recent_raid_types.py`, dataclasses, so both the service and the repository can import them without a cycle):

```python
@dataclass(frozen=True)
class ListedReport:      # one item from the recentReports list step
    code: str
    title: str
    zone_id: int | None
    zone_name: str | None
    started_at: datetime
    ended_at: datetime
    character_ids: frozenset[uuid.UUID]
    is_raid: bool = False  # from zone id alone, so a raid lists before its details arrive

@dataclass(frozen=True)
class ReportDetails:     # the detail step
    ended_at: datetime
    difficulty: int | None
    bosses_pulled: int
    bosses_killed: int
    is_raid: bool
```

**WCL client** (`wcl_agent/wcl_client.py`), plain module types:
- `Lane = Literal["interactive", "background"]`
- `background_lane()`: a context manager that sets the `wcl_lane` ContextVar.
- `LaneLimiter(total: int, background_cap: int)`: `acquire()` and `release()` take their lane from the ContextVar. It is used as `async with limiter.slot():`.

---

## 5. Existing entities (read-only use)

- **`user_characters`** (`role = 'self'`): the set of characters to look up, and the FK target for links.
- **`tracked_raids`**: a row is created from a recent raid on investigation (research R10). The schema is unchanged.
- **WCL cache** (`wcl_agent/cache.py`): stores **raw bytes** instead of parsed objects. The key and TTL rules are unchanged, plus the `cache=False` bypass used by the list step.
