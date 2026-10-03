# Phase 0 Research: Multi-Tenancy

Decisions that resolve the plan's unknowns. Each: **Decision / Rationale / Alternatives**. The
`documentation/multi_tenancy_guide.md` is the governing contract; where it is prescriptive we adopt
it and record only the app-specific adaptation.

---

## R1 — Schema migrations (adopt Alembic)

**Decision**: Introduce **Alembic** as the schema authority for this feature and onward. Four
versions: `0001_baseline` (snapshot of today's tables so history starts from a known point),
`0002_auth_tenancy` (new auth/tenant tables), `0003_tenant_columns` (phased `tenant_id` add +
backfill + indexes + per-tenant uniqueness), `0004_rls` (enable/force RLS, policies, runtime-role
grants — Postgres only). The `lifespan` `create_all`+`ALTER … IF NOT EXISTS` block is removed for
production; `create_all` remains **only** in the SQLite test fixtures (which build `Base.metadata`
directly). Alembic uses the async engine; `env.py` runs under the **migration-owner** role (table
owner), distinct from the runtime role (R4). The ADK `DatabaseSessionService` tables continue to be
created by ADK's `prepare_tables()` — Alembic does not manage them.

**Rationale**: The current approach can only add *new tables*; it explicitly "does NOT alter the
pre-existing tables" (see `main.lifespan`). This feature needs nullable→backfill→not-null column
adds, FKs, tenant-leading indexes, per-tenant unique constraints, and RLS + grants — all reversible
and ordered. That is exactly Alembic's job, and it gives an auditable history before the founder
data migration (FR-031).

**Alternatives**: (a) More hand-written idempotent `ALTER`s — cannot do phased not-null backfills
or manage RLS/grants reversibly, and leaves no downgrade path. (b) Drop-and-recreate — unacceptable,
destroys the founder's existing data. (c) SQLModel/other — gratuitous churn; SQLAlchemy stays.

---

## R2 — Password hashing (pwdlib + Argon2id, off the event loop)

**Decision**: Use `pwdlib`'s `PasswordHash.recommended()` (Argon2id) exactly as the guide shows.
Wrap `hash`/`verify` in `anyio.to_thread.run_sync` guarded by a module-level
`asyncio.Semaphore` (bound = a small multiple of CPU, env-tunable) so hashing never blocks the
event loop and cannot be used to exhaust CPU/memory. Validate password policy (min length 15, max
≥128, reject known-compromised via a bundled common-password check) **before** hashing. On
successful login, rehash when `pwdlib` reports the stored parameters need upgrading. For unknown
emails on login, verify against a process-level **dummy** Argon2 hash (computed once at import) so
timing matches the existing-user path.

**Rationale**: Directly implements guide §Password hashing and invariants 3–4 and 11; keeps the
async backend non-blocking (Principle V) while bounding resource use.

**Alternatives**: `passlib` (less actively aligned with current FastAPI guidance than `pwdlib`);
hashing on the event loop (blocks the loop under load); per-request dummy-hash generation (wasteful
and the guide warns against it).

---

## R3 — Sessions & CSRF (opaque server-side, `__Host-` cookie, header token)

**Decision**: Opaque session: generate `secrets.token_bytes(32)`, send the base64url raw token in a
`__Host-session` cookie (`Secure; HttpOnly; SameSite=Lax; Path=/`, no `Domain`), store only
`sha256(raw)` in `sessions.token_hash`. A per-session CSRF token is generated the same way; its
raw value is returned in the JSON body (never a cookie) and kept **in memory** by the frontend,
with only `sha256` stored in `sessions.csrf_token_hash`. The shared `require_session` dependency:
read cookie → sha256 → load unrevoked/unexpired session joined to active user+tenant+membership →
enforce idle timeout via `last_seen_at` (write at most every 5 min) → return a frozen
`RequestIdentity`. Every unsafe (state-changing) request additionally requires a matching
`X-CSRF-Token` header **and** an `Origin`/`Referer` check against the configured canonical origin.
CSRF + session tokens rotate on login (and would rotate on tenant switch, not used in v1). Logout
revokes server-side and clears the cookie with matching attributes; it is idempotent.

**Rationale**: Verbatim with guide §Login/session/CSRF and invariants 3, 5, 6, 12. Same-origin
deployment (Vite proxy / single reverse proxy) makes `__Host-` + `SameSite=Lax` + header-CSRF the
simplest correct design; no CORS credential complexity.

**Alternatives**: JWT/stateless sessions (guide forbids; can't revoke server-side; the directive
is explicit "Do not add JWTs"); CSRF cookie double-submit (weaker than a per-session secret held in
memory); `localStorage` for tokens (forbidden — XSS-readable).

**WebSocket note**: see R6 — the handshake authenticates from the same cookie + origin check.

---

## R4 — Row-level security + separate runtime role

**Decision**: Enable **and force** RLS on the 7 tenant-owned tables; policy
`USING/WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)`. Every
protected transaction sets `app.tenant_id` (and `app.user_id`) **transaction-locally**
(`set_config(key, value, true)`) immediately after `BEGIN`, via a helper that wraps the existing
async session (R5). Two DB roles: a **migration owner** (owns tables, runs Alembic) and a
**runtime** role used by the app — not a superuser, not a table owner, without `BYPASSRLS`. Compose
and `.env.example` gain the runtime role/credentials; `config.py` exposes both URLs (owner URL used
only by Alembic). RLS DDL and role grants live in `0004_rls` and run **only** on Postgres; SQLite
tests skip RLS and assert application-level scoping instead. A dedicated Postgres-only `test_rls`
(run in CI/quickstart) verifies the guide's RLS matrix.

**Rationale**: Defense in depth (FR-020, invariants 9–10); matches guide §RLS exactly, including the
pooled-connection warning (never session-level `SET`).

**Alternatives**: App-scoping only (single point of failure for the feature's worst risk); one
superuser role (RLS can be bypassed, defeating the purpose); RLS on SQLite (unsupported).

---

## R5 — Tenant scoping pattern (repositories, cache, ADK, scratch)

**Decision**: (a) **Repositories**: every tenant-owned function in `db/repository.py` gains a
keyword-only `tenant_id: UUID` included in the `WHERE`/`INSERT`. Resource lookups combine id +
tenant in one predicate and return `None`→`404` for foreign/absent rows (never fetch-then-authorize;
invariant 10, FR-018). `user_characters` uniqueness becomes `(tenant_id, name, server, region,
role)`; `guild_profile` becomes one-per-tenant; `tracked_raids.report_code` uniqueness becomes
per-tenant. (b) **Transaction context**: a `tenant_session(identity)` helper opens the async
transaction and sets `app.tenant_id`/`app.user_id` so RLS and app scope agree. (c) **ADK**:
`agent_runner` sets `user_id = str(tenant_id)` (replacing the hardcoded `local_user`) so
`DatabaseSessionService` state is isolated per tenant; `_ensure_session`/`run_async` use it. The WS
layer verifies the conversation belongs to the caller's tenant before streaming. (d) **WCL cache**
(feature 005): the cache key gains a `tenant_id` prefix so cached lookups never cross tenants
(FR-019); `wcl_agent` stays standalone — the backend passes the prefix in, no DB import. (e)
**Scratch**: already per-conversation; conversation is tenant-owned, so no extra change beyond the
ownership check.

**Rationale**: Implements guide §Tenant authorization across *all* paths (reads/writes/search/
export/cache/jobs) and FR-017–FR-019; keeps one authoritative scoping mechanism (DRY).

**Alternatives**: A global SQLAlchemy event that injects tenant filters (too implicit, fights the
explicit-contract principle and is easy to bypass); scoping messages only via conversation FK
(leaves `messages` without its own RLS predicate — we add `tenant_id` to it for uniform RLS).

---

## R6 — WebSocket authentication

**Decision**: On `/ws/chat` connect, before `accept()`, read the `__Host-session` cookie from the
handshake headers, validate it exactly like the HTTP dependency (sha256 → active session → tenant),
and validate the `Origin` header against the canonical origin; reject (close with a policy code)
if either fails. Hold the resolved `RequestIdentity` for the socket's lifetime and pass
`tenant_id` into `_handle_turn`/`stream_response` and all capture calls. Because the socket is
already authenticated and same-origin (cookie `SameSite=Lax` + origin check), per-frame CSRF is not
needed; a disabled user/revoked session is caught on the next turn's re-validation (cheap session
lookup) so disabling takes effect mid-session (FR-023 edge case).

**Rationale**: Browsers send cookies on same-origin WS handshakes; validating there keeps one
session model for HTTP and WS. Origin check is the WS analogue of CSRF.

**Alternatives**: A query-string token (leaks into logs — forbidden by secret-handling rules);
a separate WS auth handshake message (reinvents the cookie we already have).

---

## R7 — Rate limiting & abuse controls

**Decision**: In-process limiter behind an interface. Login uses **progressive delay** keyed by
account and source, backed by the `users.failed_login_count` / `login_blocked_until` columns (per
account) plus an in-memory per-source counter — capped delay (≤30 s), never a permanent lockout.
Public token endpoints (accept-invitation, reset) and admin invitation creation get in-memory
source limits. Responses never reveal whether throttling hit a known vs. unknown account. Config
exposes the thresholds; the limiter interface allows a shared (Redis/Postgres) backend later.

**Rationale**: Satisfies guide §Rate limiting and FR-016 at the current single-process scale with no
new infra (Principle III). The multi-worker caveat is recorded (Complexity Tracking) rather than
pre-solved.

**Alternatives**: Redis now (speculative infra, YAGNI); no throttling (fails FR-016 / invariant 11).

---

## R8 — Founder bootstrap & existing-data migration

**Decision**: A controlled CLI (`backend/cli/bootstrap_admin.py`, run via `uv run`) creates the
first platform admin: prompt for email + password (or read from env/secret), create the `user`
(`is_platform_admin=true`, `active`, Argon2id hash), auto-provision their single `tenant` + owner
`membership`. **No HTTP endpoint** can create the first admin (invariant: no public "create first
admin"). The founder data migration (in `0003_tenant_columns`, or a dedicated data step run right
after) assigns **every** existing row in the 7 tenant-owned tables to the founder's tenant: add
`tenant_id` nullable → `UPDATE … SET tenant_id = <founder tenant>` → validate no NULLs remain → set
`NOT NULL` + add index. The founder tenant id is resolved at migration time (single admin assumed);
if no admin exists yet, the migration fails loudly rather than guessing (no ambiguous assignment,
per guide §Data model).

**Rationale**: FR-004, FR-031, and guide §Operational/Implementation-sequence; keeps the phased,
no-orphan backfill the guide mandates.

**Alternatives**: Assign existing data to a synthetic "default" tenant (user chose founder);
auto-create an admin on first boot (violates the no-public-bootstrap invariant).

---

## R9 — Link delivery seam (no email in v1) & fragment-token handling

**Decision**: One `link_delivery` seam. v1 implementation builds the canonical HTTPS URL from
trusted config (never the inbound `Host`) and **returns the link to the admin** (shown once in the
admin UI response / dev log) for manual sharing; it never emails and never exposes the raw token
elsewhere. Invitation/reset URLs put the raw token in the **fragment**
(`/accept-invite#token=…`), with `Referrer-Policy: no-referrer` on those pages. React reads the
fragment once, immediately `history.replaceState`s it away, keeps it only in memory, and submits it
over HTTPS. A later email implementation drops in behind the same seam, at which point the public
self-service "forgot password" flow (neutral 202) is enabled.

**Rationale**: Implements the clarified founder-mediated delivery and guide §Secret handling / §React
requirements, while keeping the exact seam that lets email + self-service reset land later without
rework (spec FR-007, FR-025, US5 #5).

**Alternatives**: Email now (user has no provider at launch — out of scope); token in query string
(leaks via logs/referrer — forbidden); admin sees the raw token via the normal admin list
(forbidden — the link is shown once at creation/resend only, never stored raw).

---

## Cross-cutting: audit, redaction, config, tests

- **Audit** (FR-030): one append-only `auth_audit_events` writer records the guide's event set with
  non-secret ids only. A shared redaction helper strips keys matching
  `password|token|authorization|cookie|set-cookie|csrf` from logs; APM/exception capture is reviewed
  so it can't bypass it.
- **Config** (`config.py`): cookie name/attrs, session idle+absolute lifetimes, invitation/reset
  lifetimes, token entropy, password min/max, rate-limit thresholds, canonical site URL, runtime vs.
  owner DB URLs — all env-driven with the guide's defaults.
- **Tests**: unit (passwords, tokens, redaction, tenant context), integration (invitations, login,
  sessions/CSRF, admin role enforcement, password reset, rate limit, audit), the **two-tenant
  isolation matrix** (gating US3), and a Postgres-only `test_rls`. Existing endpoint tests are
  updated to authenticate first (a shared `as_user` fixture that provisions a user+tenant+session).
