# Implementation Plan: Multiple Own Characters on the Profile

**Branch**: `012-multi-character-profile` | **Date**: 2026-10-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/012-multi-character-profile/spec.md`

## Summary

A user can register up to 10 characters as their own instead of one. All of them are sent to the assistant in the per-turn KNOWN PLAYER CONTEXT, and the agent instruction says "I/me/my" can mean any of them.

There is no schema change. The `user_characters` table already allows several `role = "self"` rows; only `upsert_self` limited it to one. The work has four parts:

- Replace the single-self repository and API paths with list paths that share one implementation with friends.
- Turn `ProfileOut.self` into an `own` list.
- Teach `build_preamble` and the agent instruction to handle several own characters. With one character, the output stays byte-identical to today.
- Render own characters on the profile page with the same list component as friends.

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript + React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy async, Pydantic v2, Google ADK (agent), Tailwind v4 + shadcn/ui

**Storage**: PostgreSQL, existing `user_characters` table with RLS. No migration.

**Testing**: pytest (`backend/tests/`), `tsc -b && vite build` for the frontend

**Target Platform**: Linux server (docker compose) and a modern browser

**Project Type**: Web application (FastAPI backend, React frontend, ADK agent package `wcl_agent/`)

**Performance Goals**: The preamble stays within its existing caps: 1500 characters per guide and 4000 for all guides. Ten own characters add about 10 identity lines, roughly 1 KB.

**Constraints**: With 0 or 1 own character, the preamble must be byte-identical to today (FR-011). No new dependencies.

**Scale/Scope**: At most 10 own characters per tenant. 1 table (unchanged), 4 backend modules, 1 agent instruction bullet, 3 frontend files.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. DRY & reuse-first | ✅ | Own characters and friends share `add_character`, `update_character_role` and `delete_character`, plus one conflict helper. The frontend shares one `CharacterList`. The limit is defined once, in the backend, and exposed as `own_limit`. Removes `upsert_self` and `get_self_character` rather than adding parallel paths. |
| II. Step-wise delivery | ✅ | Increments: (1) repository and API with tests, (2) preamble and instruction with tests, (3) frontend. Each is verifiable on its own. |
| III. Simplicity / YAGNI | ✅ | No migration, no new table, no "main" flag, no new tools. To change an own character's identity, the user removes and re-adds it, as with friends. |
| IV. Typed contracts | ✅ | `ProfileOut.own: list[CharacterOut]`, `own_limit: int`. `FriendPatchIn` is renamed to `CharacterPatchIn`. `CharacterConflict` carries a typed code. |
| V. Async FastAPI | ✅ | New endpoints follow the existing async handler pattern in `api/profile.py`. |
| VI. GitNexus awareness | ✅ ⚠ | Impact analysis was run. `build_preamble` LOW (`ws._handle_turn`). `upsert_self` LOW (`put_self`). `get_self_character` **HIGH**: 6 upstream symbols via `get_profile` → profile API and `ws._handle_turn`. Every caller is rewritten here and covered by existing tests (see research R4). `get_profile` was ambiguous by name; it resolves to `repository.get_profile` (LOW). Re-run `impact` per symbol before editing. |
| VII. shadcn/ui via MCP | ✅ | No new UI primitives are needed. Card, Item, Empty, Dialog, NativeSelect and Button already exist in `components/ui/`. Nothing is hand-built. Run the MCP audit checklist after the frontend change. |

No violations, so Complexity Tracking is empty.

**Post-design re-check**: still passes. The design adds no layers. The only new symbols are `list_own_characters`, `find_character_identity`, `CharacterConflict`, the three generalised repository functions, three endpoints and `CharacterList`. Each replaces or merges an existing path.

## Project Structure

### Documentation (this feature)

```text
specs/012-multi-character-profile/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── rest-profile.md
│   └── prompt-context.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (files touched)

```text
backend/app/
├── db/repository.py            # list_own_characters, find_character_identity, CharacterConflict,
│                               #   add/update/delete_character(role=…), MAX_OWN_CHARACTERS,
│                               #   get_profile → (own, friends, guild); drop upsert_self/get_self_character
├── schemas.py                  # ProfileOut.own + own_limit; FriendPatchIn → CharacterPatchIn
├── api/profile.py              # POST/PATCH/DELETE /self[/{id}]; friends use shared repo fns; 409 codes
├── api/ws.py                   # get_profile → own list into build_preamble
└── services/profile_context.py # build_preamble(own_characters: list, …); grouped spec guides

wcl_agent/agent.py              # <CONTEXT_RESOLUTION> KNOWN PLAYER CONTEXT bullet

frontend/src/
├── types.ts                    # Profile.own: Character[], own_limit
├── api/restClient.ts           # addOwnCharacter, updateOwnCharacter, deleteOwnCharacter (drop putSelf)
└── components/profile/CharactersTab.tsx  # "Your characters" list via shared CharacterList

backend/tests/
├── test_profile.py             # own add/patch/delete, limit, duplicate, cross-role, upgrade row
├── test_profile_context.py     # 0/1 byte-identical, ≥2 line, grouped guides
├── test_roles.py, test_guide*.py, test_tenant_isolation.py  # adapt upsert_self/put_self usages
```

**Structure Decision**: Use the existing web-app layout (`backend/`, `frontend/`, `wcl_agent/`). No new modules.

## Complexity Tracking

No violations.
