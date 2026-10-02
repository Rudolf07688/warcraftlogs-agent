# Phase 1 Data Model: Personalized Guild Context, Interactive Artifacts & Faster Analysis

Entities and persistence for feature 005. New tables are additive (created via
`Base.metadata.create_all` in `lifespan`), reusing the existing dual-dialect helpers
`_JSON` (JSONB on Postgres / JSON on SQLite) and `_UUID`.

## Entity overview

| Entity | Store | New? | Purpose |
|--------|-------|------|---------|
| UserCharacter | `user_characters` table | new | Self + friend characters, each with a resolved active spec + persisted guide |
| GuildProfile | `guild_profile` table (singleton) | new | The one main guild + optional recent-progression summary |
| Artifact | `artifacts` table | new | Agent-declared chart (chart spec), persisted for reload + PDF |
| Cached Tool Result | in-process `TTLCache` | new | WCL query results keyed by query+variables (not persisted) |
| ChartSpec | transient (tool result + `artifacts.spec_json`) | new | Single source of truth for Plotly (UI) + matplotlib (PDF) |
| Profile Context | transient (built per turn) | new | Compact preamble injected into the model input |
| CapturedGraph | `captured_graphs` table | existing | Reused; `message_seq` now assigned at turn end |
| TrackedRaid / Conversation / Message | existing tables | existing | Unchanged |

---

## UserCharacter (`user_characters`)

A self or friend character in the single global profile.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | `default=uuid4` |
| `role` | str(10) | `"self"` or `"friend"` |
| `name` | str(100) | Character name |
| `server` | str(100) | Realm (slugified when queried) |
| `region` | str(8) | `US`/`EU`/`KR`/`TW`/`CN` |
| `class_name` | str(40) \| null | Resolved by the guide task |
| `active_spec` | str(40) \| null | Resolved by the guide task |
| `guide_markdown` | Text \| null | Persisted spec guide |
| `guide_status` | str(10) | `"pending"` \| `"ready"` \| `"failed"` \| `"none"` (default `"none"`) |
| `guide_updated_at` | datetime(tz) \| null | When the guide last succeeded |
| `created_at` / `updated_at` | datetime(tz) | `server_default=now()`, `onupdate=now()` |

**Constraints / rules**
- Uniqueness: `UniqueConstraint(name, server, region, role)` — no duplicate identical entry.
- At most **one** `role == "self"` row: enforced in the repository (`PUT /self` upserts the single
  self row rather than inserting a second).
- Identity = `(name, server, region)` — must be unambiguous (FR-001 edge case); if WCL resolution is
  ambiguous/not found, the row still saves with `guide_status="failed"`/`"none"` and `active_spec=NULL`.

**State (guide lifecycle)**: `none` → (`pending` on lock-in) → `ready` | `failed`. Re-lock resets to
`pending`.

---

## GuildProfile (`guild_profile`)

The single main guild (one-main-guild limit, FR-003). Singleton row.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | `default=uuid4` |
| `name` | str(120) | Guild name |
| `server` | str(100) | Realm |
| `region` | str(8) | Region |
| `summary_markdown` | Text \| null | Optional recent-progression summary (guild "guide") |
| `summary_status` | str(10) | `"pending"`/`"ready"`/`"failed"`/`"none"` |
| `summary_updated_at` | datetime(tz) \| null | |
| `created_at` / `updated_at` | datetime(tz) | |

**Rules**: `PUT /api/profile/guild` replaces the single row (delete-then-insert or upsert of the lone
row) — setting a new main guild supersedes the previous one (FR-003). `DELETE` clears it.

---

## Artifact (`artifacts`)

An agent-declared chart, persisted so it re-renders on reload (FR-011) and prints in the PDF (FR-024).

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | `default=uuid4` |
| `conversation_id` | UUID FK → `conversations.id` | `ondelete=CASCADE`, indexed |
| `message_seq` | int \| null | Assigned at turn end (the agent message this chart belongs to) |
| `kind` | str(20) | `"line"`/`"bar"`/`"scatter"`/`"area"` |
| `title` | str(200) | Chart title |
| `spec_json` | `_JSON` | The `ChartSpec` (single source of truth) |
| `created_at` | datetime(tz) | `server_default=now()` |

**Rules**
- Mirrors `CapturedGraph` (same conversation linkage + `message_seq` pattern).
- Figure JSON for the UI is **derived** from `spec_json` at emit/read time (not stored twice).
- Oversized specs are bounded before persistence (cap on points/series — see
  `services/charts.py`; consistent with the existing graph-size guard `_cap`).

---

## ChartSpec (transient contract; stored as `artifacts.spec_json`)

Single source of truth for both renderers. Validated by the `create_chart` tool and by a Pydantic
`ChartSpec` on the backend boundary.

```jsonc
{
  "kind": "line | bar | scatter | area",
  "title": "Raid DPS over time — aBcDeFgH #12",
  "x_label": "Time (s)",          // optional
  "y_label": "DPS",               // optional
  "series": [
    { "name": "Raid", "x": [0, 5, 10], "y": [1200000, 1350000, 1180000] },
    { "name": "Boss", "y": [900000, 1010000, 870000] }   // x optional → index
  ],
  "source_url": "https://www.warcraftlogs.com/reports/aBcDeFgH#fight=12"  // optional (US1 link)
}
```

**Validation rules**
- `kind` ∈ the four kinds; unknown → tool error (agent retries).
- `series` non-empty; each `y` non-empty; `x` (if given) length matches `y`.
- Point/series counts bounded (e.g. ≤ 12 series, ≤ ~500 points/series) to protect storage + render.

---

## Cached Tool Result (in-process `TTLCache`, `wcl_agent/cache.py`)

Not persisted. Entry = `{ key, value (deep-copied dict), expires_at }`.

| Aspect | Value |
|--------|-------|
| Key | `sha256(query + " " + json.dumps(variables, sort_keys=True, default=str))` |
| Tier: immutable | report-scoped query (`reportData`/`report(`/`code` var) → `WCL_CACHE_TTL_REPORT_S` (~86400) |
| Tier: volatile | leaderboard/rankings/other → `WCL_CACHE_TTL_LEADERBOARD_S` (~3600) |
| Bypass | `rateLimitData` queries (always live) |
| Eviction | LRU bound (e.g. 512 entries) + lazy expiry on read |
| Isolation | deep copy on read (callers can't mutate stored entries) |

---

## Profile Context (transient; `services/profile_context.py`)

Built per turn from `UserCharacter` + `GuildProfile`, prepended to the model input only (never
persisted/shown). Shape (illustrative):

```text
KNOWN PLAYER CONTEXT (use only when the question is about the user, their friends, or their guild;
answer population-level questions normally):
- You (self): <Name>-<Server> (<Region>) — <Class> <Spec>
- Friends: <Name>-<Server> (<Region>) — <Class> <Spec>; …
- Main guild: <Guild>-<Server> (<Region>)
- Spec guides:
  ## <Name> — <Spec>
  <guide_markdown, capped>
```

**Rules**: total injected guide text is capped (a few KB) to bound tokens; omitted entirely when the
profile is empty (so with no profile, behavior is unchanged — FR-006).

---

## Relationships

```text
Conversation 1──* Message
Conversation 1──* CapturedGraph        (message_seq → Message.seq, assigned at turn end)
Conversation 1──* Artifact             (message_seq → Message.seq, assigned at turn end)
GuildProfile (singleton)               (no FK; global profile)
UserCharacter * (role=self: 1, friend: N)
```

## Repository additions (`db/repository.py`)

- `get_profile(session)` → self row, friend rows, guild row.
- `upsert_self(session, CharacterIn)` / `add_friend` / `delete_friend(id)`.
- `set_guild(session, GuildIn)` / `delete_guild(session)`.
- `set_character_guide(session, id, *, class_name, active_spec, markdown, status)`.
- `add_artifact(session, *, conversation_id, kind, title, spec_json)` / `list_artifacts(conv_id)`.
- `assign_message_seq_to_turn_captures(session, conv_id, seq)` — sets `message_seq=seq` on this
  conversation's `message_seq IS NULL` artifacts **and** captured graphs (turns are serialized per
  socket, so these are exactly the current turn's captures).

## Migration notes

- All three new tables created by `create_all` in `lifespan` (new tables only — safe/idempotent).
- No `ALTER` on existing tables required.
- Dual-dialect types reused so SQLite-backed tests cover the same models.
