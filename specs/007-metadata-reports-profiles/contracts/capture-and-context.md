# Contract: Metadata capture & context injection (US1)

Internal (non-HTTP) contracts for capturing metadata from successful tool calls and surfacing it into the agent's per-turn context. All operate inside the already tenant-scoped turn transaction.

## Capture extractors (`backend/app/services/known_entities.py`, NEW)

Mirror the existing `capture_raid_from_tool` signature (`services/raids.py:57`) and best-effort discipline.

```python
async def capture_players_from_tool(
    session, *, tenant_id: uuid.UUID, name: str, ok: bool,
    args: dict, result: dict | None, conversation_id: uuid.UUID | None,
) -> int:                      # number of players upserted (0 when N/A)
    ...

async def capture_encounters_from_tool(
    session, *, tenant_id: uuid.UUID, name: str, ok: bool,
    args: dict, result: dict | None, conversation_id: uuid.UUID | None,
) -> int:                      # number of encounters upserted (0 when N/A)
    ...
```

**Rules**
- Return immediately (no write) when `ok` is false or `name` is not a relevant source tool.
- Player sources: `get_character_zone_rankings`, `get_character_encounter_rankings` (name/server/region from args; class/spec from result), `get_report_master_data` (actors). Skip records lacking an unambiguous `(name, server, region)`.
- Encounter source: `find_encounter` matches with a numeric `encounter_id` (+ name, zone id/name when present).
- Pure extraction helpers (`players_from_tool`, `encounters_from_find`) return typed lists; the async functions upsert via repository with dedup (see data-model dedup keys).
- **Best-effort**: never raise into the turn — a failure is logged and swallowed (FR-008). Writes participate in the existing commit-and-rescope guard.

## Hub wiring (`backend/app/api/ws.py` → `_handle_tool_end`)

Add alongside the existing capture calls (`ws.py:82-112`):
```python
players = await known_entities.capture_players_from_tool(session, tenant_id=tenant_id,
            name=name, ok=ok, args=args, result=result, conversation_id=conv_id)
encounters = await known_entities.capture_encounters_from_tool(session, tenant_id=tenant_id,
            name=name, ok=ok, args=args, result=result, conversation_id=conv_id)
```
- Include `players`/`encounters` in the existing “did we capture anything?” commit guard (`ws.py:115-117`) so a stream error can't lose them.
- No new WebSocket frame is required (metadata is silent context); the existing `raid_tracked`/`encounters` frames are unchanged.

## Repository helpers (`backend/app/db/repository.py`, NEW)

```python
async def upsert_known_player(session, *, tenant_id, name, server, region,
                              class_name=None, spec=None, source=None) -> KnownPlayer
async def upsert_known_encounter(session, *, tenant_id, encounter_id,
                                 encounter_name, zone_id=None, zone_name=None) -> KnownEncounter
async def list_recent_known_players(session, *, tenant_id, limit=15) -> list[KnownPlayer]
async def list_recent_known_encounters(session, *, tenant_id, limit=10) -> list[KnownEncounter]
async def list_recent_known_guilds(session, *, tenant_id, limit=10) -> list[str]   # derived from TrackedRaid.guild
# known raids reuse existing list_tracked_raids(...) ordered by last_asked_at
```
- All reads tenant-scoped; recency ordering uses the `(tenant_id, last_seen_at)` / `(tenant_id, last_asked_at)` indexes.

## Context injection (`backend/app/services/profile_context.py` → `build_preamble`, EXTENDED)

Extend the single preamble builder (do NOT add a second path). New optional parameters carry the capped, recency-ordered captured metadata; `ws.py` fetches and passes them.

```python
def build_preamble(
    self_character, friends, guild,
    *,
    known_raids=(), known_players=(), known_encounters=(), known_guilds=(),
) -> str: ...
```
- Appends a `RECENTLY SEEN (this account)` section after the existing profile/guide blocks:
  - `- Raids: <label>; <label>; …`
  - `- Players: <name-server (region) — class — spec>; …` (excluding any already in the profile)
  - `- Encounters: <encounter_name (zone_name)>; …`
  - `- Guilds: <guild>; …`
- The whole captured section is trimmed to a fixed char cap (new constant next to `_TOTAL_GUIDE_CHARS`); when all inputs are empty the section is omitted and the returned string is byte-identical to today (FR-011, SC-003, SC-008).
- Effective raid role (US4) is appended inside `_ident` for self/friend lines (see data-model 5.2).

## Spec→role SSOT (`wcl_agent/constants.py`, EXTENDED)

```python
SPEC_ROLES: dict[str, str] = { "Blood": "tank", "Vengeance": "tank", "Guardian": "tank",
  "Brewmaster": "tank", "Protection": "tank",
  "Restoration": "healer", "Preservation": "healer", "Mistweaver": "healer",
  "Holy": "healer", "Discipline": "healer", /* all remaining specs → "dps" */ }

def role_for_spec(spec: str | None) -> str | None:
    """Return 'tank'|'healer'|'dps' for a known spec; None when unknown/unset."""
```
- Keyed by the same PascalCase spec filter values as `CLASS_SPECS`. Spec names are role-unambiguous across classes (verified). Unknown/None → `None` (unset, not guessed).

## Acceptance mapping
- FR-001 durable per-tenant store (new tables survive restart); FR-003 players; FR-004 encounters; FR-005 injected via the single preamble across conversations; FR-006 tenant-scoped; FR-007 bounded; FR-008 best-effort; FR-009 fewer WCL calls on follow-ups; FR-010 server-side off the hub; FR-011 additive/empty-state unchanged.
