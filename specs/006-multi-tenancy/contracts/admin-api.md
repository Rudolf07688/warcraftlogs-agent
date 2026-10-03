# Contract: Admin API (`/api/admin/*`)

Every endpoint requires an authenticated session whose identity has `is_platform_admin = true`
(enforced server-side by the `require_platform_admin` dependency — **independent** of any UI hiding,
FR-022) **and** CSRF on unsafe methods. Non-admins receive `403` from all of these, even when called
directly. Views never expose password hashes, token hashes, or raw/hashed tokens (FR-024). The raw
invitation/reset **link** is returned **once**, only in the create/resend/trigger-reset responses,
for the founder to copy and share (research R9).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/admin/users` | paginated users: email, status, last-login, memberships |
| POST | `/api/admin/invitations` | create invitation → returns `invite_link` once |
| POST | `/api/admin/invitations/{id}/resend` | rotate token+expiry → returns fresh `invite_link` once |
| DELETE | `/api/admin/invitations/{id}` | revoke invitation (link stops working) |
| GET | `/api/admin/invitations` | list pending invitations: email, role, status, expiry (no token) |
| PATCH | `/api/admin/users/{id}` | disable/enable a user (not self) |
| POST | `/api/admin/users/{id}/reset` | trigger a reset → returns `reset_link` once |

> **Deferred in v1 (not built)**: `PUT`/`DELETE /api/admin/users/{id}/memberships/{tenant_id}`
> (add/change/remove membership). With one workspace per user there is nothing to manage, so building
> them now would be speculative (Simplicity-First). The `tenant_memberships` table and `MembershipIn`
> schema are retained, so these endpoints can be added later without rework when shared/multi-member
> workspaces are introduced.

### POST /api/admin/invitations
Req `{ "email", "role" }`. One transaction (guide §Admin creates invitation): normalize email;
create the `invited` user if none exists; `409 user_disabled` if the user exists and is disabled;
`409 membership_exists` if already an active member; revoke any prior open invitation for the email;
generate token (store digest only), 24h expiry; audit `invitation.created` (no raw token). `201`
returns `InvitationOut` **with** `invite_link` (built from canonical config URL, token in fragment).
In v1 the invited workspace is provisioned at acceptance, so an invite for a new person does not
pre-create a tenant.

### POST /api/admin/invitations/{id}/resend
Revokes the prior token, issues a new token + expiry, audits `invitation.resent`, returns a fresh
`invite_link` once. Prior link no longer works.

### DELETE /api/admin/invitations/{id}
Sets `revoked_at`, audits `invitation.revoked`, `204`.

### PATCH /api/admin/users/{id}
Req `{ "status": "active" | "disabled" }`. Disabling: set `users.status='disabled'` **and revoke all
that user's sessions** (takes effect on their next request/turn, FR-023); audit
`user.disabled`/`user.enabled`. The founder cannot disable their own last admin account (`409`).

### POST /api/admin/users/{id}/reset
Generates a single-use reset token (digest stored), audits `password_reset.requested`, returns
`{ "reset_link": "…#token=…" }` once for the founder to share. The admin cannot view/set the
password (FR-027).

### Pagination & shapes
`GET /api/admin/users?limit=&cursor=` → `{ "users":[AdminUserOut], "next_cursor": "…"|null }`.
`InvitationOut` = `{ id,email,role,status,expires_at, invite_link? }` (`invite_link` only on
create/resend). `AdminUserOut` = `{ id,email,status,last_login_at, memberships:[{tenant_id,name,role}] }`.
