# Phase 1 Data Model: Multi-Tenancy

Maps the guide's data model onto this repo. UUID PKs, UTC `timestamptz`, FKs, check constraints.
Email uses `citext` on Postgres; models stay SQLite-portable for tests (a normalized-lowercase
fallback is used where `citext` is unavailable). All new and altered structures are delivered via
Alembic (research R1); SQLite test fixtures build `Base.metadata` directly and skip Postgres-only
RLS.

Legend: **[new]** table, **[alter]** existing table.

---

## New auth/tenant tables (migration `0002_auth_tenancy`)

### `users` [new] — global identity
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `email` | citext UNIQUE NOT NULL | case-insensitive identity |
| `password_hash` | text NULL | Argon2id; NULL until activation |
| `status` | text NOT NULL `'invited'` | `invited` \| `active` \| `disabled`; CHECK active ⇒ hash present |
| `is_platform_admin` | bool NOT NULL false | global privilege; never inferred from membership |
| `password_changed_at` | timestamptz NULL | |
| `failed_login_count` | int NOT NULL 0 | ≥0; progressive throttle (R7) |
| `login_blocked_until` | timestamptz NULL | temporary, never permanent |
| `last_login_at` | timestamptz NULL | shown in admin |
| `created_at`/`updated_at` | timestamptz | |

### `tenants` [new] — a workspace
`id` uuid PK · `name` text NOT NULL (1–200) · `status` text NOT NULL `'active'` (`active`\|`disabled`)
· `created_at`/`updated_at`. In v1 exactly one per user, auto-provisioned at invitation acceptance
(name defaults from the invitee's email); table retained for future multi-member use (plan
Complexity Tracking).

### `tenant_memberships` [new] — user ↔ tenant
PK `(tenant_id, user_id)` · `tenant_id`→tenants ON DELETE CASCADE · `user_id`→users ON DELETE
CASCADE · `role` text CHECK (`tenant_admin`\|`member`) · `status` (`active`\|`disabled`) ·
timestamps. v1: one membership per user as the workspace owner (`tenant_admin`).

### `invitations` [new]
`id` uuid PK · `tenant_id`→tenants CASCADE **NULLABLE** · `email` citext · `role`
CHECK(`tenant_admin`\|`member`) · `token_hash` bytea UNIQUE NOT NULL (sha256 of raw) · `expires_at`
(CHECK > created) · `accepted_at` NULL · `revoked_at` NULL · `invited_by`→users · `created_at`.
Partial unique index `uq_open_invitation (email) WHERE accepted_at IS NULL AND revoked_at IS NULL`
(at most one open invite per person). **In v1 the invite flow creates the tenant on acceptance**,
so `tenant_id` stays NULL until the invitee accepts (see acceptance flow below).

### `auth_sessions` [new]
Named `auth_sessions` (NOT `sessions`) because Google ADK's `DatabaseSessionService` owns a
table named `sessions` in the same database.
`id` uuid PK · `token_hash` bytea UNIQUE NOT NULL · `user_id`→users
CASCADE · `active_tenant_id`→tenants · `created_at` · `last_seen_at` · `expires_at` (CHECK > created)
· `revoked_at` NULL · `user_agent_hash` bytea NULL. (CSRF token is HMAC-derived from the session id,
not stored — research R3.) Index
`ix_auth_sessions_user_active (user_id, expires_at) WHERE revoked_at IS NULL`.

### `password_reset_tokens` [new]
`id` uuid PK · `user_id`→users CASCADE · `token_hash` bytea UNIQUE NOT NULL · `expires_at` (CHECK >
created) · `consumed_at` NULL · `created_at`.

### `auth_audit_events` [new]
`id` bigint identity PK · `occurred_at` · `actor_user_id`→users SET NULL · `target_user_id`→users
SET NULL · `tenant_id`→tenants SET NULL · `event_type` text · `outcome` CHECK(`success`\|`failure`)
· `request_id` text NULL · `metadata` jsonb NOT NULL `'{}'`. **Never** contains passwords, hashes,
or raw/hashed tokens (FR-030).

---

## Altered tenant-owned tables (migration `0003_tenant_columns`)

Each of the 7 gains `tenant_id uuid` → FK `tenants(id)` + a **tenant-leading index**, added in the
guide's phases: add nullable → backfill to the founder tenant (R8) → validate no NULLs → set
`NOT NULL`. Uniqueness that was global becomes per-tenant.

| Table | Add | Uniqueness change |
|---|---|---|
| `conversations` | `tenant_id` NOT NULL + index `(tenant_id, updated_at)` | — |
| `messages` | `tenant_id` NOT NULL + index `(tenant_id, conversation_id, seq)` | keep `uq_message_conv_seq` |
| `tracked_raids` | `tenant_id` NOT NULL + index `(tenant_id, last_asked_at)` | `report_code` unique → **per-tenant** `(tenant_id, report_code)` |
| `captured_graphs` | `tenant_id` NOT NULL + index `(tenant_id, conversation_id)` | — |
| `user_characters` | `tenant_id` NOT NULL + index `(tenant_id, role)` | `uq_user_char_identity` → `(tenant_id, name, server, region, role)` |
| `guild_profile` | `tenant_id` NOT NULL + index `(tenant_id)` | one-per-tenant (replace-on-set stays, scoped) |
| `artifacts` | `tenant_id` NOT NULL + index `(tenant_id, conversation_id)` | — |

`messages` gets its own `tenant_id` (not just the conversation FK) so RLS applies uniformly
(research R5). `tenant_id` is denormalized onto child rows for one consistent RLS predicate; it is
always set from the parent's tenant at write time.

**ADK session tables** (`DatabaseSessionService`): isolated by `user_id = tenant_id` (research R5),
created by ADK, **not** under our RLS.

---

## RLS (migration `0004_rls`, Postgres only)

For each of the 7 tables: `ENABLE` + `FORCE ROW LEVEL SECURITY`, and policy
`USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)` with the same
`WITH CHECK`. Grants: runtime role gets `SELECT/INSERT/UPDATE/DELETE` but is **not** owner/superuser
and lacks `BYPASSRLS`. Protected transactions set `app.tenant_id`/`app.user_id` transaction-locally
(research R4/R5).

---

## Entity relationships

```text
users 1──* tenant_memberships *──1 tenants
users 1──* sessions ─ active_tenant_id ──> tenants
users 1──* password_reset_tokens
tenants 1──* invitations ─ invited_by ──> users
tenants 1──* { conversations, tracked_raids, captured_graphs,
              user_characters, guild_profile, artifacts }
conversations 1──* { messages, captured_graphs, artifacts }   (all also carry tenant_id)
auth_audit_events ─ actor/target ──> users ; ─ tenant ──> tenants
```

## State transitions

- **User.status**: `invited` → (accept) `active` → (admin disable) `disabled` → (admin enable)
  `active`. Activation requires setting `password_hash`.
- **Invitation**: open (`accepted_at`/`revoked_at` NULL, not expired) → `accepted` | `revoked` |
  expired (passive via `expires_at`). Resend revokes the prior open invitation and issues a new
  token. Concurrent accept resolves to one success via `SELECT … FOR UPDATE` on the row + the unique
  `token_hash`.
- **Session**: active → expired (idle via `last_seen_at`, or absolute via `expires_at`) | `revoked`
  (logout, password reset, membership removal, account disable). Rotated on login.
- **Password reset token**: issued → `consumed` (single use) | expired. Consuming updates the hash
  and revokes all the user's sessions.

## Invitation-acceptance flow (one transaction, guide §Invitation lifecycle, adapted to v1 1:1)

1. sha256 the supplied raw token; `SELECT … FOR UPDATE` the invitation.
2. Reject generically if missing/expired/revoked/accepted (`400 invalid_or_expired_invitation`).
3. Validate password policy + confirmation.
4. Load/confirm the `invited` user for the email; reject disabled user/tenant.
5. Hash the password off-loop (two-phase: hash outside the txn, re-lock + revalidate before commit).
6. Set `password_hash`, `status='active'`, `password_changed_at=now()`.
7. **Auto-provision the workspace**: ensure the user's single `tenant` + owner `membership` exist.
8. `accepted_at=now()`; revoke any other open invitation for this email/tenant.
9. Create a session for that tenant; write `invitation.accepted` + `session.created` audit events.
10. Commit; set the `__Host-session` cookie; return the `/me` payload + CSRF token.

## Typed contracts (Pydantic / dataclass)

- `RequestIdentity` (frozen dataclass): `user_id, tenant_id, membership_role, is_platform_admin,
  session_id` — the only authority used by handlers (never client input).
- Requests: `LoginIn{email,password}`, `AcceptInvitationIn{token,password,password_confirmation}`,
  `ForgotPasswordIn{email}`, `ResetPasswordIn{token,password,password_confirmation}`,
  `InvitationIn{email,role}`, `MembershipIn{role}`.
- Responses: `MeOut{user_id,email,is_platform_admin,active_tenant,memberships[],csrf_token}`,
  `InvitationOut{id,email,role,status,expires_at, invite_link?}` (`invite_link` returned **once** on
  create/resend only), `AdminUserOut{id,email,status,last_login_at,memberships[]}`, and the error
  envelope `{error:{code,message,request_id}}`.
