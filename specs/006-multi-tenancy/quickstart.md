# Quickstart: Multi-Tenancy — Verification

Manual verification per story, plus the migration/bootstrap/RLS steps that unit tests (SQLite)
cannot cover. Run the backend against **Postgres** for anything involving RLS, roles, or the real
migration. Assumes phases 1–5 complete.

## 0. One-time setup (Postgres + roles + migration)

1. **Configure the two DB roles** in `.env`: `DATABASE_URL` = the non-privileged **runtime**
   role (`APP_DB_USER`/`APP_DB_PASSWORD`), `DATABASE_OWNER_URL` = the **owner/superuser**
   (`POSTGRES_USER`/`POSTGRES_PASSWORD`) — Alembic uses the owner. The runtime role itself is
   created by migration `0004_rls` (step 4) from `APP_DB_USER`/`APP_DB_PASSWORD`, running as
   the owner (needs `CREATEROLE`; the compose superuser has it). On a managed Postgres without
   `CREATEROLE`, create it manually first:
   `CREATE ROLE wcl_app LOGIN PASSWORD '…' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;`.
   Start the DB (`docker compose up -d db`) before the steps below; start the **app** only
   after step 4.
2. **Create the auth/tenant schema**: `uv run alembic upgrade 0002_auth_tenancy`. This creates the
   auth/tenant tables only — it does **not** yet add `tenant_id` to the existing tables.
3. **Bootstrap the founder**: `uv run python -m backend.cli.bootstrap_admin` (prompts for email +
   password, or reads from env/secret). Creates the platform-admin user + their tenant + owner
   membership. Confirm **no** HTTP route can create a first admin. This must run **before** step 4
   because the founder-data backfill needs the founder tenant to exist.
4. **Add tenant columns + RLS**: `uv run alembic upgrade head`. Migration `0003` adds `tenant_id` to
   the 7 tenant-owned tables (nullable → **backfill all existing rows to the founder tenant** → not
   null + indexes), then `0004` enables RLS. The backfill **fails loudly** if no platform admin
   exists — so step 3 must precede it (see `research.md` R8).
5. Start backend + frontend (same origin via the Vite proxy / reverse proxy). Confirm `/health` ok.

## 1. US1 — Invite a friend and activate (P1)

1. Sign in as the founder at `/login`. Open `/admin/users`.
2. Create an invitation for a test email + role → the response shows an **invite link once**; copy it.
3. Open the link in a fresh browser/incognito → `/accept-invite` reads `#token`, immediately strips
   it from the address bar (verify: reload does not re-accept), asks for a password (not the email).
4. Set a policy-compliant password → you land signed in, in an **empty** workspace.
5. Negative: a second open of the same link fails generically; an edited/garbage token fails
   generically; knowing the email without the link cannot activate; there is no public sign-up route.

## 2. US2 — Sign in / stay signed in / sign out (P1)

1. Sign in with correct credentials → reach the chat shell. Reload → still signed in.
2. Wrong password, unknown email, and a disabled account all return the **same** generic error.
3. Sign out → the session is immediately invalid (reload bounces to `/login`; the old cookie no
   longer works). Confirm via DevTools that the session cookie is `Secure; HttpOnly; SameSite=Lax`,
   host-only, `Path=/`, and that no session/password value is in `localStorage`/`sessionStorage`.

## 3. US3 — Isolation between two users (P1, gating)

1. As user A: add self/friend characters + a main guild; hold a chat that tracks a raid and renders a
   chart; download a per-message report.
2. As user B (separate browser): confirm an **empty** workspace — none of A's profile, conversations,
   raids, or artifacts are visible.
3. As B, try to open A's conversation id directly (URL/API), pass A's ids in request body/query, and
   guess A's raid/report ids → every attempt returns `404`/empty, never A's data.
4. Confirm a guild/chat question for B uses only B's data; the WCL cache does not serve A's cached
   lookups to B.
5. **RLS (Postgres)**: run `test_rls` (or manually) — with the app `WHERE tenant_id` removed, RLS
   still blocks cross-tenant read/write; missing `app.tenant_id` yields no rows; the runtime role
   cannot bypass; a reused pooled connection does not leak the prior tenant context.

## 4. US4 — Admin surface (P2)

1. As founder at `/admin/users`: see users (email, status, last-login) and pending invitations
   (status, expiry, **no token shown**).
2. Resend an invitation → old link dies, new link shown once. Revoke one → link dies.
3. Disable a user → that user can no longer sign in and their active session/socket stops on next
   action; re-enable restores sign-in.
4. As an ordinary user: `/admin/users` is not shown; navigating there shows Forbidden; calling any
   `/api/admin/*` directly returns `403`.
5. Confirm no view shows password/token hashes.

## 5. US5 — Founder-triggered password reset (P2)

1. As founder, trigger a reset for a user → copy the **reset link** shown once.
2. As that user, open the link, set a new password → all their prior sessions are revoked (an older
   tab is signed out on next action); sign in with the new password works.
3. An expired/used reset link fails generically. Confirm the founder never sees/sets the password.

## 6. Hardening checks

- Repeated bad logins slow progressively (per account + source), never a permanent lockout; throttle
  responses don't reveal account existence.
- Inspect DB, logs, and a captured request trace: **no** plaintext password and **no** raw/hashed
  token appears in `users`/`sessions`/`invitations` raw columns, logs, audit metadata, or errors.
- `auth_audit_events` records login/logout/invitation/reset/disable/membership events with non-secret
  ids only.

## 7. Regression (single user)

With only the founder (and their migrated data), confirm every prior capability works unchanged:
streaming chat, raid tracking + investigate, profile/characters/guild + spec guides, interactive
charts, math rendering, conversation + per-message PDF — all now scoped to the founder, zero
behavior change.
