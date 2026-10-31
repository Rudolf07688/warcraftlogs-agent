# Contract changes (internal)

## services/profile_proposals.py
- `get_proposal(identity, proposal_id, *, db: AsyncSession | None = None)`
- `list_proposals(identity, conversation_id, *, db: AsyncSession | None = None)`

With `db`, the read runs in the caller's transaction (already scoped to the identity's tenant
and user); without it, in its own `tenant_scope` as before.

## services/guide.py
- `schedule_character_guides(char_ids, tenant_id)`: one background task; at most 3 character
  guide jobs run at a time.

## services/background.py
- `spawn(coro, key)`: the task runs in a fresh, empty `contextvars.Context`.

## db/repository.py
- `lock_profile(session, tenant_id)`: per-tenant transaction advisory lock (Postgres only).
- `add_characters`, `set_raid_roles`, `delete_characters`: bulk writes for an approval.

No HTTP, WebSocket or frame shapes change.
