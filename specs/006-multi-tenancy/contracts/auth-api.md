# Contract: Authentication API (`/api/auth/*`)

All JSON. Cookies: `__Host-session` (`Secure; HttpOnly; SameSite=Lax; Path=/`, no `Domain`). The raw
CSRF token is returned in response bodies (never a cookie) and sent back by the client in
`X-CSRF-Token` on unsafe requests. Public auth errors are **generic** (no account enumeration). Error
envelope: `{ "error": { "code", "message", "request_id" } }`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/auth/login` | public, rate limited | authenticate, start session |
| POST | `/api/auth/logout` | session + CSRF | revoke current session (idempotent) |
| GET | `/api/auth/me` | session | identity, active tenant, memberships, CSRF token |
| POST | `/api/auth/accept-invitation` | public, token, rate limited | set first password, activate, sign in |
| POST | `/api/auth/forgot-password` | public, rate limited | **deferred in v1** (returns neutral 202; no email) |
| POST | `/api/auth/reset-password` | public, token, rate limited | set new password via founder-shared link, revoke sessions |

> Tenant switching (`/api/auth/switch-tenant`) is **not implemented in v1** (one workspace per user).
> The session model already carries `active_tenant_id` so it can be added later without rework.

### POST /api/auth/login
Req `{ "email", "password" }`. Success `200`: sets `__Host-session`, returns `MeOut` (incl.
`csrf_token`). Failure `401 invalid_credentials` — identical for unknown email / wrong password /
disabled user / no active membership (verify against a dummy hash for unknown email). On success:
reset failure counters, set `active_tenant_id` to the user's single tenant, rotate session + CSRF,
record `last_login_at` + `login` audit. `429` when throttled (no known/unknown distinction).

### POST /api/auth/logout
Requires valid session + `X-CSRF-Token`. Sets `revoked_at`, clears cookie with matching attrs,
`204`. Idempotent (already-invalid session still `204`).

### GET /api/auth/me
Requires session. `200 MeOut`. The frontend calls this on bootstrap and after login/accept/reset.
`401` clears client auth state.

### POST /api/auth/accept-invitation
Req `{ "token", "password", "password_confirmation" }`. Runs the data-model acceptance transaction
(auto-provisions the workspace, activates, signs in). Success `200`: sets session cookie, returns
`MeOut`. Any missing/expired/revoked/used token or policy failure → generic
`400 invalid_or_expired_invitation` (policy violations may return `422` **without echoing** the
password/token). Concurrent acceptance → exactly one `200`, others generic `400`.

### POST /api/auth/reset-password
Req `{ "token", "password", "password_confirmation" }`. Validates+consumes the single-use token,
updates the Argon2id hash, `password_changed_at=now()`, **revokes all** the user's sessions, creates
no new session (`200` with a "sign in again" message). Invalid/expired/used → generic
`400 invalid_or_expired_token`. (Link is founder-shared in v1; see admin-api trigger-reset.)

### POST /api/auth/forgot-password (deferred)
Always `202` with the same neutral message regardless of email existence. In v1 it performs **no
delivery** (no email provider) — reset is founder-mediated. Wired now so enabling email later turns
on true self-service without API changes.

### `MeOut`
```json
{ "user_id":"uuid","email":"a@b.c","is_platform_admin":false,
  "active_tenant":{"id":"uuid","name":"a@b.c"},
  "memberships":[{"tenant_id":"uuid","name":"a@b.c","role":"tenant_admin"}],
  "csrf_token":"base64url" }
```
