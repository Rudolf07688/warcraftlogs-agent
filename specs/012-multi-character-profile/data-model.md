# Data Model: Multiple Own Characters on the Profile

No schema change. No migration (research R1).

## UserCharacter (`user_characters`, existing)

| Field | Type | Notes |
|---|---|---|
| id | uuid | PK |
| tenant_id | uuid | FK `tenants.id`, CASCADE, RLS-scoped |
| role | `"self"` \| `"friend"` | `"self"` now means **one of the user's own characters**. There can be 0–10 per tenant. |
| name, server, region | str | Identity |
| class_name, active_spec | str \| null | Resolved in the background by `run_character_guide` (unchanged) |
| raid_role | `tank` \| `healer` \| `dps` \| null | User override. Effective role is `raid_role or role_for_spec(active_spec)` |
| created_at, updated_at | timestamptz | `created_at` orders the own list |

**Constraints**

- DB, unchanged: unique `(tenant_id, name, server, region, role)`.
- App, new: one identity (case-insensitive `name/server/region`) exists in at most one role per tenant (FR-004, R2).
- App, new: count of `role = "self"` rows per tenant ≤ `MAX_OWN_CHARACTERS` (10) (FR-001, R3).

**Lifecycle of an own character**

```text
add (POST /self) ──► class/spec unresolved, guide "none"/"pending"
                     │ background run_character_guide (unchanged)
                     ▼
                     class/spec resolved, guide from shared spec_guides
role change (PATCH /self/{id}) ──► raid_role updated in place
remove (DELETE /self/{id})     ──► row deleted
```

Removing the last own character is valid. The profile then has `own = []`.

## Repository functions (internal, `backend/app/db/repository.py`)

| Before | After |
|---|---|
| `get_self_character(...) -> UserCharacter \| None` | `list_own_characters(...) -> list[UserCharacter]` (ordered by `created_at`) |
| `upsert_self(...)` | removed |
| `add_friend(...)` | `add_character(..., role)`, which raises `CharacterConflict(code)` on a duplicate, cross-role identity or the limit |
| `update_friend_role(...)` | `update_character_role(char_id, ..., role, raid_role)` |
| `delete_friend(...)` | `delete_character(char_id, ..., role)` |
| — | `find_character_identity(...) -> UserCharacter \| None` (case-insensitive, any role) |
| `get_profile -> (self \| None, friends, guild)` | `get_profile -> (own: list, friends, guild)` |

`CharacterConflict` is a small exception carrying the code: `duplicate_character`, `already_friend`, `already_own` or `character_limit`. The API maps it to a 409.

## Prompt context (in-process, not persisted)

`build_preamble(own_characters: list[UserCharacter], friends, guild, *, …)`. Output rules are in [contracts/prompt-context.md](./contracts/prompt-context.md).
