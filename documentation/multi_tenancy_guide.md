# Multi-Tenant Authentication and User Management Specification

## Purpose

This document specifies invite-only, email-and-password authentication and tenant isolation for a React frontend, asynchronous FastAPI backend, and PostgreSQL database. It is intended as an implementation contract for a coding agent.

The system must allow platform administrators to invite users by email, prevent ordinary users from accessing platform administration, let an invited user choose a password after proving possession of the invited email address, maintain server-side sessions, and enforce tenant boundaries throughout the application.

Passwords must be one-way hashed rather than encrypted. Reversible encryption would allow anyone with the key to recover every password; OWASP recommends a modern password-hashing algorithm such as Argon2id instead. No design can make password entry absolutely unknowable to an operator who controls the deployed frontend or backend code, but the implementation must ensure that plaintext passwords are never persisted, logged, returned, emailed, or intentionally exposed after the authentication request.[^1][^2]

## Scope

### Included

- Global user identities keyed by normalized email address
- Tenants and user-to-tenant memberships
- Platform-administrator-only invitation and user-management APIs
- Email invitation acceptance and first-password setup
- Login, logout, session validation, and tenant switching
- Password reset
- Password hashing with Argon2id
- Opaque server-side sessions using secure cookies
- CSRF protection and authentication rate limiting
- Application-layer tenant authorization
- PostgreSQL row-level security as defense in depth
- Audit events that exclude credentials and secret tokens
- React routes and state required for these flows
- Migrations, backend tests, frontend tests, and security acceptance criteria

### Excluded from version 1

- Public self-registration
- Social login, SAML, OIDC, or enterprise SSO
- HTTP Basic Authentication
- API keys and machine identities
- Billing or tenant provisioning workflows
- Fine-grained permissions beyond the roles defined here
- Impersonation
- Password recovery by administrators

“Basic authentication” in this specification means a simple email-and-password product experience. It does not mean the HTTP `Authorization: Basic` scheme.

## Security invariants

The implementation is invalid if any invariant below is violated:

1. An email address alone is insufficient to claim an invited account.
2. Invitation acceptance requires a cryptographically random, single-use, expiring token delivered to the invited email address.
3. Plaintext passwords and raw session, invitation, reset, and CSRF tokens are never stored in PostgreSQL.
4. Passwords are stored only as Argon2id encoded hashes. FastAPI’s current security guidance uses `pwdlib` and recommends Argon2.[^3]
5. Browser JavaScript cannot read the session token.
6. Every protected backend operation authenticates the session and authorizes the requested action server-side.
7. React route hiding is never treated as authorization.
8. Tenant identity is derived from the authenticated session and verified membership, not trusted from a client-supplied body, query parameter, or header.
9. Every tenant-owned query, mutation, cache entry, background job, export, object-storage key, and search document is tenant scoped. OWASP specifically requires tenant identifiers in tenant-varying cache keys.[^4]
10. Resource lookups combine resource and tenant predicates in the same authorization path; list authorization does not implicitly authorize update or delete operations.[^5]
11. Authentication endpoints return generic failures where a specific response would permit email or account enumeration.[^6]
12. Production authentication traffic is HTTPS-only.

## Roles

| Role | Scope | Capabilities |
|---|---|---|
| `platform_admin` | Entire deployment | Create, resend and revoke invitations; list users; disable users; assign memberships; access the platform admin UI |
| `tenant_admin` | One tenant | Normal tenant access plus future tenant-level management; no platform admin access in version 1 |
| `member` | One tenant | Access application resources belonging to that tenant |

A user may belong to multiple tenants. `platform_admin` is a global privilege and must not be inferred from tenant membership. The first platform administrator must be bootstrapped by a CLI command or controlled database migration; no public “create first admin” HTTP endpoint may exist.

MFA is outside the version 1 user flow, but platform administrators should be migrated to MFA as the next security increment because privileged accounts have disproportionate impact.[^7]

## Architecture

```text
Browser / React
    |
    | HTTPS, JSON, secure cookies, CSRF header
    v
FastAPI authentication and authorization dependencies
    |
    | async transaction + tenant context
    v
PostgreSQL
    |- users
    |- tenants
    |- tenant_memberships
    |- invitations
    |- sessions
    |- password_reset_tokens
    |- auth_audit_events
    `- tenant-owned application tables

Email provider
    `- invitation and password-reset links
```

Prefer serving React and `/api` under the same site through one reverse proxy. This reduces CORS complexity. If development uses separate origins, configure an explicit frontend origin and credentialed CORS; never combine credentialed requests with a wildcard allowed origin.

## Data model

Use UUID primary keys, UTC `timestamptz`, foreign keys, explicit check constraints, and migrations. Use PostgreSQL `citext` for case-insensitive email uniqueness, or store a separately normalized lowercase email if extensions are disallowed.

### SQL migration

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE tenants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email citext NOT NULL UNIQUE,
    password_hash text,
    status text NOT NULL DEFAULT 'invited'
        CHECK (status IN ('invited', 'active', 'disabled')),
    is_platform_admin boolean NOT NULL DEFAULT false,
    password_changed_at timestamptz,
    failed_login_count integer NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
    login_blocked_until timestamptz,
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (status = 'active' AND password_hash IS NOT NULL)
        OR status <> 'active'
    )
);

CREATE TABLE tenant_memberships (
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('tenant_admin', 'member')),
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE invitations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email citext NOT NULL,
    role text NOT NULL CHECK (role IN ('tenant_admin', 'member')),
    token_hash bytea NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    accepted_at timestamptz,
    revoked_at timestamptz,
    invited_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (expires_at > created_at)
);

CREATE UNIQUE INDEX uq_open_invitation
ON invitations (tenant_id, email)
WHERE accepted_at IS NULL AND revoked_at IS NULL;

CREATE TABLE sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash bytea NOT NULL UNIQUE,
    csrf_token_hash bytea NOT NULL,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    active_tenant_id uuid NOT NULL REFERENCES tenants(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    user_agent_hash bytea,
    CHECK (expires_at > created_at)
);

CREATE INDEX ix_sessions_user_active
ON sessions (user_id, expires_at)
WHERE revoked_at IS NULL;

CREATE TABLE password_reset_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash bytea NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (expires_at > created_at)
);

CREATE TABLE auth_audit_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    target_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    tenant_id uuid REFERENCES tenants(id) ON DELETE SET NULL,
    event_type text NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('success', 'failure')),
    request_id text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
```

The migration must add a non-null `tenant_id` foreign key and a tenant-leading index to every tenant-owned table. For an existing populated table, migrate in phases: add nullable column, backfill deterministically, validate ownership, add foreign key and index, then set `NOT NULL`. Do not silently assign ambiguous rows to an arbitrary tenant.

### Configuration

| Setting | Default | Requirement |
|---|---:|---|
| Invitation lifetime | 24 hours | Configurable; single use |
| Password-reset lifetime | 30 minutes | Configurable; single use |
| Session absolute lifetime | 12 hours | Configurable |
| Session idle timeout | 60 minutes | Configurable |
| Session activity write interval | 5 minutes | Avoid a database write on every request |
| Minimum password length | 15 characters | Password-only authentication |
| Maximum password length | At least 128 characters | Prevent unreasonable resource use without rejecting passphrases |
| Login failure delay | Progressive, capped at 30 seconds | Per account and source; avoid permanent lockout |
| Invitation token entropy | 256 bits | Generated by a CSPRNG |
| Session token entropy | 256 bits | Generated by a CSPRNG |
| Reset token entropy | 256 bits | Generated by a CSPRNG |

Current NIST guidance requires a minimum of 15 characters when a password is the sole authentication factor, while allowing shorter passwords when used as part of MFA. Do not require arbitrary uppercase, lowercase, digit, or symbol combinations. Permit spaces and passphrases, reject common or known-compromised passwords, and do not force periodic password changes without evidence of compromise.[^8]

## Secret handling

Use Python’s `secrets.token_bytes(32)` for invitation, reset, session, and CSRF secrets. Encode raw URL tokens with unpadded base64url and store only `sha256(raw_token)` as `bytea`. A database leak must not make active bearer tokens immediately usable.

Use a constant-time comparison where direct comparisons occur. Database equality lookup on a SHA-256 digest is acceptable for locating a token, followed by checks for expiry, revocation, consumption, user status, and tenant status.

Do not include raw tokens or passwords in:

- Logs or traces
- Exception messages
- Analytics
- Audit metadata
- Error-reporting payloads
- Database query parameters captured by APM
- Email subject lines
- URLs sent to third-party analytics

Apply `Referrer-Policy: no-referrer` to invitation and reset pages. Prefer putting the raw token in the URL fragment, for example `/accept-invite#token=...`, because fragments are not sent in HTTP requests. React must read the fragment once, immediately remove it using `history.replaceState`, keep it only in memory, and submit it to FastAPI over HTTPS. If query parameters are used instead, remove them immediately and ensure access logs and referrers cannot capture them.

A password pepper is optional, not required for version 1. If introduced later, store it in a secret manager rather than PostgreSQL; document rotation because changing a pepper ordinarily requires users to authenticate or reset their passwords.[^1]

## Password hashing

Use `pwdlib` with Argon2 support and its recommended hasher configuration rather than hand-constructing salts or cryptographic parameters.[^3]

```python
from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    return password_hasher.verify(password, encoded_hash)
```

Requirements:

- Pass the password as a Python string directly to the password library.
- Never trim, lowercase, normalize, or silently transform a password.
- Validate length before hashing.
- Confirm the password field in React using a second input, but enforce all policy in FastAPI.
- On successful login, rehash when `pwdlib` reports that stored parameters require upgrading.
- Perform expensive password hashing and verification without blocking the asyncio event loop. Use `anyio.to_thread.run_sync`, `asyncio.to_thread`, or an explicitly bounded worker pool.
- Limit concurrent hashing work to protect the service from CPU and memory exhaustion.

## Invitation lifecycle

### Admin creates invitation

`POST /api/admin/invitations` requires `platform_admin`.

Request:

```json
{
  "email": "person@example.com",
  "tenant_id": "uuid",
  "role": "member"
}
```

Processing must occur in one transaction:

1. Normalize the email for identity lookup while preserving a display form if desired.
2. Verify that the tenant exists and is active.
3. If an active user already has this membership, return `409 membership_exists`.
4. Create the user in `invited` status if no global user exists.
5. If the user exists and is disabled, return `409 user_disabled` rather than silently reactivating the account.
6. Revoke any prior open invitation for the same email and tenant.
7. Generate a new raw token and store only its digest.
8. Set expiry to 24 hours from creation.
9. Write `invitation.created` to the audit table without the raw token.
10. Commit before attempting email delivery.
11. Send the invitation email. If delivery fails, retain the invitation but report delivery failure to the admin and allow resend.

Admin responses may disclose membership state because the caller is privileged. The endpoint must never return the raw token in production. A development-only email sink may expose links locally, guarded by an explicit non-production setting.

### User accepts invitation

`POST /api/auth/accept-invitation` is public but rate limited.

Request:

```json
{
  "token": "raw-base64url-token",
  "password": "chosen passphrase",
  "password_confirmation": "chosen passphrase"
}
```

Processing:

1. Hash the supplied token and begin a transaction.
2. Lock the invitation row with `SELECT ... FOR UPDATE`.
3. Reject with a generic `400 invalid_or_expired_invitation` if it is missing, expired, revoked, or consumed.
4. Validate both passwords match and enforce password policy.
5. Load or create the user associated with the invitation email.
6. Reject disabled users and disabled tenants.
7. Hash the password outside the event loop. Avoid holding a database transaction while waiting on a saturated hash worker; use a two-phase approach and re-lock/revalidate before commit.
8. In the final transaction, re-lock and revalidate the invitation.
9. Set the user’s `password_hash`, `status = 'active'`, and `password_changed_at = now()`.
10. Upsert the membership using the invitation’s tenant and role.
11. Set `accepted_at = now()`.
12. Revoke any other unconsumed invitation for the same user and tenant.
13. Create a session for the invitation tenant.
14. Write audit events for invitation acceptance and session creation.
15. Commit, set cookies, and return the current-user payload.

Invitation and reset tokens must be random, single-use, and expire after an appropriate period. The unique digest and row lock prevent concurrent double acceptance.[^9]

## Login and session flow

### Login

`POST /api/auth/login` accepts email and password and returns the same generic `401 invalid_credentials` response for unknown email, wrong password, disabled user, or unavailable membership. Generic failures reduce account enumeration.[^6]

For unknown users, run one verification against a process-level dummy Argon2 hash so timing is closer to the existing-user path. Do not generate the dummy hash per request.

On success:

1. Reset failure counters.
2. Determine available active memberships.
3. If there is one membership, use it as `active_tenant_id`.
4. If there are multiple memberships, use the most recently selected still-valid tenant or return the list for an explicit selection step.
5. Revoke or retain prior sessions according to product policy; version 1 permits multiple sessions.
6. Create a random session token and random CSRF token; store only their hashes.
7. Set the session cookie and return the raw CSRF token in the JSON response.
8. Record `last_login_at` and an audit event.

### Cookie

Set the session as:

```http
Set-Cookie: __Host-session=<opaque-token>; Path=/; Secure; HttpOnly; SameSite=Lax
```

The `__Host-` prefix requires `Secure`, `Path=/`, and no `Domain` attribute. `HttpOnly` prevents frontend JavaScript from reading the credential. OWASP recommends explicit `SameSite` but treats it as defense in depth, not a replacement for CSRF protection.[^10][^11]

### Session authentication

A shared FastAPI dependency must:

1. Read `__Host-session`.
2. SHA-256 hash it.
3. Load an unrevoked, unexpired session joined to active user, active tenant, and active membership.
4. Enforce idle timeout using `last_seen_at`.
5. Update `last_seen_at` no more than once every five minutes.
6. Return a typed immutable security context.

```python
@dataclass(frozen=True, slots=True)
class RequestIdentity:
    user_id: UUID
    tenant_id: UUID
    membership_role: Literal["tenant_admin", "member"]
    is_platform_admin: bool
    session_id: UUID
```

Do not accept a client-supplied `is_admin`, role, user ID, or tenant ID as authoritative.

### CSRF

All state-changing cookie-authenticated requests must:

- Require an `X-CSRF-Token` header whose digest matches the current session’s `csrf_token_hash`.
- Validate `Origin` against the configured frontend origin; if `Origin` is absent where legitimately expected, validate `Referer` conservatively.
- Continue using `SameSite=Lax` as defense in depth.
- Reject simple cross-origin content types where the endpoint expects JSON.

Rotate the CSRF token when the user logs in or switches tenant. React keeps the raw CSRF token in memory, not `localStorage`.

### Logout

`POST /api/auth/logout` requires session authentication and CSRF validation. It sets `revoked_at`, clears the cookie with matching attributes, and returns `204`. Logout must be idempotent.

### Tenant switching

`POST /api/auth/switch-tenant` accepts the target tenant UUID. FastAPI verifies an active membership, rotates the session and CSRF tokens, sets `active_tenant_id`, revokes the old token, and returns an updated current-user payload. Token rotation avoids carrying a pre-switch credential context forward.

## Password reset

`POST /api/auth/forgot-password` always returns `202` with the same message, regardless of whether the email exists.[^6]

If the email belongs to an active user:

1. Invalidate previous unconsumed reset tokens.
2. Generate a 256-bit token and store only its SHA-256 digest.
3. Set a 30-minute expiry.
4. Send a reset link using the same fragment-token and no-referrer rules as invitations.

`POST /api/auth/reset-password` validates and consumes the token, updates the Argon2id hash, updates `password_changed_at`, revokes every existing session for the user, and creates no new session until the user logs in again. Reset tokens are single-use and no account change occurs until a valid token is presented.[^9]

Platform administrators can disable an account or send a reset invitation, but cannot view, set, email, or recover a user’s password.

## API contract

| Method | Path | Authentication | Purpose |
|---|---|---|---|
| `POST` | `/api/auth/login` | Public, rate limited | Authenticate and start session |
| `POST` | `/api/auth/logout` | Session + CSRF | Revoke current session |
| `GET` | `/api/auth/me` | Session | Return identity, active tenant and memberships |
| `POST` | `/api/auth/accept-invitation` | Public, token, rate limited | Set first password and activate account |
| `POST` | `/api/auth/forgot-password` | Public, rate limited | Send reset email if eligible |
| `POST` | `/api/auth/reset-password` | Public, token, rate limited | Replace password and revoke sessions |
| `POST` | `/api/auth/switch-tenant` | Session + CSRF | Change active tenant and rotate session |
| `GET` | `/api/admin/users` | Platform admin | Paginated user and membership listing |
| `POST` | `/api/admin/invitations` | Platform admin + CSRF | Create invitation |
| `POST` | `/api/admin/invitations/{id}/resend` | Platform admin + CSRF | Rotate token, expiry and resend |
| `DELETE` | `/api/admin/invitations/{id}` | Platform admin + CSRF | Revoke invitation |
| `PATCH` | `/api/admin/users/{id}` | Platform admin + CSRF | Disable or enable eligible user |
| `PUT` | `/api/admin/users/{id}/memberships/{tenant_id}` | Platform admin + CSRF | Add or change membership |
| `DELETE` | `/api/admin/users/{id}/memberships/{tenant_id}` | Platform admin + CSRF | Remove membership and revoke affected sessions |

Use stable machine-readable errors:

```json
{
  "error": {
    "code": "invalid_credentials",
    "message": "The email or password is incorrect.",
    "request_id": "..."
  }
}
```

Public authentication errors must remain generic. Detailed causes belong only in redacted server-side audit events.

## FastAPI structure

Use clear boundaries rather than embedding authentication logic in routers:

```text
app/
  api/
    auth.py
    admin_users.py
  auth/
    dependencies.py
    passwords.py
    tokens.py
    sessions.py
    csrf.py
    rate_limit.py
  tenants/
    context.py
    authorization.py
  repositories/
    users.py
    invitations.py
    sessions.py
    memberships.py
  services/
    auth_service.py
    invitation_service.py
    password_reset_service.py
    email_service.py
  models/
  schemas/
  migrations/
```

Rules:

- Routers validate transport data and call services.
- Services own workflows and transaction boundaries.
- Repositories require explicit tenant context for tenant-owned data.
- Dependencies perform authentication and role checks.
- Domain services must not import React-specific concepts.
- Email delivery occurs after transaction commit through an outbox or retryable task when infrastructure supports it. For version 1, synchronous post-commit delivery is acceptable if failures are surfaced and resend is available.

## Tenant authorization

Every tenant-owned repository method must require `tenant_id` as a keyword-only argument and include it in SQL:

```python
async def get_project(
    conn: AsyncConnection,
    *,
    project_id: UUID,
    tenant_id: UUID,
) -> Project | None:
    result = await conn.execute(
        text("""
            SELECT *
            FROM projects
            WHERE id = :project_id
              AND tenant_id = :tenant_id
        """),
        {"project_id": project_id, "tenant_id": tenant_id},
    )
    return result.mappings().one_or_none()
```

Do not fetch by `project_id` and authorize afterward. Use `404` for tenant-owned resources that do not exist within the caller’s tenant, avoiding disclosure that the identifier exists elsewhere.

Apply tenant scope to:

- Reads, writes, deletes, counts and aggregates
- Search and export
- File and object-storage paths
- Background jobs and queued payloads
- WebSocket and SSE subscriptions
- Cache keys
- Idempotency keys
- Observability dimensions, without exposing sensitive tenant content

## PostgreSQL row-level security

PostgreSQL row security can restrict rows returned or modified in addition to normal grants. Use it as defense in depth against missing application predicates.[^12]

The migration owner and runtime application role must be separate. The runtime role must not be a superuser, table owner, or possess `BYPASSRLS`. Enable and force RLS on tenant-owned tables:

```sql
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects FORCE ROW LEVEL SECURITY;

CREATE POLICY projects_tenant_policy
ON projects
USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
)
WITH CHECK (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
);
```

Set tenant context transaction-locally on every protected transaction:

```sql
SELECT set_config('app.tenant_id', :tenant_id, true);
SELECT set_config('app.user_id', :user_id, true);
```

With SQLAlchemy async, begin a transaction, call `set_config(..., true)`, perform all work, and commit or roll back before returning the pooled connection. Never use session-level `SET` on a pooled connection because context could leak into a later request.

RLS based on an application-set custom parameter is defense against accidental unscoped queries, not against SQL injection or a fully compromised runtime service: the runtime role can set that parameter. Parameterize all SQL and retain application authorization.

RLS tests must verify:

- Tenant A cannot select, update or delete Tenant B rows.
- Tenant A cannot insert a row labeled Tenant B.
- Missing tenant context returns no rows and rejects writes.
- Runtime role cannot bypass RLS.
- Pooled connections do not retain tenant context between transactions.

## React requirements

### Routes

```text
/login
/accept-invite
/forgot-password
/reset-password
/app/*
/admin/users
/forbidden
```

The router may hide or redirect unauthorized pages for user experience, but the API remains the authority. `/admin/users` renders only when `/api/auth/me` reports `is_platform_admin: true`; all admin API calls independently enforce the same privilege.

### Authentication state

Create one `AuthProvider` or equivalent query-backed store that:

- Calls `GET /api/auth/me` on application bootstrap.
- Keeps identity, active tenant, memberships and CSRF token in memory.
- Uses `credentials: 'include'` for API calls.
- Adds `X-CSRF-Token` to unsafe requests.
- Clears user state on `401`.
- Refetches current identity after login, invitation acceptance, reset where relevant, and tenant switch.
- Never stores the session token or password.
- Does not persist the CSRF token to `localStorage`.

### Forms

Login, invitation acceptance and reset forms must:

- Use semantic labels and browser password-manager-compatible fields.
- Use `autocomplete="email"`, `autocomplete="current-password"`, and `autocomplete="new-password"` appropriately.
- Allow paste into password fields.
- Include show/hide password controls that are keyboard accessible.
- Display generic authentication errors.
- Disable duplicate submission while a request is in flight without destroying entered values.
- Clear password values from component state after completion or unmount where practical.
- Avoid analytics events containing field values.

The invitation page must not ask for the email again; the token binds the accepted invitation to the email and tenant. It may display a masked email returned by a token-inspection endpoint, but that endpoint must be rate limited and reveal only minimal data.

### Admin page

The admin page must provide:

- Paginated users with email, status, memberships and last-login timestamp
- Invite form with email, tenant and role
- Pending invitation status and expiry
- Resend and revoke actions
- Disable/enable user actions with confirmation
- Membership add, change and remove actions
- Clear success and failure feedback

It must never display password hashes, token hashes, raw tokens, session tokens, reset tokens, or detailed authentication failure data.

## Rate limiting and abuse controls

Apply independent controls to login, invitation acceptance, forgotten-password requests, password resets, and admin invitation creation. Use both source-based and account/token-based limits. Do not rely solely on an in-process dictionary when running multiple workers or replicas.

Preferred enforcement order:

1. Edge or reverse-proxy rate limits for coarse source abuse.
2. Shared application limits using Redis when available.
3. PostgreSQL-backed counters if Redis is intentionally excluded.
4. Progressive delays and temporary blocks rather than permanent account lockout, which can be abused for denial of service.

Never reveal whether throttling was triggered for a known versus unknown account. Security events should record a request ID and coarse outcome without passwords or raw tokens.

## Logging and auditing

Audit these events:

- Login success and failure
- Logout
- Invitation created, resent, revoked, accepted and rejected
- Password reset requested and completed
- Password changed
- Session revoked
- User enabled or disabled
- Membership added, changed or removed
- Tenant switched
- Platform-admin authorization failure

Audit metadata may include non-secret IDs, role changes, request ID, and a privacy-reviewed source fingerprint. It must not contain plaintext passwords, password hashes, raw or hashed bearer tokens, full request bodies, or sensitive email content. Access to audit events is itself privileged.

Configure HTTP access logs to avoid query strings on token-bearing routes. Add application log filters for keys matching `password`, `token`, `authorization`, `cookie`, `set-cookie`, and `csrf`. Review APM and exception middleware because automatic request capture can bypass application logging discipline.

## Email requirements

Invitation and reset emails must:

- Contain one HTTPS link to the configured canonical frontend origin.
- Avoid credentials and raw tokens in the subject.
- State expiry without exposing internal IDs.
- Tell recipients to ignore the message if unexpected.
- Not send a password chosen by an admin.

Construct URLs from trusted configuration, never from the inbound `Host` header. This prevents poisoned reset or invitation links.

## Error and status behavior

| Situation | Response |
|---|---|
| Missing or invalid session | `401` |
| Authenticated but insufficient global role | `403` |
| Tenant resource absent or belongs to another tenant | `404` |
| Login failure | Generic `401 invalid_credentials` |
| Invalid, expired, revoked or used public token | Generic `400 invalid_or_expired_token` |
| Duplicate active membership from admin API | `409 membership_exists` |
| CSRF failure | `403 csrf_failed` |
| Rate limited | `429`, with safe retry guidance |
| Validation failure | `422`, without echoing password or token values |

## Implementation sequence

1. Add migrations for users, tenants, memberships, invitations, sessions, reset tokens and audit events.
2. Backfill `tenant_id` into existing domain tables and add tenant-leading indexes.
3. Create separate migration-owner and runtime database roles.
4. Implement token, password and redaction utilities with unit tests.
5. Implement repositories and transaction-scoped tenant context.
6. Implement authentication dependencies and session/CSRF middleware or dependencies.
7. Implement invitation creation and email delivery.
8. Implement invitation acceptance and first-password setup.
9. Implement login, `/me`, logout and tenant switching.
10. Implement password reset.
11. Add application-level tenant predicates to all existing repositories.
12. Enable and test RLS after application scoping is complete.
13. Implement React authentication state and public forms.
14. Implement the platform admin page and backend role enforcement.
15. Add rate limiting, audit events, log redaction and operational alerts.
16. Run the full security and cross-tenant test matrix before production migration.

## Test specification

### Unit tests

- Argon2 hashes differ for the same password because each uses a unique salt.
- Correct password verifies; incorrect password does not.
- Password policy accepts long passphrases and rejects short or blocked passwords.
- Token generator produces URL-safe values of configured entropy.
- Token digesting is deterministic while raw tokens are not stored.
- Email normalization is consistent.
- Session and CSRF cookie/header helpers set required attributes.
- Log redaction removes secret fields.

### Invitation integration tests

- Platform admin can create an invitation.
- Non-admin receives `403` from every admin endpoint, even when calling it directly.
- Invited email receives a link and can choose a first password.
- Knowing an invited email without the token cannot claim the account.
- Expired, revoked, malformed and consumed tokens fail generically.
- Simultaneous acceptance requests produce exactly one success.
- Resend invalidates the previous token.
- Acceptance creates exactly one membership and one valid session.
- Disabled user or tenant cannot accept an invitation.

### Authentication tests

- Unknown email and wrong password return indistinguishable public responses.
- Plaintext password is absent from database, logs, traces and audit metadata.
- Session cookie is `Secure`, `HttpOnly`, `SameSite=Lax`, host-only and `Path=/`.
- Logout revokes the server-side session and clears the cookie.
- Expired, idle, revoked and disabled-user sessions fail.
- Password reset consumes one token and revokes all prior sessions.
- Unsafe requests fail without valid CSRF header or allowed origin.
- Login and reset endpoints enforce shared rate limits across workers.

### Tenant-isolation tests

Create Tenant A and Tenant B with overlapping-looking data, then verify:

- A user in Tenant A cannot read, list, count, search, export, update or delete Tenant B data.
- Guessing Tenant B resource UUIDs returns `404`.
- Supplying Tenant B’s ID in JSON, query strings or custom headers does not change authorization context.
- A multi-tenant user sees only the active tenant and can switch only to a valid membership.
- Removing a membership revokes sessions using that tenant.
- Cache and background-job keys include tenant identity.
- RLS blocks cross-tenant reads and writes when application filters are intentionally omitted in a test.
- Reused pooled connections do not leak prior tenant context.

### Frontend tests

- Protected routes redirect unauthenticated users.
- Admin route is hidden from ordinary users, and direct navigation shows forbidden or redirects.
- Admin API `403` is handled correctly.
- Passwords and session tokens are not written to browser storage.
- Invitation token is removed from the visible URL immediately.
- Duplicate submissions are prevented.
- Keyboard and screen-reader behavior works for forms and dialogs.

## Operational requirements

- Run migrations before enabling the feature flag.
- Bootstrap at least one platform admin through a controlled CLI command.
- Verify production canonical URL, HTTPS, secure-cookie behavior and email DNS configuration.
- Store database, email and optional pepper credentials in a secret manager.
- Back up PostgreSQL and test restore procedures.
- Monitor login failures, invitation-delivery failures, reset spikes, cross-tenant authorization failures and unexpected admin actions.
- Periodically delete expired sessions and consumed/expired tokens according to the retention policy.
- Retain audit events according to the application’s legal and operational needs; avoid indefinite retention by default.

## Definition of done

The feature is complete only when:

- A platform admin can invite an email into a selected tenant and role.
- An ordinary user cannot access or successfully call any platform admin operation.
- The invited user must possess the emailed, expiring, single-use token before setting the first password.
- The database contains an Argon2id hash and never the plaintext password.
- Login establishes an opaque server-side session in a secure `HttpOnly` cookie.
- CSRF protection is enforced for every unsafe cookie-authenticated request.
- Logout and password reset revoke sessions server-side.
- All existing tenant-owned data paths are scoped and covered by negative cross-tenant tests.
- PostgreSQL RLS is enabled and validated for tenant-owned tables without relying on a privileged runtime role.
- Raw secrets are absent from browser storage, URLs after initial parsing, logs, traces, audit events and error reports.
- Rate limiting functions across all production workers or replicas.
- Migrations, backend tests, frontend tests, production build and security acceptance tests pass.

## Coding-agent directives

- Inspect the existing repository, dependency versions, ORM and migration conventions before editing.
- Reuse established architecture where it does not violate this specification.
- Do not replace the application’s data-access layer merely to implement authentication.
- Present the proposed migration and affected tables before applying destructive changes.
- Implement in reviewable increments matching the implementation sequence.
- Do not add JWTs, put credentials in `localStorage`, expose raw invitation tokens from admin APIs, or weaken tenant checks for convenience.
- Treat uncertain security behavior as a blocker requiring explicit clarification rather than inventing a permissive fallback.
- Report changed files, migration behavior, commands run, test results, and any unmet requirement at completion.

---

## References

1. [Password Storage - OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) - Passwords should never be stored in plain text. Instead, they must be protected using strong, slow h...

2. [Cryptographic Storage - OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html) - This article provides a simple model to follow when implementing solutions to protect data at rest. ...

3. [OAuth2 with Password (and hashing), Bearer with JWT tokens](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) - pwdlib is a great Python package to handle password hashes. It supports many secure hashing algorith...

4. [Multi Tenant Security - OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html) - Include the tenant identifier in every cache key whose value or authorization varies by tenant. Give...

5. [Authorization Decisions And Output Handling - OWASP Cheat ...](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Decisions_And_Output_Handling_Cheat_Sheet.html) - Cover every data path. Enforce the restriction on list, search, export, count, aggregate, and direct...

6. [Authentication - OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) - ... generic error message regardless of whether: The user ID or password was incorrect. The account ...

7. [Multifactor Authentication - OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html) - Multifactor Authentication (MFA) or Two-Factor Authentication (2FA) is when a user is required to pr...

8. [NIST Special Publication 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html) - Verifiers and CSPs MAY allow passwords that are only used as part of multi-factor authentication pro...

9. [Forgot Password - OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) - Single use and expire after an appropriate period. Do not make a change to the account until a valid...

10. [Session Management - OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) - Treat SameSite as defense in depth against CSRF, not as a replacement for a CSRF token. Session cook...

11. [Cross-Site Request Forgery Prevention - OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) - SameSite is a cookie attribute (similar to HTTPOnly, Secure etc.) which aims to mitigate CSRF attack...

12. [PostgreSQL: Documentation: 18: 5.9. Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) - In addition to the SQL-standard privilege system available through GRANT, tables can have row securi...

