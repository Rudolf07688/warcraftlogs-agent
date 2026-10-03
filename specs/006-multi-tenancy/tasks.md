---
description: "Task list for Multi-Tenancy — Invite-Only Accounts & Private Per-User Workspaces"
---

# Tasks: Multi-Tenancy — Invite-Only Accounts & Private Per-User Workspaces

**Input**: Design documents from `/specs/006-multi-tenancy/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — the spec and `documentation/multi_tenancy_guide.md` specify an explicit test
matrix, and the two-tenant isolation suite **gates US3**. Write each story's tests first and ensure
they fail before implementing.

**Organization**: Grouped by user story (US1–US5) for independent implementation and testing.
US6 (tenant-switching) is out of scope for v1 (one workspace per user).

**Constitution note (Principle VI)**: Before editing a high-blast-radius existing symbol
(`db/repository.py` functions, `api/ws.py`, `agent_runner.stream_response`/`_ensure_session`,
`main.lifespan`, each existing router), run `gitnexus_impact({target, direction:"upstream"})` first;
run `gitnexus_detect_changes()` before each commit. Tasks that touch these are marked **⚠️impact**.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US5; Setup/Foundational/Polish tasks carry no story label

## Path Conventions

Web app: `backend/` (FastAPI, `backend/app/…`, tests `backend/tests/…`), `frontend/src/…`,
`wcl_agent/` (standalone agent package). Migrations in `backend/migrations/versions/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencies, configuration, migration tooling, and the delivery seam.

- [X] T001 Add backend deps `pwdlib[argon2]` and `alembic` to `pyproject.toml` `[project.dependencies]`; run `uv sync`
- [X] T002 [P] Add `react-router-dom` to `frontend/package.json` dependencies; run the frontend install
- [X] T003 Initialize Alembic: create `backend/alembic.ini` and `backend/migrations/env.py` (async engine; target `backend.app.db.models.Base.metadata`; use the **owner** DB URL from settings; do not autogenerate against ADK tables)
- [X] T004 [P] Extend `backend/app/config.py` with settings: cookie name/attrs, session idle + absolute lifetimes, invitation + reset lifetimes, token entropy, password min/max, rate-limit thresholds, canonical site URL, and separate `database_url` (runtime) + `database_owner_url` (migrations) — all env-driven with guide defaults
- [X] T005 [P] Add a non-superuser **runtime** role and a **migration-owner** role to `docker-compose.yml` and `.env.example`, with comments documenting the bootstrap/migration order (research R4/R8)
- [X] T006 [P] Create the delivery seam `backend/app/services/link_delivery.py`: build canonical HTTPS links from trusted config (token in URL fragment, never the `Host` header) and return the link to the caller; v1 performs no email (research R9)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Auth/tenant data model, migrations for new tables, security primitives, repositories, the
shared auth dependency, bootstrap, and the test harness. **No user story can begin until this is done.**

**⚠️ CRITICAL**: Blocks all user stories.

- [X] T007 Add auth/tenant ORM models to `backend/app/db/models.py`: `User`, `Tenant`, `TenantMembership`, `Invitation`, `Session`, `PasswordResetToken`, `AuthAuditEvent` (portable column types; `citext`/plain-lowercase email fallback) per `data-model.md`
- [X] T008 Create Alembic baseline migration `backend/migrations/versions/0001_baseline.py` capturing the **current** schema (conversations, messages, tracked_raids, captured_graphs, user_characters, guild_profile, artifacts) so history starts from a known point
- [X] T009 Create migration `backend/migrations/versions/0002_auth_tenancy.py` adding the seven new tables + `citext` extension + the `uq_open_invitation` partial unique index + the `ix_sessions_user_active` index (depends on T007, T008)
- [X] T010 [P] Implement `backend/app/auth/passwords.py` (Argon2id hash/verify via `pwdlib.recommended()` offloaded with `anyio.to_thread.run_sync` under a bounded semaphore; policy validation; process-level dummy hash) and `backend/tests/test_passwords.py`
- [X] T011 [P] Implement `backend/app/auth/tokens.py` (CSPRNG `secrets.token_bytes(32)`, unpadded base64url encode, `sha256` digest, constant-time compare) and `backend/tests/test_tokens.py`
- [X] T012 [P] Implement a log-redaction helper `backend/app/auth/redaction.py` (strip keys matching `password|token|authorization|cookie|set-cookie|csrf`) and `backend/tests/test_redaction.py`
- [X] T013 [P] Implement `backend/app/tenancy/context.py` (frozen `RequestIdentity` dataclass; `tenant_session(identity)` opening a transaction and running transaction-local `set_config('app.tenant_id'/'app.user_id', …, true)`; no-op on SQLite) and `backend/tests/test_tenant_context.py`
- [X] T014 Implement `backend/app/auth/sessions.py` (create/lookup/revoke sessions; cookie attribute helper; idle + absolute expiry; `last_seen_at` throttled write) (depends on T011)
- [X] T015 Implement `backend/app/auth/csrf.py` (issue/verify CSRF against session digest; `Origin`/`Referer` validation) (depends on T011)
- [X] T016 Implement `backend/app/auth/dependencies.py`: `require_session` → `RequestIdentity`, `require_platform_admin`, and the CSRF guard for unsafe methods (depends on T013, T014, T015)
- [X] T017 [P] Implement `backend/app/auth/rate_limit.py` (in-process progressive limiter behind an interface, keyed by account + source) (research R7)
- [X] T018 [P] Implement auth/tenant data access under `backend/app/repositories/` (users, tenants, memberships, invitations, sessions, reset tokens, and the append-only audit writer) per `data-model.md` (depends on T007)
- [X] T019 Add auth/admin Pydantic schemas + the `{error:{code,message,request_id}}` envelope to `backend/app/schemas.py` (`LoginIn`, `AcceptInvitationIn`, `ForgotPasswordIn`, `ResetPasswordIn`, `MeOut`, `InvitationIn/Out`, `AdminUserOut`, `MembershipIn`)
- [X] T020 Implement the founder bootstrap CLI `backend/cli/bootstrap_admin.py` (create platform-admin user + auto-provisioned tenant + owner membership; **no HTTP path**) (depends on T007, T010, T018)
- [X] T021 Add shared test fixtures `as_user` and `as_admin` to `backend/tests/conftest.py` (provision user + tenant + membership + session cookie + CSRF for authenticated endpoint tests) (depends on T014, T018)

**Checkpoint**: Auth primitives, schema for new tables, bootstrap, and the test harness exist.

---

## Phase 3: User Story 1 - Invite a friend and activate their account (Priority: P1) 🎯 MVP

**Goal**: The founder creates an invitation (shareable single-use link); the invitee accepts it, sets
a first password, gets a workspace auto-provisioned, and is signed in. No public sign-up.

**Independent Test**: Create an invitation as the founder, copy the link, open it as the invitee, set a
password, land signed-in in an empty workspace; confirm email-without-link and reused/expired links
all fail generically.

### Tests for User Story 1

- [X] T022 [P] [US1] `backend/tests/test_invitations.py`: create invitation; accept (activates user + auto-provisions tenant + owner membership + session); concurrent acceptance → exactly one success; expired/revoked/used/garbage token → generic `400`; disabled user/tenant rejected; email-without-token cannot claim

### Implementation for User Story 1

- [X] T023 [US1] Implement `backend/app/services/invitation_service.py`: `create`/`resend`/`revoke` (store token digest only, 24h expiry) and the single-transaction `accept` (validate token, two-phase off-loop hash, activate user, auto-provision tenant + owner membership, create session, write `invitation.*` + `session.created` audit) (depends on Phase 2)
- [X] T024 [US1] Add `POST /api/admin/invitations` (create) to `backend/app/api/admin_users.py` guarded by `require_platform_admin` + CSRF; return `InvitationOut` with `invite_link` **once** (depends on T023)
- [X] T025 [US1] Add `POST /api/auth/accept-invitation` to `backend/app/api/auth.py` (public, rate limited); set `__Host-session` cookie, return `MeOut` (depends on T023); register both routers in `backend/app/main.py`
- [X] T026 [P] [US1] Create `frontend/src/pages/AcceptInvitePage.tsx`: read `#token` from the fragment, immediately `history.replaceState` it away, keep in memory, collect password + confirmation, submit; apply `Referrer-Policy: no-referrer`
- [X] T027 [US1] Add `acceptInvitation()` and `createInvitation()` to `frontend/src/api/restClient.ts` (JSON, credentials, CSRF on the admin create)

**Checkpoint**: A second real person can be invited and reach their own empty workspace.

---

## Phase 4: User Story 2 - Sign in, stay signed in, sign out (Priority: P1)

**Goal**: Activated users sign in (email+password), persist via a secure server-side session, and sign
out; the chat WebSocket requires an authenticated session.

**Independent Test**: Sign in with correct creds (reach the app), wrong/unknown/disabled → identical
generic error, reload stays signed in, sign out invalidates the session; cookie is `Secure/HttpOnly/
SameSite=Lax/host-only`; no token in browser storage.

### Tests for User Story 2

- [X] T028 [P] [US2] `backend/tests/test_auth_login.py` and `backend/tests/test_sessions_csrf.py`: generic `401` for unknown/wrong/disabled (+ dummy-hash timing path); session cookie attributes; `/me` shape; logout revokes + idempotent; idle + absolute expiry; unsafe request without CSRF/allowed origin → `403`

### Implementation for User Story 2

- [X] T029 [US2] Implement `backend/app/services/auth_service.py` (login: dummy-hash on unknown email, reset counters, set single tenant active, rotate session+CSRF, `last_login_at`, audit; logout: revoke + clear) wired to the login throttle from T017 (depends on Phase 2)
- [X] T030 [US2] Add `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` to `backend/app/api/auth.py` (depends on T029)
- [X] T031 [US2] ⚠️impact Authenticate the `/ws/chat` handshake in `backend/app/api/ws.py`: validate the `__Host-session` cookie + `Origin` before `accept()`, bind `RequestIdentity` to the socket, reject on failure (depends on T016)
- [X] T032 [US2] ⚠️impact Thread an identity/`user_id` parameter through `backend/app/agent_runner.py` call sites so the runner no longer hardcodes `USER_ID` (tenant value wired in US3)
- [X] T033 [P] [US2] Create `frontend/src/auth/AuthProvider.tsx` + `frontend/src/auth/useAuth.ts`: call `/api/auth/me` on bootstrap, hold identity + in-memory CSRF token, clear on `401`, expose login/logout
- [X] T034 [P] [US2] Create `frontend/src/auth/RequireAuth.tsx` guarding `/app/*` (redirect unauthenticated to `/login`)
- [X] T035 [US2] Add the router to `frontend/src/main.tsx` (public `/login`, `/accept-invite`, `/reset-password`; guarded `/app/*`) and create `frontend/src/pages/LoginPage.tsx` (semantic autocomplete fields, show/hide, generic errors, no-double-submit)
- [X] T036 [US2] Update `frontend/src/api/restClient.ts` (all calls `credentials:'include'`, `X-CSRF-Token` on unsafe) and `frontend/src/api/wsClient.ts` (rely on same-origin cookie; close/reconnect on auth loss); add `login`/`logout`/`getMe`

**Checkpoint**: Users authenticate and the app shell + chat require a session.

---

## Phase 5: User Story 3 - Each user's data is private and isolated (Priority: P1) 🔒 GATING

**Goal**: Thread `tenant_id` through every data path, migrate existing data to the founder, and enable
RLS so no user can reach another's data.

**Independent Test**: Two users each with look-alike data; user A cannot read/list/mutate B's
conversations/messages/raids/graphs/artifacts/profile/reports by any means (guessed ids, injected ids,
cache, ADK state); all foreign access returns `404`; RLS blocks cross-tenant access even with the app
predicate removed.

### Tests for User Story 3 (gating)

- [ ] T037 [P] [US3] `backend/tests/test_tenant_isolation.py` (the two-tenant matrix from `contracts/tenant-scoping.md`: reads/lists/counts/search/export/update/delete, id-guessing → 404, injected ids ignored, cache + ADK isolation, disable/revoke stops in-flight socket) and Postgres-only `backend/tests/test_rls.py` (skipped on SQLite)

### Implementation for User Story 3

- [ ] T038 [US3] Add `tenant_id` columns (+ per-tenant uniqueness changes) to the 7 tenant-owned models in `backend/app/db/models.py` per `data-model.md` (depends on T007)
- [ ] T039 [US3] Create migration `backend/migrations/versions/0003_tenant_columns.py`: for each of the 7 tables add nullable `tenant_id` → **backfill to the founder tenant** → validate no NULLs → set `NOT NULL` + add tenant-leading index + per-tenant unique constraints; fail loudly if no platform admin exists (depends on T038, T020)
- [ ] T040 [US3] Create migration `backend/migrations/versions/0004_rls.py`: `ENABLE`+`FORCE` RLS, tenant policies, and runtime-role grants on the 7 tables (Postgres only) (depends on T039)
- [ ] T041 [US3] ⚠️impact Thread keyword-only `tenant_id: UUID` through **every** tenant-owned function in `backend/app/db/repository.py` (include it in all `WHERE`/`INSERT`; child rows inherit parent tenant) per `contracts/tenant-scoping.md`
- [ ] T042 [US3] ⚠️impact Require session + scope all repo calls by tenant in `backend/app/api/conversations.py` (foreign/absent `{id}` → `404`) (depends on T016, T041)
- [ ] T043 [P] [US3] Require session + tenant scope in `backend/app/api/reports.py` (conversation + captures scoped; foreign → `404`) (depends on T016, T041)
- [ ] T044 [P] [US3] Require session + tenant scope in `backend/app/api/raids.py` (raids scoped; investigate creates a tenant-owned conversation) (depends on T016, T041)
- [ ] T045 [P] [US3] Require session + tenant scope in `backend/app/api/profile.py` (all profile rows scoped) (depends on T016, T041)
- [ ] T046 [P] [US3] Require session in `backend/app/api/greeting.py` and `backend/app/api/models.py` (no anonymous access) (depends on T016)
- [ ] T047 [US3] ⚠️impact Per-turn tenant scoping in `backend/app/api/ws.py`: assert conversation ownership, create conversations with the socket tenant, wrap work in `tenant_session`, pass `tenant_id` to every capture call, re-validate session each turn (depends on T031, T041)
- [ ] T048 [US3] ⚠️impact Set ADK `user_id = str(tenant_id)` in `backend/app/agent_runner.py` (`_ensure_session`/`run_async`) so `DatabaseSessionService` state is tenant-isolated (depends on T032, T047)
- [ ] T049 [US3] Prefix the WCL result cache key with `tenant_id` in `wcl_agent/cache.py` (accept a caller-supplied prefix; no DB import) and pass it from the backend tool path
- [ ] T050 [US3] Run background spec-guide/guild-summary tasks inside a `tenant_session` scope in `backend/app/services/guide.py` (and guild summary) so derived context is tenant-scoped
- [ ] T051 [US3] ⚠️impact Remove the altered-table `create_all`/`ALTER … IF NOT EXISTS` block from `backend/app/main.lifespan`; make Alembic the schema authority (keep `create_all` only in the SQLite test fixtures) (depends on T039, T040)
- [ ] T051a [US3] Migrate the existing backend test suite to the authenticated, tenant-scoped contracts: update `backend/tests/{test_api,test_profile,test_raids,test_reports,test_artifacts,test_message_report,test_persistence,test_guide}.py` to use the `as_user`/`as_admin` fixtures (T021), pass the required keyword-only `tenant_id` to every `repo.*` call, and sign in before hitting now-session-guarded endpoints. Add assertions that pre-existing behavior is unchanged for a single tenant (FR-032 no-regression) (depends on T021, T038, T041, T042–T047)

**Checkpoint**: The gating isolation matrix (T037) passes; RLS enforced on Postgres; the full existing suite is green under auth + tenant scoping (FR-032).

---

## Phase 6: User Story 4 - Founder manages users and invitations (Priority: P2)

**Goal**: Platform-admin-only page + endpoints to list users/invitations and resend/revoke/disable/
enable; refused for non-admins server-side.

**Independent Test**: As founder, list users + pending invitations, resend/revoke an invitation,
disable then re-enable a user; as an ordinary user, the page is hidden and every `/api/admin/*` call
returns `403`; no view shows hashes/tokens.

### Tests for User Story 4

- [ ] T052 [P] [US4] `backend/tests/test_admin_users.py`: every admin endpoint returns `403` for non-admin (called directly); list users/invitations; resend invalidates prior link; revoke disables link; disable revokes sessions + blocks sign-in, enable restores; responses never contain hashes/raw tokens

### Implementation for User Story 4

- [ ] T053 [US4] Add the remaining admin endpoints to `backend/app/api/admin_users.py`: `GET /users` (paginated), `GET /invitations`, `POST /invitations/{id}/resend`, `DELETE /invitations/{id}`, and `PATCH /users/{id}` (disable/enable + revoke sessions; cannot disable last admin) — all `require_platform_admin` + CSRF (depends on T023, T018). **Membership add/change/remove endpoints are deferred** (not built in v1; one workspace per user — Simplicity-First). The `tenant_memberships` table and `MembershipIn` schema remain so they can be added without rework.
- [ ] T054 [P] [US4] Create `frontend/src/pages/AdminUsersPage.tsx`: users table (email/status/last-login/memberships), pending invitations, create-invite form with copy-link, resend/revoke, disable/enable with confirmation, clear feedback; never render secrets
- [ ] T055 [P] [US4] Create `frontend/src/pages/ForbiddenPage.tsx` and guard `/admin/users` in the router/`RequireAuth` to render only when `is_platform_admin`
- [ ] T056 [US4] Add admin REST calls to `frontend/src/api/restClient.ts` and admin types (`AdminUser`, `Invitation`, `Membership`) to `frontend/src/types.ts`

**Checkpoint**: Founder can run the invite-only deployment; admin surface is server-enforced.

---

## Phase 7: User Story 5 - Founder-triggered password reset (Priority: P2)

**Goal**: Founder triggers a reset producing a shareable single-use link; completing it rehashes the
password and revokes all the user's sessions. Founder never sees/sets the password.

**Independent Test**: Founder triggers a reset and copies the link; user follows it, sets a new
password, all prior sessions end, sign-in works with the new password; expired/used links fail
generically.

### Tests for User Story 5

- [ ] T057 [P] [US5] `backend/tests/test_password_reset.py`: trigger → shareable link; complete → hash updated + all sessions revoked + no new session; expired/used/garbage → generic `400`; founder cannot view/set the password; deferred `/forgot-password` always returns neutral `202`

### Implementation for User Story 5

- [ ] T058 [US5] Implement `backend/app/services/password_reset_service.py` (request: single-use token digest + expiry + audit; complete: validate/consume, update Argon2id hash + `password_changed_at`, revoke all user sessions, audit) (depends on Phase 2)
- [ ] T059 [US5] Add `POST /api/admin/users/{id}/reset` (admin, returns `reset_link` once) to `backend/app/api/admin_users.py`, and `POST /api/auth/reset-password` + the deferred neutral `POST /api/auth/forgot-password` to `backend/app/api/auth.py` (depends on T058)
- [ ] T060 [P] [US5] Create `frontend/src/pages/ResetPasswordPage.tsx` (read `#token` + strip, set new password + confirmation, then route to `/login`)
- [ ] T061 [US5] Add `resetPassword()` + admin `triggerReset()` to `frontend/src/api/restClient.ts` and surface the reset-link copy action in `AdminUsersPage.tsx`

**Checkpoint**: Account recovery works end-to-end without exposing passwords.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Abuse controls, auditing, redaction, docs, and full-system verification.

- [ ] T062 [P] Apply rate limits to the token + admin-invitation endpoints and verify progressive login throttling in `backend/tests/test_rate_limit.py` (no known/unknown distinction; capped, non-permanent)
- [ ] T063 [P] Verify the full audit-event set (login/logout, invitation created/resent/revoked/accepted, reset requested/completed, user enabled/disabled, membership changes, admin authz failures) in `backend/tests/test_audit.py`, asserting no secrets in metadata
- [ ] T064 [P] Wire the redaction filter into app logging and review APM/exception middleware so raw secrets never reach logs/traces (`backend/app/main.py` + logging config)
- [ ] T065 [P] Update `.env.example`, `README.md`, and `documentation/ai_guide.md` with the runtime/owner roles, bootstrap CLI, `alembic upgrade head`, and auth/tenancy operational notes
- [ ] T066 Run migrations + bootstrap on Postgres and execute `specs/006-multi-tenancy/quickstart.md` (all 5 stories + isolation + regression)
- [ ] T067 Run the full backend + cross-tenant/RLS test suite and `/speckit-analyze`; address any spec↔plan↔contracts drift; run `gitnexus_detect_changes()` before the final commit

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)**: no dependencies.
- **Foundational (P2)**: depends on Setup — **blocks all user stories**.
- **US1 (P3)**: depends on Foundational.
- **US2 (P4)**: depends on Foundational (independent of US1).
- **US3 (P5)**: depends on Foundational; best after US2 (needs `require_session` + WS auth to scope). **Gating** — its isolation matrix must pass before the feature is shippable.
- **US4 (P6)**: depends on Foundational + US1 (reuses `invitation_service`) + US2 (admin auth).
- **US5 (P7)**: depends on Foundational + US2.
- **Polish (P8)**: depends on all desired stories.

### Critical path

Setup → Foundational → US1 (MVP) → US2 → **US3 (gating)** → US4 → US5 → Polish.

### Within a story

Tests (write first, fail) → migrations/models → services → endpoints → frontend → integration.

### Parallel opportunities

- Setup: T002, T004, T005, T006 in parallel (T001/T003 touch deps/alembic first).
- Foundational: T010, T011, T012, T013, T017, T018 in parallel; then T014/T015 → T016; T019/T020/T021 after their deps.
- US3 endpoint scoping: T043, T044, T045, T046 in parallel (distinct router files) after T041.
- Frontend pages across stories (T026, T033/T034, T054/T055, T060) are largely parallel (distinct files).
- Each story's test task ([P]) is written first, in parallel with its siblings.

---

## Parallel Example: Foundational primitives

```bash
Task: "Implement backend/app/auth/passwords.py + test_passwords.py"      # T010
Task: "Implement backend/app/auth/tokens.py + test_tokens.py"            # T011
Task: "Implement backend/app/auth/redaction.py + test_redaction.py"      # T012
Task: "Implement backend/app/tenancy/context.py + test_tenant_context.py"# T013
Task: "Implement backend/app/auth/rate_limit.py"                         # T017
Task: "Implement backend/app/repositories/ (auth+tenant data access)"    # T018
```

---

## Implementation Strategy

### MVP First

1. Setup + Foundational.
2. US1 → **STOP & validate**: invite a second person who reaches their own empty workspace.
3. US2 → sign-in/session/logout working.

### Gating isolation

4. US3 is the security core — do not ship multi-user until the T037 two-tenant matrix + RLS pass.

### Incremental delivery

5. US4 (admin), then US5 (reset), then Polish (rate limiting, audit, redaction, docs, quickstart).

---

## Notes

- `[P]` = different files, no incomplete dependencies.
- Never accept tenant/user id, role, or `is_admin` from client input — only from `RequestIdentity`.
- No JWTs, no credentials/CSRF token in `localStorage`, no raw tokens from admin list views.
- Keep `wcl_agent` standalone (no backend/DB import) — the cache takes a tenant prefix from the caller.
- Commit after each task or logical group; run `gitnexus_detect_changes()` before committing ⚠️impact edits.
