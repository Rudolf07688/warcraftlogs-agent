# Contract: Authenticated Chat WebSocket (`/ws/chat`)

Extends the feature-005 WS contract with authentication and tenant scoping. All existing frames
(`meta`, `token`, `tool_start`, `tool_end`, `tool_progress`, `grounding`, `raid_tracked`,
`encounters`, `artifact`, `suggestions`, `done`, `error`) are unchanged — they are now implicitly
scoped to the connection's tenant.

## Handshake authentication (new)

Before `ws.accept()`:
1. Read `__Host-session` from the handshake `Cookie` header.
2. Validate exactly as the HTTP `require_session` dependency: sha256 → load unrevoked/unexpired
   session joined to active user + active tenant + active membership → build `RequestIdentity`.
3. Validate the `Origin` header against the configured canonical origin (the WS analogue of CSRF;
   `SameSite=Lax` is defense in depth).
4. On failure (missing/invalid session, or bad origin): close with a policy-violation code
   **without** accepting; emit no data. On success: accept and bind `RequestIdentity` to the socket.

No session token or tenant id is ever accepted from the query string, a frame body, or a custom
header (FR-006; secret-handling rules forbid tokens in URLs).

## Per-turn scoping (changes to `_handle_turn` / `_handle_tool_end`)

- The conversation referenced by `ChatTurn.conversation_id` must belong to the socket's `tenant_id`;
  otherwise emit `error{code:"not_found"}` (never reveal cross-tenant existence, FR-018).
- New conversations are created with the socket's `tenant_id`.
- Every `repo.*` call made during the turn passes the socket's `tenant_id`; the transaction sets
  `app.tenant_id` so RLS agrees (research R4/R5).
- `stream_response` runs with ADK `user_id = str(tenant_id)` so `DatabaseSessionService` state is
  isolated per tenant.
- The WCL result cache key is prefixed with `tenant_id` (FR-019) — cached lookups never cross tenants.
- Re-validation is cheap per turn: a revoked/expired session or a disabled user/tenant causes the
  next turn to fail with `error{code:"unauthorized"}` and the socket to close, so account disabling
  takes effect mid-session (FR-023).

## New error codes
`unauthorized` (session invalid/expired mid-connection) · `not_found` (conversation not in tenant).
Existing codes (`empty_message`, `invalid_model`, `agent_error`) unchanged.
