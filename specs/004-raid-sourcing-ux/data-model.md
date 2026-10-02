# Phase 1 Data Model: Raid Sourcing, Tracking & Report UX

This feature is largely behavioral; the only persistent schema change is one additive column.
Everything else is new in-transit contracts (WS frame + REST body) and one in-process cache.

---

## Persistent entities

### TrackedRaid (edited)

`backend/app/db/models.py` — one new column; all existing columns unchanged.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID (PK) | unchanged |
| report_code | str(32), unique, indexed | unchanged — natural dedup key |
| label | str(200) | unchanged (`"<guild> — <zone> — <date>"`) |
| zone | str(120) \| null | unchanged |
| guild | str(120) \| null | unchanged |
| report_started_at | datetime(tz) \| null | **now surfaced in UI** (US2): the raid's own date **and time** |
| first_seen_at | datetime(tz) | unchanged |
| last_asked_at | datetime(tz) | unchanged — list ordering key |
| last_conversation_id | UUID \| null (FK) | unchanged |
| **encounters** | **JSON \| null** | **NEW** — deduped distinct boss list for this report (US2 display + US4 checkboxes) |

**`encounters` element shape** (validated at the capture edge via `EncounterOut`):

```json
{ "encounter_id": 2902, "name": "Ulgrax the Devourer", "difficulty": 5, "kill": true }
```

Rules:
- Deduped by `encounter_id`; trash pulls / null `encounterID` excluded.
- `kill` is `true` if **any** pull of that encounter was a kill; otherwise `false`.
- Backfilled on each successful `get_report_fights`; merges with (does not blindly overwrite)
  any previously stored encounters for the report.
- Nullable/empty is valid — a raid tracked via a non-fight tool has `encounters = []`/`null`.

**Migration**: added idempotently in `main.py` lifespan (Postgres `ALTER TABLE tracked_raids
ADD COLUMN IF NOT EXISTS encounters JSONB`; SQLite test DBs get it via `create_all`), mirroring
the existing `messages.status` pattern.

### Unchanged

`Conversation`, `Message`, `CapturedGraph` — no changes. The PDF fix (US3) reads existing
`Message`/`CapturedGraph` rows; it changes rendering only, not storage.

---

## In-process state (not persisted)

### Greeting cache (US5)

`app.state.greeting_cache: dict[str, str]` — maps model id → generated Barnaby greeting text.

- Primed for the default model at startup (lifespan); other models filled lazily on first use.
- Lives for the process lifetime; refreshed on restart (FR-023). Not per-user (single-guild
  app), not persisted to the DB.

### Theme tokens & spell registry (US6, frontend-only)

Not persisted; defined in source as the single source of truth for the fixed look:

- **Theme tokens** — CSS variables on `:root` in `frontend/src/index.css` (color/font/glow/
  texture). One fixed theme; no runtime variants, no user switcher.
- **Spell registry** — `frontend/src/lib/spells.ts`: `Record<toolName, { icon, hue, verb, flavor[] }>`
  plus a `DEFAULT_SPELL`. Keys MUST cover every real tool name (16 WCL tools + `web_search`).
- **Per-turn spell state** — transient UI state: active/resolved/fizzled cards keyed by tool
  call id, each holding `{ name, status, summary?, ms?, progress? }` derived from WS frames.

---

## In-transit contracts (new / edited)

### EncounterOut (new Pydantic model) — `backend/app/schemas.py`

```
EncounterOut:
  encounter_id: int
  name: str
  difficulty: int | None = None
  kill: bool | None = None
```

### EncountersFrame (new WS frame) — server → client

```
EncountersFrame:
  type: "encounters"
  report_code: str
  encounters: list[EncounterOut]   # distinct, deduped
```

Emitted from `ws.py::_handle_tool_end` immediately after the `tool_end` for a successful
`get_report_fights`. Only emitted when `encounters` is non-empty.

### RaidOut (edited) — `backend/app/schemas.py`

Add `encounters: list[EncounterOut] = []` so the sidebar can show boss(es). All other fields
unchanged; `report_started_at` is already present and now consumed by the UI.

### GreetingResponse (new REST body) — `backend/app/schemas.py`

```
GreetingResponse:
  greeting: str
```

Returned by `GET /api/greeting?model=<id>`.

### ToolEndFrame (edited) + ToolProgressFrame (new, optional) — US6

```
ToolEndFrame (edited):
  type: "tool_end"
  name: str
  ok: bool = True
  summary: str | None = None   # NEW — short human-readable result summary (≤140 chars)
  ms: int | None = None        # NEW — elapsed duration of the tool call

ToolProgressFrame (new, optional):
  type: "tool_progress"
  id: str                      # correlates to the tool call
  done: int
  total: int
  note: str | None = None
```

`summary` is produced by `backend/app/services/tool_summary.py` from the tool result; `ms` is
timed in `agent_runner.stream_response`. Both are additive and optional — older clients ignore
them. `tool_progress` is only emitted by tools that can report progress.

### Frontend mirrors — `frontend/src/types.ts`, `frontend/src/api/wsClient.ts`

- `Frame` union gains `{ type: "encounters"; report_code: string; encounters: Encounter[] }`,
  optional `{ type: "tool_progress"; id: string; done: number; total: number; note?: string }`,
  and `summary?`/`ms?` on the existing `tool_end` member.
- `Encounter` interface `{ encounter_id: number; name: string; difficulty?: number; kill?: boolean }`.
- `Raid` interface gains `encounters: Encounter[]`.
- Per-turn UI state tracks the encounters surfaced on the latest sourcing turn and the user's
  current checkbox selection (reset per turn — FR-020), plus the spell-card state per tool call
  id (US6).

---

## Validation & integrity rules

- **Dedup (US2)**: raid identity stays `report_code`-unique; the upsert is made race-safe
  (`ON CONFLICT`/`IntegrityError` fallback) so concurrent first-time inserts converge to one row.
- **Encounters dedup (US4)**: distinct by `encounter_id` before persisting and before emitting
  the frame; repeated pulls of the same boss collapse to one checkbox (FR-019).
- **Source links (US1)**: no stored entity — links are produced inline by the agent from
  identifiers already in tool results; the frontend only adjusts link target/rel.
- **Greeting (US5)**: cache values are plain strings; a generation failure yields no cache
  entry and the endpoint returns an empty/omitted greeting so the client opens a clean chat.
