# Research: Multiple Own Characters on the Profile

Spec: [spec.md](./spec.md). The Technical Context had no open unknowns. Each item below records one design decision made after reading the current code, with file references.

## R1 — Storage: reuse `user_characters`, no migration

**Decision**: Store own characters as `user_characters` rows with `role = "self"`. Allow several per tenant. Add no schema change and no migration.

**Rationale**: The unique constraint is `(tenant_id, name, server, region, role)` (`backend/app/db/models.py:451`). Only `repo.upsert_self` keeps "self" to one row; the database does not. Several `self` rows therefore already fit the schema. The existing single self row automatically becomes the first own character, which satisfies FR-006 with no backfill. The role value stays `"self"`, which keeps the meaning of the existing rows and the `ix_user_characters_tenant_role` index unchanged.

**Alternatives considered**:
- A new `role = "own"` value with a data migration. Rejected: it renames a value for no behavioural gain and adds migration risk.
- A separate table. Rejected under Principle III: same columns, same guide lifecycle.

## R2 — Duplicate and cross-role conflicts (FR-003, FR-004)

**Decision**: Before inserting any character, call a single repository helper, `find_character_identity(session, tenant_id, name, server, region)`. It returns the existing row for that identity in either role, compared case-insensitively, or `None`. The self and friend add paths both call it:
- Same role already exists: 409 with `duplicate_character`.
- Other role exists: 409 with `already_friend` (when adding an own character) or `already_own` (when adding a friend).

The database `IntegrityError` path stays in place as a backstop for same-role races.

**Rationale**: The DB constraint includes `role`, so it cannot express "one identity across both roles". Dropping `role` from the constraint would need a migration, and that migration would fail on any tenant that already has the same character saved as both self and friend. An application check is enough because one tenant edits its own profile, so concurrent races are not a realistic concern. Comparing case-insensitively matches how `_recent_block` already reconciles identities (`profile_context.py:74`).

**Alternatives considered**: Changing the constraint to `(tenant_id, lower(name), lower(server), lower(region))`. Rejected: it needs a migration and data cleanup that this feature doesn't need.

## R3 — Cap of 10 own characters (FR-001)

**Decision**: `MAX_OWN_CHARACTERS = 10` is defined once, in `backend/app/db/repository.py` next to the profile functions. The add path counts the existing `self` rows and rejects an 11th with 409 `character_limit`. The frontend reads the limit from the profile response field `own_limit` instead of hard-coding it a second time (Principle I).

**Rationale**: A single source of truth for the limit. It keeps the prompt bounded (R6).

## R4 — API shape: mirror the friends endpoints, share one implementation

**Decision**: Replace `PUT /api/profile/self` with three endpoints that match the friends endpoints:
- `POST /api/profile/self` adds an own character.
- `PATCH /api/profile/self/{id}` sets its raid role.
- `DELETE /api/profile/self/{id}` removes it.

The repository functions `add_friend`, `update_friend_role` and `delete_friend` are generalised into `add_character(role=…)`, `update_character_role(role=…)` and `delete_character(role=…)`. Both route groups call them. `upsert_self` and `get_self_character` are removed. `get_self_character` becomes `list_own_characters`, which returns rows ordered by `created_at`.

To change the identity of an own character, the user removes it and adds it again, the same way friends work today. The old "Edit identity" flow existed only because self was a single slot.

**Rationale**: Principle I, one code path per behaviour instead of a self copy and a friend copy. Impact analysis:
- `upsert_self`: LOW risk, one caller (`put_self`).
- `get_self_character`: **HIGH** risk, six upstream symbols across the profile API, `get_profile` and `ws._handle_turn`.

The HIGH rating comes from its reach through `get_profile` into the chat turn. Every one of those callers is rewritten in this feature (R5, R6), and each is covered by an existing test file: `test_profile.py`, `test_profile_context.py`, `test_tenant_isolation.py`, `test_roles.py`, `test_guide*.py`.

**Alternatives considered**:
- Keeping `PUT /self` for "the first character". Rejected: it would mean two ways to write an own character.
- A generic `/api/profile/characters?role=` endpoint. Rejected: it would also mean changing the friends API and its frontend client, which is more change than this feature needs.

## R5 — Profile response: `own` list replaces `self`

**Decision**: In `ProfileOut`, the field `self_character` (serialised as `"self"`) becomes `own: list[CharacterOut]`, plus `own_limit: int`. `repo.get_profile` returns `(own, friends, guild)`. The frontend `Profile` type changes from `self: Character | null` to `own: Character[]` and gains `own_limit: number`.

**Rationale**: The frontend is the only API client. A clean break is simpler than keeping a deprecated `self` field alive.

## R6 — Prompt injection (FR-007 to FR-011)

**Decision**: `build_preamble(own_characters: list[UserCharacter], friends, guild, …)`. The line it writes depends on how many own characters there are:
- **0**: no "You" line, the same as today.
- **1**: `- You (self): {ident}`, **byte-identical** to today (FR-011). The existing `test_profile_context` byte-identity tests keep passing.
- **2 or more**: `- You (self) — the user plays all of these characters; "I/me/my" can mean any of them: {ident}; {ident}; …`

Spec guides are grouped by `(class_name, active_spec)`, so two own characters with the same spec inject the guide once, under a heading that names both characters (for example `## Alpha, Beta — Frost`). The existing 1500-character per-guide and 4000-character total caps are unchanged. With one character per spec, the output is unchanged.

**Rationale**: The smallest change that tells the model every name to look for. Grouping the guides stops ten characters of the same spec from using up the guide budget.

## R7 — Agent instruction (FR-008 to FR-010)

**Decision**: Rewrite the KNOWN PLAYER CONTEXT bullet in `<CONTEXT_RESOLUTION>` (`wcl_agent/agent.py:180`) to say:
- The block may list several characters as the user's own, and "I/me/my/mine" refers to any of them.
- When examining a report, find which of them appear.
- If exactly one appears, answer about that character.
- If several appear, cover each by name or ask which one is meant, and never pick one silently.
- If none appear, say so instead of answering about another player.

The existing sentence about not narrowing population-level questions stays.

**Rationale**: The preamble supplies the data and the system instruction supplies the rule, the same split as today. Only one bullet changes.

## R8 — Frontend: one character list for own characters and friends

**Decision**: The "Your character" hero card becomes a "Your characters" card. It renders own characters with the same item-list markup the Friends card uses: avatar, name, guide badge, realm and spec, role select, remove button. That markup is extracted into one local `CharacterList` component in `CharactersTab.tsx`, used by both cards (Principle I). The `RoleToggle` hero control is removed, along with its now-unused imports. `DialogKind` changes from `"self"` to `"own"`, and the dialog is only used for adding. `ConfirmDialog` gains an "own" variant. When `own.length >= own_limit`, the Add button is disabled and its caption reads "Maximum of N characters".

**Principle VII check**: The UI needs no new registry component. `Card`, `Item`, `Empty`, `Dialog`, `NativeSelect` and `Button` are already in `frontend/src/components/ui/`. Nothing is hand-built. Run the shadcn audit checklist after the change.

## R9 — Error messages in the UI

**Decision**: Map 409 detail codes to friendly text in the existing `describeError` callback:
- `duplicate_character`: "X is already added."
- `already_friend`: "X is saved as a friend — remove it there first."
- `already_own`: "X is one of your characters."
- `character_limit`: "You can register up to N characters."
