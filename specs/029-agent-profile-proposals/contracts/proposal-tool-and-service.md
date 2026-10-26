# Contract: profile proposal tool, proposal service, shared profile service (sc-205)

Design: C5–C14, `#proposal-contract`, `#proposal-service-api`. Data shapes: `../data-model.md`.

## Agent tool: `backend/app/agent_tools/profile_tools.py` (new)

```python
async def propose_profile_changes(changes: list[ProfileChangeIn], tool_context: ToolContext) -> dict:
    """Propose adding, re-roling or removing the user's own characters and friends; nothing changes until the user approves.
    ...(argument rules: 1–30 items; update = raid role only; raid_role only when the user asked; played_role display only)
    """

PROFILE_TOOLS = ToolGroup(
    "Profile", (propose_profile_changes,),
    note="proposals only: nothing changes until the user approves the card",
)
```

- No tenant, user, conversation or id parameters (C7).
- Identity: `current_identity.get()`. It must be non-null and its `tenant_id` must equal
  `tool_context.user_id`, otherwise the tool fails closed and stores nothing.
  Conversation = `uuid.UUID(tool_context.session.id)`.
- Results (existing tool convention):
  - success: `{"status": "success", "proposal": ProfileProposalOut (JSON mode), "note": "Nothing has changed yet. The user approves or cancels on the card."}`
  - error: `{"status": "error", "error_message": …}` for no identity or a mismatch ("Profile
    changes are unavailable in this session."), 0 items, or more than 30 items ("Too many
    changes (N): at most 30 per proposal; ask the user to narrow it down.").
- Registration: `backend/app/agent_runner.py::_get_runner` →
  `build_agent(model, retry=policy, extra_groups=(PROFILE_TOOLS,))`.

## Proposal service: `backend/app/services/profile_proposals.py` (new)

Each function opens its own `tenant_scope(identity.tenant_id, user_id=identity.user_id)`
and scopes every query on tenant and user.

| Function | Returns | Errors |
|---|---|---|
| `create_proposal(identity, conversation_id, changes)` | `ProfileProposalOut` (pending) | `ValueError` for 0 or > `MAX_PROPOSAL_ITEMS` items (the tool turns it into its error) |
| `list_proposals(identity, conversation_id)` | `list[ProfileProposalOut]`, oldest first, status computed | none |
| `get_proposal(identity, proposal_id)` | `ProfileProposalOut`, status computed | `ProposalError("not_found")` |
| `execute_proposal(identity, proposal_id)` | `ProfileProposalOut` (applied, per-item results) | `not_found`, `proposal_expired` (status stored), `proposal_cancelled` |
| `cancel_proposal(identity, proposal_id)` | `ProfileProposalOut` (cancelled; or expired if past expiry; a second cancel is a no-op) | `not_found`, `proposal_applied` |

- `not_found` covers a missing id, another tenant's id and another user's id (no disclosure).
- Idempotency: an applied proposal comes back unchanged and nothing is written (C11).
- Execution: row lock → re-validate → one savepoint per item through `profile_service` →
  results → `applied` → one commit → guide tasks scheduled after the commit
  (research R6).
- 031 calls only these functions (and never touches `user_characters`). 029 adds no frames
  and no routes.

## Shared profile service: `backend/app/services/profile_service.py` (new, C8)

| Function | Does | Raises |
|---|---|---|
| `add_character(db, identity, body: CharacterIn, role) -> UserCharacter` | `repo.add_character`, flush, no commit | `CharacterConflict(code)`; an `IntegrityError` becomes `CharacterConflict("duplicate_character" \| "duplicate_friend")` |
| `set_raid_role(db, identity, char_id, raid_role, role) -> UserCharacter` | `repo.update_character_role`, no commit | `CharacterNotFound` |
| `remove_character(db, identity, char_id, role) -> None` | `repo.delete_character` | `CharacterNotFound` |

Guide tasks: callers call `schedule_character_guide` after their commit. The design's
`schedule_guides` wrapper is dropped. The existing REST tests patch
`backend.app.api.profile.schedule_character_guide`, so `_add` keeps that call, and AC 4 needs
those tests unchanged.

## REST (unchanged surface, `backend/app/api/profile.py`)

The six character routes keep their paths, bodies, status codes and details. Only the bodies
of `_add`/`_patch`/`_delete` change: they call the service, then map `CharacterConflict` → 409
`detail=code` and `CharacterNotFound` → 404 `not_found`. New detail: `friend_limit` (409) on
`POST /api/profile/friends` once 50 friends exist (D8).

## Validation codes

Exactly the design's `#validation-codes` table. Item `result.status`:
- `skipped`: `validation.ok` was false;
- `failed`: the item was valid when proposed but conflicts at execution (code = the
  re-validation code, or the `CharacterConflict` code from a race);
- `applied`: the item was applied (`character_id` = the new row for an add, or the row
  updated or removed).
