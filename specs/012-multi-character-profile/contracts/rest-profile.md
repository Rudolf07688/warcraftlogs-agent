# Contract: Profile REST API (own characters)

Prefix `/api/profile`. Authentication is unchanged: a session is required, and mutations require CSRF. All rows are tenant-scoped.

## GET `/api/profile` → `ProfileOut` (changed)

```json
{
  "own": [CharacterOut, ...],
  "own_limit": 10,
  "friends": [CharacterOut, ...],
  "guild": GuildOut | null
}
```

- `own` replaces `self`. It is ordered by creation time and holds 0–10 entries.
- `CharacterOut` is unchanged. Its `role` is `"self"` for own characters.

## POST `/api/profile/self` → 201 `CharacterOut` (new; replaces `PUT /self`)

Body: `CharacterIn` (`name`, `server`, `region`, `raid_role?`).

Schedules `schedule_character_guide` exactly as before.

| Status | `detail` | When |
|---|---|---|
| 409 | `duplicate_character` | The same identity (case-insensitive) is already an own character |
| 409 | `already_friend` | The identity is saved as a friend |
| 409 | `character_limit` | The tenant already has `own_limit` own characters |
| 422 | (validation) | The body is invalid |

## PATCH `/api/profile/self/{id}` → `CharacterOut` (new)

Body: `{ "raid_role": "tank" | "healer" | "dps" | null }` (`CharacterPatchIn`, renamed from `FriendPatchIn`). `null` reverts to the inferred role. Returns 404 `not_found` when `id` is not an own character of this tenant.

## DELETE `/api/profile/self/{id}` → 204 (new)

Returns 404 `not_found` when `id` is not an own character of this tenant. Removing the last own character is allowed.

## PUT `/api/profile/self` (removed)

## POST `/api/profile/friends` (changed errors only)

| Status | `detail` | When |
|---|---|---|
| 409 | `duplicate_friend` | Unchanged |
| 409 | `already_own` | New: the identity is one of the user's own characters |

PATCH and DELETE on `/friends/{id}`, and the `/guild` endpoints, are unchanged.
