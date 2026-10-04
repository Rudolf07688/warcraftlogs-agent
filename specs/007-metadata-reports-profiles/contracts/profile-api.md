# Contract: Profile API — raid roles & multi-friend (US4)

Base: `/api/profile` (`backend/app/api/profile.py`). All routes require an authenticated session; mutations require CSRF (`require_csrf`) and are tenant-scoped. Only the **deltas** from today are specified.

## Schema changes (`backend/app/schemas.py`)

### `CharacterIn` (extended)
```jsonc
{
  "name": "string (1..100)",
  "server": "string (1..100)",
  "region": "string (1..8)",
  "raid_role": "tank | healer | dps | null"   // NEW, optional, default null (unset override)
}
```
- `raid_role` validated as `Literal["tank","healer","dps"] | None`. Any other value ⇒ `422` (character unchanged, FR-027).

### `CharacterOut` (extended)
```jsonc
{
  "id": "uuid",
  "role": "self | friend",            // unchanged (relationship)
  "name": "...", "server": "...", "region": "...",
  "class_name": "string | null",
  "active_spec": "string | null",
  "raid_role": "tank | healer | dps | null",      // NEW — the stored user override
  "effective_role": "tank | healer | dps | null", // NEW — raid_role or inferred-from-spec
  "guide_status": "none | pending | ready | failed",
  "guide_updated_at": "datetime | null"
}
```
- `effective_role` is computed: `raid_role or role_for_spec(active_spec)`. UI treats `effective_role != null && raid_role == null` as **inferred** (FR-029).

### `FriendPatchIn` (NEW)
```jsonc
{ "raid_role": "tank | healer | dps | null" }
```

## Endpoints

### `GET /api/profile` → `ProfileOut` *(unchanged shape, enriched characters)*
- Returns `self`, `friends[]`, `guild` with each character now carrying `raid_role` + `effective_role`.

### `PUT /api/profile/self` *(extended)*
- Body `CharacterIn` (now may include `raid_role`). Upserts the single self character in place and sets the override. Returns `CharacterOut`. Still schedules the guide task.

### `POST /api/profile/friends` *(extended)*
- Body `CharacterIn` (may include `raid_role`). `201` → `CharacterOut`.
- No cap (FR-022). Exact duplicate identity ⇒ `409 {"detail": "duplicate_friend"}` (unchanged); the **frontend** maps this to a friendly "already added" message (FR-023).

### `PATCH /api/profile/friends/{char_id}` *(NEW)* — FR-026/FR-028
- Body `FriendPatchIn`. Updates the friend's `raid_role` **in place** (no new row). `raid_role: null` clears the override (reverts to inferred).
- `200` → `CharacterOut`. Not found / not a friend of this tenant ⇒ `404 {"detail":"not_found"}`.
- Must `commit_and_rescope` after the write (tenant-scope discipline).

### `DELETE /api/profile/friends/{char_id}` *(unchanged)* → `204`
### `PUT /api/profile/guild` / `DELETE /api/profile/guild` *(unchanged)*

## Acceptance mapping
- FR-022 multi-friend: `POST /friends` repeated → all persist (no cap).
- FR-023 duplicate: `409 duplicate_friend` + friendly UI message.
- FR-024/FR-027 role attribute + validation: `raid_role` on `CharacterIn`, `Literal` enforced.
- FR-025 inference: `effective_role` falls back to `role_for_spec(active_spec)`.
- FR-026 override persists: `PATCH` sets override; survives reload and spec re-resolution.
- FR-028 in-place edit: `PATCH` updates the row; `PUT /self` upserts.
- FR-029 UI indicates set vs inferred: `raid_role` + `effective_role` both returned.
