# Tasks: Multiple Own Characters on the Profile

**Input**: Design documents from `specs/012-multi-character-profile/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/rest-profile.md, contracts/prompt-context.md, quickstart.md

**Tests**: Included. The plan lists the test files to update, and the existing suites call the single-self paths that are being removed, so they must change alongside the code.

**Organization**: Grouped by user story. US1 is registering several own characters (repository, API, UI). US2 is the assistant treating all of them as "me" (preamble and instruction). Both are P1. US2 depends on the Foundational phase only, not on the US1 UI.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: The user story the task belongs to (US1, US2)

---

## Phase 1: Setup

- [X] T001 Refresh the GitNexus index with `node .gitnexus/run.cjs analyze --index-only` from the repo root, then confirm `node .gitnexus/run.cjs impact "get_self_character" --direction upstream --repo .` reports no `staleness: behind`. Record the HIGH risk and its 6 upstream symbols in the commit body later (constitution VI).

---

## Phase 2: Foundational (blocks both stories)

**Purpose**: Replace the single-self repository and schema with the list shape. After this phase the backend compiles against `own: list`, and both stories build on it.

- [X] T002 Run `impact` (upstream) on `upsert_self`, `get_self_character`, `add_friend`, `update_friend_role`, `delete_friend` and `backend/app/db/repository.py:get_profile` (pass `--file backend/app/db/repository.py` to disambiguate). Then edit `backend/app/db/repository.py` in the profile section:
  - Add `MAX_OWN_CHARACTERS = 10` and `class CharacterConflict(Exception)` with a `code: str` attribute. Its codes are `duplicate_character`, `duplicate_friend`, `already_friend`, `already_own` and `character_limit`.
  - Add `find_character_identity(session, *, tenant_id, name, server, region) -> UserCharacter | None`, which matches `func.lower()` on name, server and region across both roles.
  - Replace `get_self_character` with `list_own_characters(session, *, tenant_id) -> list[UserCharacter]`: `role == "self"`, ordered by `created_at`.
  - Replace `add_friend` with `add_character(session, *, tenant_id, role, name, server, region, raid_role=None)`. Its conflict checks:
    - Existing identity in the same role: `duplicate_character` for self, `duplicate_friend` for friend.
    - Existing identity in the other role: `already_friend` when adding self, `already_own` when adding a friend.
    - When `role == "self"` and the count of own characters is already `>= MAX_OWN_CHARACTERS`: `character_limit`.
    - Otherwise insert and flush.
  - Rename `update_friend_role` to `update_character_role(session, char_id, *, tenant_id, role, raid_role)` and `delete_friend` to `delete_character(session, char_id, *, tenant_id, role)`. Both filter on the given `role` instead of the hard-coded `"friend"`.
  - Delete `upsert_self`.
  - Change `get_profile` to return `(own: list[UserCharacter], friends, guild)` and update its docstring.

  This follows research R1–R4 and data-model.md.
- [X] T003 [P] In `backend/app/schemas.py`:
  - Rename `FriendPatchIn` to `CharacterPatchIn` and update its docstring to cover own characters and friends.
  - Change `ProfileOut`: remove `self_character` and its `"self"` serialization alias. Add `own: list[CharacterOut] = []` and `own_limit: int`. Keep `friends` and `guild`.

  This follows contracts/rest-profile.md.
- [X] T004 Update every caller of the removed names so the backend imports cleanly:
  - `backend/app/api/profile.py`: imports, `get_profile` builds `own=[out(c) for c in own]` and `own_limit=repo.MAX_OWN_CHARACTERS`, and the friends routes call `add_character(role="friend")`, `update_character_role(role="friend")` and `delete_character(role="friend")`.
  - `backend/app/api/ws.py:214`: unpack `own, friends, guild`, use `profile_chars = list(own) + list(friends)`, and pass `own` as the first argument to `build_preamble`.

  If T013 is not done yet, change only `build_preamble`'s first parameter to `own_characters: list` and render `own_characters[0]` as today. T013 does the full change. Preferably do T013 in the same sitting. Then run `uv run python -c "import backend.app.main"` to confirm imports.

**Checkpoint**: The backend imports. `repo.get_profile` returns a list of own characters.

---

## Phase 3: User Story 1 — Register several characters as my own (P1) 🎯 MVP

**Goal**: The user can add up to 10 own characters, change the role of each, remove any of them, and see them all on the profile page. Duplicate and cross-role additions are rejected with clear messages, and a pre-existing self character shows up as the first own character.

**Independent Test**: quickstart.md "Verify US1" steps 1–7.

### Tests for US1

- [X] T005 [P] [US1] Rewrite the repository-level tests in `backend/tests/test_profile.py`:
  - Replace `test_upsert_self_keeps_single_row` with tests for:
    - (a) `add_character(role="self")` twice with different identities gives `list_own_characters` 2 rows in creation order.
    - (b) Adding the same identity again with different case raises `CharacterConflict("duplicate_character")`.
    - (c) A self identity that already exists as a friend raises `already_friend`, and the reverse raises `already_own`.
    - (d) An 11th own character raises `character_limit`.
    - (e) A pre-existing `UserCharacter(role="self")` row inserted directly, as an upgrade would leave it, is returned by `list_own_characters` (FR-006).
- [X] T006 [P] [US1] Rewrite the API-level tests in `backend/tests/test_profile.py`, around lines 78–103:
  - An empty profile returns `own == []` and `own_limit == 10`.
  - `POST /api/profile/self` returns 201, and a second POST with a different identity gives `own` length 2.
  - `PATCH /api/profile/self/{id}` changes only that character's `raid_role`.
  - `DELETE /api/profile/self/{id}` returns 204 and the character is gone.
  - PATCH and DELETE with a friend's id return 404.
  - A duplicate returns 409 `duplicate_character`. An identity that exists as a friend returns 409 `already_friend`. Adding as a friend an identity that is one of the user's own returns 409 `already_own`. An 11th character returns 409 `character_limit`.
  - The old `PUT /api/profile/self` returns 405.
- [X] T007 [P] [US1] Adapt the other test files that used the single-self paths:
  - `backend/tests/test_roles.py:157`: `PUT /api/profile/self` becomes `POST`, then `PATCH /api/profile/self/{id}` for role changes.
  - `backend/tests/test_guide.py:54,117`: `repo.upsert_self(...)` becomes `repo.add_character(..., role="self")`.
  - `backend/tests/test_tenant_isolation.py:91-97`: use `add_character(role="self")` and assert `a_prof["own"][0]["name"] == "ASelf"` and `b_prof["own"] == []`.

### Implementation for US1

- [X] T008 [US1] Edit `backend/app/api/profile.py`:
  - Delete `put_self`.
  - Add `POST /self`, returning 201 `CharacterOut`. It calls `repo.add_character(role="self")`, then `commit_and_rescope`, then `schedule_character_guide`.
  - Add `PATCH /self/{char_id}` with a `CharacterPatchIn` body. It calls `update_character_role(role="self")` and returns 404 `not_found` when the id is not found.
  - Add `DELETE /self/{char_id}`, returning 204. It calls `delete_character(role="self")` and returns 404 when the id is not found.
  - Map `CharacterConflict` to `HTTPException(409, detail=exc.code)` with one small helper used by both POST routes. On `IntegrityError`, roll back and keep the 409 backstop (`duplicate_character` / `duplicate_friend`).
  - Update the module docstring.
  - Run `uv run pytest backend/tests/test_profile.py backend/tests/test_roles.py backend/tests/test_guide.py backend/tests/test_tenant_isolation.py -q` until it is green.
- [X] T009 [P] [US1] In `frontend/src/types.ts`, change `Profile` to `{ own: Character[]; own_limit: number; friends: Character[]; guild: Guild | null }`. In `frontend/src/api/restClient.ts`, replace `putSelf` with:
  - `addOwnCharacter(body: CharacterInput)` → `POST /api/profile/self`
  - `updateOwnCharacter(id, raidRole)` → `PATCH /api/profile/self/${id}`
  - `deleteOwnCharacter(id)` → `DELETE /api/profile/self/${id}`

  Match the style of the friend functions, which are directly below.
- [X] T010 [US1] Rework `frontend/src/components/profile/CharactersTab.tsx` (research R8–R9):
  - Extract the friends item-list markup (the `ItemGroup` and `Item` with `ClassAvatar`, `GuideBadge`, realm and spec, `RoleSelect`, and the remove button) into a local `CharacterList({ chars, busy, onRoleChange, onRemove, removeLabel })`.
  - Use `CharacterList` in the Friends card.
  - Turn the "Your character" hero card into a "Your characters" card (`lg:col-span-2`) that renders `profile.own` with `CharacterList`. It has an "Add character" `CardAction` button and an `Empty` state when the list is empty.
  - Disable the Add button when `own.length >= own_limit`, with the description "Maximum of {own_limit} characters".
  - Change `DialogKind` `"self"` to `"own"` and change the dialog copy to "Add your character" / "A character you play, as it appears on Warcraft Logs. The agent treats all your characters as you." Submitting calls `addOwnCharacter`.
  - Extend `pendingRemove` and `ConfirmDialog` with an `{ kind: "own"; char }` variant that calls `deleteOwnCharacter`.
  - In the pending-guide poll, use `profile.own.some(c => c.guide_status === "pending")`.
  - Write one `describeError` for both add flows that maps `duplicate_character` / `duplicate_friend` to "X is already added.", `already_friend` to "X is saved as a friend — remove it there first.", `already_own` to "X is one of your characters." and `character_limit` to "You can register up to N characters."
  - Remove `RoleToggle` and any imports that become unused, such as `ToggleGroup` and `Separator` if they are no longer referenced.
  - Run `cd frontend && npm run build` until it is green.
- [X] T011 [US1] Run the shadcn MCP audit checklist (`get_audit_checklist`) against the changed `CharactersTab.tsx` and fix anything it flags (constitution VII). No new registry items are expected.

**Checkpoint**: US1 is complete. Several own characters can be managed end to end and the backend tests are green.

---

## Phase 4: User Story 2 — The assistant treats all my characters as "me" (P1)

**Goal**: The per-turn KNOWN PLAYER CONTEXT lists every own character, and the agent instruction resolves "I/me/my" across them. With 0 or 1 own character, the output is byte-identical to today.

**Independent Test**: The preamble unit tests (T012) and quickstart.md "Verify US2" steps 1–5.

### Tests for US2

- [X] T012 [P] [US2] Update `backend/tests/test_profile_context.py` and `backend/tests/test_guide_meta.py:168-175`:
  - Change every `build_preamble(self_char, …)` call to `build_preamble([self_char], …)` and every `build_preamble(None, …)` call to `build_preamble([], …)`. The existing byte-identity assertions must still pass unchanged (FR-011).
  - Add tests for:
    - (a) Two own characters produce exactly the ≥2 "You" line from contracts/prompt-context.md, listing both identities in order.
    - (b) Two own characters with the same `(class, spec)` and a guide inject that guide once, under the heading `## Alpha, Beta — Frost`.
    - (c) An own character and a friend with different specs each get their own guide heading, unchanged from today.
    - (d) Every own character is excluded from the RECENTLY SEEN `- Players:` line.

### Implementation for US2

- [X] T013 [US2] Run `impact` on `build_preamble`, then edit `backend/app/services/profile_context.py`:
  - Change the signature to `build_preamble(own_characters: list[UserCharacter], friends, guild, *, …)`.
  - `profile_chars = list(own_characters) + list(friends)`.
  - The header condition becomes `own_characters or friends or guild is not None`.
  - The "You" line: none for 0 characters, `f"- You (self): {_ident(c)}"` for exactly 1, and for 2 or more, `'- You (self) — the user plays all of these characters; "I/me/my" can mean any of them: ' + "; ".join(_ident(c) for c in own_characters)`.
  - Group the `guided` list by `(class_name, active_spec)` in first-seen order, with the heading `f"  ## {', '.join(names)} — {spec}"` plus the existing label. A pair with a single character must render exactly as today.
  - Update the module docstring and the function docstring.
  - Run `uv run pytest backend/tests/test_profile_context.py backend/tests/test_guide_meta.py -q` until it is green.
- [X] T014 [P] [US2] In `wcl_agent/agent.py`, replace the first `<CONTEXT_RESOLUTION>` bullet (around lines 180–184) with the exact text in contracts/prompt-context.md under "Agent instruction". Keep the indentation and line width of the neighbouring bullets. Run `uv run pytest -q -k "agent or instruction or prompt"` to catch any prompt snapshot tests.
- [X] T015 [US2] Confirm `backend/app/api/ws.py`, which was adapted in T004, passes the full `own` list and that `test_grounding.py` and the WebSocket tests still pass: `uv run pytest backend/tests -q`.

**Checkpoint**: Both stories are complete.

---

## Phase 5: Polish & Cross-Cutting

- [X] T016 Search the repo for leftovers: `rg -n "upsert_self|get_self_character|putSelf|self_character|FriendPatchIn|profile\.self|\"self\"\]" backend frontend/src wcl_agent`. Only the `role = "self"` literals in the repository and model should remain. Update comments in `backend/app/db/models.py:461` (`"self"` now means "one of the user's own characters") and the profile docstrings in `backend/app/api/profile.py`.
- [ ] T017 Run the full verification: `uv run pytest -q` and `cd frontend && npm run build`. Then follow quickstart.md "Verify US1" and "Verify US2" against `docker compose up --build`, and note the outcome of each step in the commit or PR description.
- [X] T018 Run `node .gitnexus/run.cjs detect-changes --scope all --repo .` and confirm the result is not `partial` or `truncated`. The changed symbols should match the plan's file list, with no unexpected flows. Then mark the tasks done in this file.

---

## Dependencies & Execution Order

- **Setup (T001)** must come first.
- **Foundational (T002 → T004, with T003 in parallel with T002)** blocks both stories. T004 needs T002 and T003, and it touches `build_preamble`'s first argument, so do it together with T013 if possible.
- **US1 (T005–T011)** needs Phase 2.
  - Tests T005, T006 and T007 can run in parallel; T005 and T006 share a file, so either write them together or run them one after the other.
  - T008 needs T002 and T003.
  - T009 can run in parallel with the backend work.
  - T010 needs T009. T011 needs T010.
- **US2 (T012–T015)** needs Phase 2 only. It can run alongside US1. T012 and T014 are [P]. T013 needs T012's expectations. T015 comes last.
- **Polish (T016–T018)** comes after both stories.

### Parallel examples

```text
# After Phase 2:
T005/T006 (backend/tests/test_profile.py)  ‖  T009 (frontend types + client)  ‖  T012 (test_profile_context.py)  ‖  T014 (wcl_agent/agent.py)
```

## Implementation Strategy

1. **MVP = Phase 1, Phase 2 and US1.** Characters are stored and managed correctly. The preamble still works because T004 passes the list. Until T013 lands, with 2 or more characters the "You" line would reflect only the shape T004 left. Do T013 before shipping.
2. **Then US2.** Add the preamble wording and the agent instruction. This is where the value appears in the answers.
3. **Commit in increments.** Commit after Phase 2 with US1 together (backend and frontend green), then after US2. Run `detect-changes` before each commit.
