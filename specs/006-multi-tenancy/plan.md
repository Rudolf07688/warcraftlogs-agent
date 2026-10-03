# Implementation Plan: Multi-Tenancy — Invite-Only Accounts & Private Per-User Workspaces

**Branch**: `006-multi-tenancy` | **Date**: 2026-10-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-multi-tenancy/spec.md`, grounded by `documentation/multi_tenancy_guide.md`.

## Summary

Turn the single-global-profile app into an invite-only, multi-tenant app where each
invited friend gets one **private workspace** (one user ↔ one workspace, per clarification)
holding their own profile (self/friend characters, main guild), conversations, tracked raids,
captured graphs, artifacts, and reports — fully isolated from every other user. The founder is
the sole platform administrator, bootstrapped by a CLI command; only they invite others. Because
there is no email provider in v1, invitation and password-reset **links are founder-mediated**
(the admin copies a link from the admin page and shares it), behind a delivery seam so automated
email can replace it later. Existing pre-accounts data is migrated into the founder's workspace.

The behavioral/security contract is `documentation/multi_tenancy_guide.md`. The implementation
follows it closely: global `users` keyed by `citext` email, `tenants` + `tenant_memberships`,
`invitations`, `sessions`, `password_reset_tokens`, `auth_audit_events`; Argon2id hashing via
`pwdlib`; opaque server-side sessions in a `__Host-` secure `HttpOnly` cookie; a CSRF header
validated per session; application-layer tenant scoping on **every** data path; and PostgreSQL
row-level security (RLS) as defense in depth under a non-privileged runtime role.

Work proceeds in seven methodical slices (Principle II), mapped to the spec's stories and the
guide's 16-step sequence:

1. **Foundation (enables all)** — adopt **Alembic** (the current startup `create_all`+`ALTER`
   cannot add non-null owner columns to existing tables, backfill, add FKs/indexes, or enable
   RLS). Baseline the existing schema, then add the auth/tenant tables. Build the token, password,
   and log-redaction utilities with unit tests; add transaction-scoped tenant context.
2. **US1 Invitations & activation (P1)** — admin creates an invitation (producing a shareable
   single-use link); the invitee accepts it, sets a first Argon2id password, gets a workspace
   auto-provisioned (one tenant + owner membership), and is signed in.
3. **US2 Sign-in / session / sign-out (P1)** — `/login`, `/me`, `/logout`; opaque session cookie
   + CSRF; shared auth dependency yielding a typed `RequestIdentity`; the chat WebSocket
   authenticates from the cookie on handshake and derives the tenant.
4. **US3 Tenant isolation (P1)** — thread `tenant_id` through **every** repository call, endpoint,
   the WS capture path, the WCL result cache key, and the ADK session `user_id`; migrate existing
   global rows into the founder's workspace; enable+force RLS on tenant-owned tables (Postgres).
5. **US4 Admin surface (P2)** — platform-admin-only user/invitation management endpoints + React
   admin page; copy-invite-link and trigger-reset actions; server-enforced on every call.
6. **US5 Password reset (P2)** — founder-triggered reset producing a shareable link; completing it
   rehashes the password and revokes all the user's sessions, behind the same delivery seam.
7. **Hardening** — progressive login throttling, the full audit-event set, log/APM redaction, and
   the cross-tenant/security test matrix.

Technical approach reuses the established backbone and keeps the agent package standalone:
`SessionLocal`/`get_session` and the `repository.py` helpers gain a required `tenant_id`; the
`ws._handle_turn`/`_handle_tool_end` path authenticates once and scopes all captures; the WCL
cache key (feature 005) gains the tenant prefix; `agent_runner` sets the ADK `user_id` to the
tenant so ADK's `DatabaseSessionService` state is isolated too. The frontend gains `react-router`
with public routes (`/login`, `/accept-invite`, `/reset-password`) and a guarded app shell, one
`AuthProvider` that calls `/api/auth/me`, and `credentials: 'include'` + `X-CSRF-Token` on all
calls. No JWTs; no credentials in `localStorage`; no raw tokens from admin APIs.

## Technical Context

**Language/Version**: Python **3.14** (backend, per `.python-version` + constitution); TypeScript 5.5;
React 19 (current).

**Primary Dependencies**:
- Backend (existing): FastAPI + asyncio, google-adk (Gemini/Anthropic via Vertex), SQLAlchemy[asyncio]
  + asyncpg, Pydantic / pydantic-settings, ReportLab + matplotlib, plotly, `requests` (WCL client).
- Backend (**new**): **`pwdlib[argon2]`** (Argon2id password hashing, per guide §Password hashing);
  **`alembic`** (schema migrations — required to alter existing tables, backfill owners, and enable
  RLS, which the current `create_all` path cannot do). No JWT library (sessions are opaque). No
  email dependency in v1 (link delivery is founder-mediated behind a seam). Rate limiting is
  in-process at current single-process scale (no Redis — recorded in Complexity Tracking).
- Frontend (existing): React 19 + Vite 5, Tailwind v4, streamdown, katex, react-plotly.js, motion.
- Frontend (**new**): **`react-router-dom`** (public auth routes vs. guarded app shell + admin page;
  the app currently has no router and renders a single `App`). Reuses `fetch` (no new HTTP client).

**Storage**: PostgreSQL (unchanged engine). **New tables**: `users`, `tenants`,
`tenant_memberships`, `invitations`, `sessions`, `password_reset_tokens`, `auth_audit_events`.
**Altered tables** (add non-null `tenant_id` + tenant-leading index, then RLS): `conversations`,
`messages`, `tracked_raids`, `captured_graphs`, `user_characters`, `guild_profile`, `artifacts`;
`user_characters`' uniqueness becomes per-tenant. **Alembic** replaces the `lifespan`
`create_all`+`ALTER` for schema changes going forward (a baseline migration captures today's
schema; a feature migration adds auth/tenant structures and backfills the founder's workspace).
ADK's own session tables (created by `DatabaseSessionService`) are isolated via the ADK `user_id`
= tenant id, not via RLS (they are outside our ORM models).

**Testing**: pytest + pytest-asyncio + httpx; models run on **SQLite** in tests (portable column
types). New backend tests: `test_passwords`, `test_tokens`, `test_redaction`, `test_tenant_context`,
`test_invitations`, `test_auth_login`, `test_sessions_csrf`, `test_tenant_isolation`,
`test_admin_users`, `test_password_reset`, `test_rate_limit`, `test_audit`, plus a Postgres-only
`test_rls` (skipped on SQLite). RLS and the real migration are exercised against Postgres in
`quickstart.md`. The two-user cross-tenant negative matrix (guide §Tenant-isolation tests) is the
gating suite for US3.

**Target Platform**: Linux server (containerized), same-site deployment (React + `/api` + `/ws`
behind one origin — already true via the Vite dev proxy and the compose topology), modern browsers.

**Project Type**: Web application — `backend/` (FastAPI), `frontend/` (React/Vite), `wcl_agent/`
(ADK agent package + CLI; stays standalone, no backend/DB import).

**Performance Goals**: authentication adds no perceptible latency to normal requests (session lookup
is one indexed query; `last_seen_at` is written at most every 5 min); Argon2id verification runs off
the event loop with bounded concurrency so hashing never stalls other requests; tenant scoping adds
only a `WHERE tenant_id = …` predicate (covered by tenant-leading indexes). A newly invited user
reaches a working workspace in under 5 minutes (SC-001).

**Constraints**: never block the asyncio event loop — Argon2id hash/verify via
`anyio.to_thread.run_sync` under a bounded semaphore (guide §Password hashing). Tenant identity is
**always** derived from the authenticated session + verified membership, never from client input
(FR-006). No plaintext passwords or raw/hashed tokens in DB columns intended for raw values, logs,
traces, audit metadata, exports, or error payloads (FR-002, FR-030). Secrets are
`secrets.token_bytes(32)`, URL-encoded unpadded base64url, stored only as `sha256` digests. The
`__Host-` cookie requires `Secure`+`Path=/`+no `Domain`. RLS uses transaction-local
`set_config('app.tenant_id', …, true)` on a **non-superuser, non-`BYPASSRLS`** runtime role; never
session-level `SET` on a pooled connection. SQLite tests skip RLS and validate app-level scoping.
The `wcl_agent` package must not import backend/DB code.

**Scale/Scope**: a founder plus a handful of invited friends; one process, low concurrency;
multiple sessions per user permitted (guide §Login). One workspace per user in v1.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| I. Strict DRY & Reuse-First | PASS — one shared auth **dependency** produces the single `RequestIdentity` consumed by every protected route and the WS; one `tenant_id` keyword threads through the existing `repository.py` (extended, not duplicated); one token-hash/secret helper serves invitations, resets, sessions, and CSRF; one tenant-context helper wraps every protected transaction; link delivery is one seam (dev copy-link now, email later). Reuses `SessionLocal`/`get_session`, the `ws` capture backbone, the feature-005 cache chokepoint, and the existing profile/conversation/raid repos rather than forking them. |
| II. Methodical, Step-Wise Delivery | PASS — seven independently verifiable slices (foundation → invitations → login → isolation → admin → reset → hardening); each leaves the app working. Backend auth is testable (httpx) before the React auth UI exists; the cross-tenant matrix gates US3 before RLS is layered on. |
| III. Simplicity First (YAGNI) — NON-NEGOTIABLE | **PASS WITH JUSTIFICATION** — five additions are justified in Complexity Tracking: **Alembic** (unavoidable — `create_all` cannot alter/backfill/secure existing tables), **`pwdlib[argon2]`** (the guide's mandated hasher; hand-rolling crypto is a defect), **`react-router-dom`** (public vs. guarded routes the single-`App` shell can't express cleanly), **retaining `tenants`+`tenant_memberships`** even though v1 is 1:1 (matches the guide's RLS/`app.tenant_id` contract and the spec's "don't preclude multi-member later"; avoids a second painful migration), and **RLS + a separate runtime DB role** (defense-in-depth the guide requires; FR-020). Deliberately *omitted* for simplicity: Redis/edge rate limiting (in-process at single-process scale), an email provider (founder-mediated links), MFA/SSO, tenant-switching UI, and a generic authz framework. |
| IV. Typed Data Contracts | PASS — new Pydantic schemas for every boundary (`LoginIn`, `AcceptInvitationIn`, `ForgotPasswordIn`, `ResetPasswordIn`, `MeOut`, `InvitationIn/Out`, `AdminUserOut`, `MembershipIn`, error envelope) and a frozen `RequestIdentity` dataclass for the in-process security context; repository scope is a keyword-only `tenant_id: UUID`. No untyped dicts cross a layer. |
| V. Async Python Backend | PASS — all new endpoints are `async`; Argon2id hash/verify is offloaded via `anyio.to_thread.run_sync` under a bounded semaphore so it never blocks the loop; session/CSRF checks are single indexed async queries; tenant context is set transaction-locally on the existing async session. |
| VI. Repo Awareness via GitNexus | PASS (process) — run `gitnexus_impact` before editing the high-blast-radius symbols: every `repository.py` function (adding `tenant_id`), `ws._handle_turn`/`_handle_tool_end`, `agent_runner.stream_response`/`_ensure_session`/`_get_runner`, `main.lifespan`, `db.session.get_session`, `WCLClient.query` cache key, and each existing router. Run `gitnexus_detect_changes` before each slice's commit to confirm scope. |

**Result**: PASS (Phase 0 gate) — Principle III justified in Complexity Tracking. Re-checked post-design (below) — still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/006-multi-tenancy/
├── plan.md              # This file
├── research.md          # Phase 0 output (R1–R9 decisions)
├── data-model.md        # Phase 1 output (new/altered tables, migration phases, RLS)
├── quickstart.md        # Phase 1 output (bootstrap, migration, per-story + 2-user isolation checks)
├── contracts/
│   ├── auth-api.md      # login, logout, me, accept-invitation, forgot/reset password
│   ├── admin-api.md     # users + invitations (platform-admin only); membership mgmt deferred (1:1 v1)
│   ├── websocket.md     # authenticated /ws/chat handshake (cookie + origin), tenant derivation
│   └── tenant-scoping.md# repository/cache/ADK/RLS scoping contract + error-status matrix
├── checklists/
│   └── requirements.md  # spec quality checklist (complete)
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
backend/
├── alembic.ini                  # [new] Alembic config (async engine URL from settings)
├── migrations/                  # [new] Alembic env + versions
│   ├── env.py                   # [new] async env; migration-owner role; imports Base.metadata
│   └── versions/
│       ├── 0001_baseline.py     # [new] current schema snapshot (conversations…artifacts + ADK tables left to ADK)
│       ├── 0002_auth_tenancy.py # [new] users/tenants/memberships/invitations/sessions/reset/audit
│       ├── 0003_tenant_columns.py # [new] add tenant_id (nullable→backfill→not null) + indexes + per-tenant uniqueness
│       └── 0004_rls.py          # [new] enable+force RLS + policies + runtime role grants (Postgres only)
├── app/
│   ├── auth/                    # [new] authentication building blocks (guide §FastAPI structure)
│   │   ├── passwords.py         # Argon2id hash/verify via pwdlib, off-loop + bounded, policy check
│   │   ├── tokens.py            # CSPRNG secret, base64url encode, sha256 digest, constant-time compare
│   │   ├── sessions.py          # create/lookup/revoke sessions; cookie attrs; idle/absolute expiry
│   │   ├── csrf.py              # CSRF token issue/verify; origin/referer validation
│   │   ├── dependencies.py      # require_session → RequestIdentity; require_platform_admin; CSRF guard
│   │   └── rate_limit.py        # in-process progressive login throttle (per account + source)
│   ├── tenancy/                 # [new]
│   │   ├── context.py           # transaction-local set_config('app.tenant_id'/'app.user_id'); RequestIdentity
│   │   └── authorization.py     # helpers to assert tenant scope / 404-on-foreign-resource
│   ├── api/
│   │   ├── auth.py              # [new] /api/auth/* (login, logout, me, accept-invitation, forgot/reset)
│   │   ├── admin_users.py       # [new] /api/admin/* (users, invitations) — platform-admin (membership routes deferred)
│   │   ├── conversations.py     # [edit] require session; scope all repo calls by tenant
│   │   ├── reports.py           # [edit] scope conversation lookup by tenant
│   │   ├── raids.py             # [edit] scope raids by tenant
│   │   ├── profile.py           # [edit] scope profile by tenant
│   │   ├── greeting.py / models.py # [edit] require session (greeting/models stay per-user-safe)
│   │   └── ws.py                # [edit] authenticate handshake (cookie + origin); derive tenant; scope captures
│   ├── services/
│   │   ├── auth_service.py      # [new] login/logout/switch workflows + audit
│   │   ├── invitation_service.py# [new] create/resend/revoke + accept (tenant auto-provision) in one txn
│   │   ├── password_reset_service.py # [new] request/complete reset; revoke sessions
│   │   └── link_delivery.py     # [new] delivery seam: v1 returns the link to the admin (no email)
│   ├── repositories/            # [new] auth/tenant data access (users, tenants, memberships,
│   │                            #       invitations, sessions, reset tokens, audit)
│   ├── db/
│   │   ├── models.py            # [edit] + User/Tenant/Membership/Invitation/Session/ResetToken/AuditEvent;
│   │   │                        #        add tenant_id to the 7 tenant-owned tables; per-tenant uniqueness
│   │   ├── repository.py        # [edit] every tenant-owned function gains keyword-only tenant_id
│   │   └── session.py           # [edit] helper to open a tenant-scoped transaction (sets app.tenant_id)
│   ├── agent_runner.py          # [edit] ADK user_id = tenant id (isolate DatabaseSessionService state)
│   ├── schemas.py               # [edit] + auth/admin request/response models + error envelope
│   ├── config.py                # [edit] + cookie/session/token/rate-limit settings; runtime vs owner DB URL; canonical site URL
│   └── main.py                  # [edit] drop create_all for altered tables (Alembic owns schema);
│                                #        mount auth/admin routers; RLS runtime role; startup checks
├── cli/
│   └── bootstrap_admin.py       # [new] controlled first-platform-admin creation (no public endpoint)
└── tests/                       # [new auth/tenant suites above] + [edit] existing tests to sign in first

frontend/
├── package.json                 # [edit] + react-router-dom
├── src/
│   ├── main.tsx                 # [edit] wrap <App/> in router + <AuthProvider/>
│   ├── auth/
│   │   ├── AuthProvider.tsx     # [new] calls /api/auth/me; holds identity + in-memory CSRF token; clears on 401
│   │   ├── RequireAuth.tsx      # [new] guards /app/* and /admin (UX only; server is authority)
│   │   └── useAuth.ts           # [new] hook
│   ├── pages/
│   │   ├── LoginPage.tsx        # [new] email + password
│   │   ├── AcceptInvitePage.tsx # [new] reads #token from fragment, strips it, sets first password
│   │   ├── ResetPasswordPage.tsx# [new] reads #token, sets new password
│   │   ├── AdminUsersPage.tsx   # [new] users + invitations; copy-link + resend/revoke + disable/enable
│   │   └── ForbiddenPage.tsx    # [new]
│   ├── App.tsx                  # [edit] the authenticated chat shell (unchanged chat behavior, now per-user)
│   ├── api/
│   │   ├── restClient.ts        # [edit] credentials:'include' + X-CSRF-Token on unsafe calls; auth/admin calls
│   │   └── wsClient.ts          # [edit] rely on same-origin cookie; reconnect/close on auth loss
│   └── types.ts                 # [edit] + Identity, Membership, AdminUser, Invitation types
└── (routes mirror the guide: /login /accept-invite /forgot-password /reset-password /app/* /admin/users /forbidden)
```

**Structure Decision**: The existing three-package layout is retained. Authentication concerns live
in new `backend/app/auth/` and `backend/app/tenancy/` packages (clear boundaries, per guide
§FastAPI structure) rather than being embedded in routers. Schema ownership moves from the
`lifespan` `create_all`+`ALTER` to **Alembic**; `create_all` is retained only for the SQLite test
fixtures (which build `Base.metadata` directly and skip Postgres-only RLS). `wcl_agent` stays
standalone — the WCL cache key simply accepts a tenant prefix from the caller, with no DB coupling.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| **Adopt Alembic** (new migration tool + `migrations/` tree) | This feature must add non-null `tenant_id` to 7 populated tables, backfill them, add FKs/indexes/per-tenant uniqueness, and enable RLS — none of which the startup `create_all` (new-tables-only) or ad-hoc `ALTER … IF NOT EXISTS` can do safely or reversibly (FR-031). | Continuing with hand-written idempotent `ALTER`s cannot do phased nullable→backfill→not-null, cannot manage RLS/role grants reversibly, and leaves no migration history before a security-critical data move. Alembic is the standard, is reversible, and coexists with the SQLite test fixtures (which keep `create_all`). |
| **`pwdlib[argon2]` dependency** | Store passwords only as Argon2id hashes with vetted parameters, with rehash-on-login support (guide §Password hashing, security invariant 4). | Hand-constructing salts/KDF parameters is exactly the defect the guide forbids; `pwdlib.PasswordHash.recommended()` is the FastAPI-recommended, maintained choice. |
| **`react-router-dom` dependency** | Public unauthenticated routes (`/login`, `/accept-invite`, `/reset-password`) must be cleanly separated from the guarded app shell and the admin-only page, with fragment-token routes (guide §React routes). | The current single-`App` conditional render cannot express public-vs-guarded routing, deep links to invite/reset pages, or `/admin/users` without an ad-hoc hand-rolled router — more code and more bugs than the standard library. |
| **Retain `tenants` + `tenant_memberships` tables (v1 is 1:1)** | Matches the guide's data model and its RLS policies/`app.tenant_id` context verbatim, and satisfies the spec's "membership model MUST NOT preclude multi-member later" (FR-005) without a future table-adding migration. | Scoping directly by `user_id` and dropping the tenant tables would make every RLS policy and the whole guide diverge, and would force a painful re-tenanting migration the first time a shared workspace is wanted (YAGNI cuts the *UI/flows*, not the isolation column). |
| **PostgreSQL RLS + separate non-privileged runtime DB role** | Defense in depth so a missing application `WHERE tenant_id` predicate still cannot cross tenants (FR-020; guide §RLS, invariant 9–10). | App-level scoping alone is a single point of failure for the feature's worst-case risk (cross-tenant data exposure). RLS is cheap insurance; it is Postgres-only and guarded so SQLite tests are unaffected. |
| **In-process rate limiting (no Redis)** *(simplification, noted for honesty)* | Progressive login throttling per account+source at the current single-process scale needs no shared store; the guide permits this and flags the multi-worker caveat. | Adding Redis now is speculative infra for a single-process friends deployment (YAGNI); the limiter sits behind an interface so a shared backend can replace it when the app scales to multiple workers — logged as a known limit, not hidden. |

## Post-Design Constitution Re-Check

Re-evaluated after Phase 1 (data-model, contracts): **still PASS.** One auth dependency and one
`tenant_id` keyword are the single sources of truth for identity and scope; the tenant tables,
RLS, and `app.tenant_id` context match the grounding guide exactly; all boundary data is typed;
Argon2id and all I/O stay off/according to the event loop; schema changes are reversible Alembic
migrations with a guarded, phased backfill that assigns existing data to the founder. Principle III
deviations are confined to the Complexity Tracking table, each tied to a concrete present
requirement (not speculation), with the deliberately-omitted scope (email, Redis, MFA, switching)
recorded so nothing is silently dropped.
