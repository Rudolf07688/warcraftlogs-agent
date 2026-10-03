# Contract: Tenant Scoping, Existing Endpoints & Status Matrix

How isolation is enforced uniformly, and how every pre-existing endpoint changes. This is the
binding checklist for US3 (FR-017–FR-020) and the gating cross-tenant test matrix.

## Repository contract

Every tenant-owned function in `db/repository.py` takes a **keyword-only `tenant_id: UUID`** and
includes it in the SQL predicate / insert. No function fetches a tenant-owned row by id alone.

```python
async def get_conversation(session, conv_id, *, tenant_id):
    # WHERE id = :conv_id AND tenant_id = :tenant_id → None if not in tenant → 404
```

Affected functions (non-exhaustive, all must be updated): `create_conversation`, `get_conversation`,
`list_conversations`, `delete_conversation`, `add_message`, `list_messages`, `_next_seq`,
`upsert_tracked_raid`, `list_tracked_raids`, `get_tracked_raid`, `add_captured_graph`,
`list_captured_graphs`, `add_artifact`, `list_artifacts`, `assign_message_seq_to_turn_captures`,
`get_self_character`, `list_friend_characters`, `get_guild_profile`, `get_profile`, `upsert_self`,
`add_friend`, `delete_friend`, `set_guild`, `delete_guild`, `get_character`, `set_character_guide`,
`set_guild_summary`. Child-row writes set `tenant_id` from the parent at insert time.

## Transaction context

A `tenant_session(identity)` helper (wrapping `SessionLocal`) opens the transaction and runs
`SELECT set_config('app.tenant_id', :tid, true); SELECT set_config('app.user_id', :uid, true);`
before any work, so application scope and RLS agree. Never session-level `SET` on a pooled
connection. Background tasks (spec-guide, guild summary) run inside their own tenant-scoped
transaction.

## Derived/cached scope
- **WCL cache** (feature 005): key = `tenant_id | tool_name | args` (FR-019).
- **ADK sessions**: `user_id = str(tenant_id)` isolates `DatabaseSessionService` state.
- **Scratch files**: already per-conversation; conversation is tenant-owned (ownership checked first).
- **Spec guides / guild summaries / graphs / artifacts / reports**: all scoped via their tenant-owned
  rows; PDFs read only the caller-tenant's captures.

## Existing endpoints — required changes

| Endpoint | Change |
|---|---|
| `GET/POST/GET{id}/DELETE{id} /api/conversations` | require session; scope all repo calls by `tenant_id`; `{id}` not in tenant → `404` |
| `GET /api/conversations/{id}/report.pdf` and `…/messages/{mid}/report.pdf` | require session; conversation + captures scoped by tenant; foreign → `404` |
| `GET /api/raids`, `POST /api/raids/{code}/investigate` | require session; raids scoped by tenant; investigate creates a tenant-owned conversation |
| `GET/PUT/POST/DELETE /api/profile*` | require session; all profile rows scoped by tenant |
| `GET /api/models`, `GET /api/greeting` | require session (no tenant data, but no anonymous access) |
| `WS /ws/chat` | authenticated handshake + per-turn scoping (see websocket.md) |

## HTTP status matrix (guide §Error and status behavior)

| Situation | Status |
|---|---|
| Missing/invalid session | `401` |
| Authenticated but not platform admin (admin API) | `403` |
| Tenant resource absent or in another tenant | `404` |
| Login failure (any cause) | generic `401 invalid_credentials` |
| Invalid/expired/used public token | generic `400 invalid_or_expired_token` |
| Duplicate active membership (admin) | `409 membership_exists` |
| CSRF failure / bad origin | `403 csrf_failed` |
| Rate limited | `429` |
| Validation failure | `422` (never echo password/token) |

## Cross-tenant test matrix (gates US3)

Create tenants A and B with look-alike data, then assert:
1. A cannot read/list/count/search/export/update/delete B's conversations, messages, raids, graphs,
   artifacts, profile, or reports.
2. Guessing B's resource UUIDs returns `404`.
3. Supplying B's tenant/resource id in body/query/header does not change A's scope.
4. Disabling a user / revoking a session stops their in-flight socket on the next turn.
5. The WCL cache and ADK session state never serve B's data to A.
6. **Postgres RLS**: with the app predicate deliberately omitted in a test, RLS still blocks
   cross-tenant read/write; missing `app.tenant_id` returns no rows and rejects writes; the runtime
   role cannot bypass RLS; a pooled connection does not retain a prior transaction's tenant context.
