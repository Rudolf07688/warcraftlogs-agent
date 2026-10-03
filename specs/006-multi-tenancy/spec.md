# Feature Specification: Multi-Tenancy — Invite-Only Accounts & Private Per-User Workspaces

**Feature Branch**: `006-multi-tenancy`

**Created**: 2026-10-03

**Status**: Draft

**Input**: User description: "We are going to be adding multi-tenancy to the app next. I want to be able to invite my friends (after hosting live of course) and then they need their own pages where they can add their characters and their friends and guilds etc. Please see the guide on multi-tenancy I have put together for you to ground the build: `documentation/multi_tenancy_guide.md`"

## Context

Today the application runs as a single global profile with no accounts: one "me" character, a list of friend characters, and one main guild, plus conversations, tracked raids, captured graphs, and artifacts — all shared globally and visible to anyone who can reach the deployment. The prior phase (005) explicitly deferred multi-user accounts and tenant isolation to "Phase X." This feature **is** that phase.

The goal: once the app is hosted live, the founder can invite friends by email; each invited person gets their own private space where they manage their own characters, friends, guild, and chat history, fully isolated from everyone else. Access is invite-only — there is no public sign-up. The grounding contract for behavior and security is `documentation/multi_tenancy_guide.md`; this spec expresses the user-facing **what** and **why**, and the guide governs the security implementation detail.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Invite a friend and let them activate their account (Priority: P1)

The founder (the only platform administrator) invites a friend by email. The founder obtains a single-use invitation link for that person and shares it with them (e.g. over Discord/DM). The friend follows the link, proves they control the invited email by possessing it, chooses their own password, and lands in their own ready-to-use space. There is no public registration — an account cannot exist without an invitation.

**Why this priority**: This is the backbone of the whole feature — without invitation and account activation there is no multi-user app at all. It is the first demonstrable slice: a second real person can get in.

**Independent Test**: As the founder, create an invitation for an email address and copy its link; open the invitation link as that invitee, set a password, and confirm the invitee ends up signed in to their own empty workspace. Confirm that knowing the invited email **without** the link never lets anyone claim the account, and that there is no way to self-register without an invitation.

**Acceptance Scenarios**:

1. **Given** the founder is signed in as platform administrator, **When** they invite an email address into a role, **Then** an invitation is created and a single-use link is made available for the founder to share with that person.
2. **Given** a valid, unused, unexpired invitation link, **When** the invitee opens it and sets a password meeting policy, **Then** their account is activated and they are signed in to their own workspace.
3. **Given** someone knows an invited email address but does not have the link, **When** they try to claim the account, **Then** they cannot (possession of the single-use link is required).
4. **Given** an invitation link that is expired, already used, or revoked, **When** it is opened, **Then** activation fails with a generic "invalid or expired" message and no account is changed.
5. **Given** two people open the same invitation link simultaneously, **When** both submit, **Then** exactly one activation succeeds.
6. **Given** no invitation exists for an email, **When** that person tries to reach any sign-up path, **Then** no account can be created (no public self-registration exists).

---

### User Story 2 - Sign in, stay signed in securely, and sign out (Priority: P1)

An activated user signs in with their email and password, stays signed in across page loads via a secure server-side session, and can sign out, which immediately ends that session.

**Why this priority**: Nobody can use their workspace without being able to authenticate. It is required alongside US1 for any usable product and is independently testable.

**Independent Test**: With an activated account, sign in with correct credentials and confirm access; sign in with wrong credentials or an unknown email and confirm an identical generic failure; reload the page and confirm the session persists; sign out and confirm the session no longer works.

**Acceptance Scenarios**:

1. **Given** an activated account, **When** the user signs in with correct email and password, **Then** they gain access to their workspace.
2. **Given** a wrong password, an unknown email, or a disabled account, **When** a sign-in is attempted, **Then** the same generic failure is returned (no hint whether the email exists).
3. **Given** a signed-in user, **When** they reload or revisit the app, **Then** they remain signed in until the session expires (idle or absolute lifetime) without re-entering credentials.
4. **Given** a signed-in user, **When** they sign out, **Then** the session is immediately invalidated server-side and can no longer be used.
5. **Given** a session that has hit its idle timeout or absolute lifetime, **When** the user acts, **Then** they are required to sign in again.
6. **Given** the session credential, **When** inspected from the browser, **Then** page JavaScript cannot read it and it is never written to browser storage.

---

### User Story 3 - Each user's data is private and isolated from everyone else (Priority: P1)

Every user manages their **own** profile — their self character, friend characters, and main guild — and has their **own** conversations, tracked raids, captured graphs, artifacts, and exports. One user can never see, change, or even detect another user's data. This is the core promise of multi-tenancy.

**Why this priority**: This is the headline value and the central risk of the feature. Isolation failures are the worst possible outcome (one friend seeing another's data), so it is P1 and gated by negative cross-tenant tests.

**Independent Test**: Create two activated users, A and B. Have each add their own characters and main guild and hold their own conversations. Signed in as A, confirm A sees only A's profile, conversations, raids, and artifacts; then attempt — by guessing identifiers and by supplying B's identifiers in requests — to read or modify B's data, and confirm every attempt fails as "not found" without revealing that B's data exists.

**Acceptance Scenarios**:

1. **Given** two users with their own data, **When** user A views their profile/characters/guild, conversations, tracked raids, and artifacts, **Then** A sees only their own and never B's.
2. **Given** user A knows or guesses an identifier belonging to B's data, **When** A requests it, **Then** the response is "not found" (A cannot confirm the item exists elsewhere).
3. **Given** user A supplies B's workspace or resource identifier in a request body, query, or header, **When** the request is processed, **Then** it does not change which data A can access (the user's identity is derived from their authenticated session, not from client input).
4. **Given** a list, search, count, export, or background task, **When** it runs for user A, **Then** it operates only over A's data in every one of those paths.
5. **Given** the existing personalization features (profile context, spec guides, guild summary, caching, artifacts, per-message reports), **When** used by a signed-in user, **Then** they operate only within that user's own data.
6. **Given** a user adds, edits, or removes a character or main guild, **When** another user views their own profile, **Then** they are unaffected (per-user single-main-guild and personalization rules continue to hold within each workspace).

---

### User Story 4 - Founder manages users and invitations (Priority: P2)

The founder has an administration page available only to them, where they can see users and their status, create invitations (and copy the shareable link), resend or revoke pending invitations, trigger a password reset for a user (and copy the shareable reset link), and disable or re-enable accounts. Ordinary users cannot see or use any of this, even if they navigate directly to it or call the operations themselves.

**Why this priority**: Operating a live, invite-only deployment needs these controls, but the app is usable for the first invited friends (US1–US3) before the full admin surface exists, so it ranks P2.

**Independent Test**: Signed in as the founder, open the admin page, send an invitation, resend it, revoke it, and disable then re-enable a user; confirm each takes effect. Then, signed in as an ordinary user, confirm the admin page is not shown and that calling any admin operation directly is refused.

**Acceptance Scenarios**:

1. **Given** the founder (platform administrator), **When** they open the admin area, **Then** they see a list of users with email, status, and last-sign-in, and pending invitations with their status and expiry.
2. **Given** a pending invitation, **When** the founder resends it, **Then** a fresh link is issued (made available to copy and share) and the previous one stops working.
3. **Given** a pending invitation, **When** the founder revokes it, **Then** the link can no longer be used to activate an account.
4. **Given** an active user, **When** the founder disables that account, **Then** that user can no longer sign in and their active sessions stop working; re-enabling restores sign-in.
5. **Given** an ordinary (non-admin) user, **When** they navigate to the admin area or call an admin operation directly, **Then** access is refused regardless of what the UI shows.
6. **Given** any admin view, **When** it renders, **Then** it never displays passwords, password hashes, or any raw or hashed security tokens.

---

### User Story 5 - Recover access via a founder-triggered password reset (Priority: P2)

A user who has forgotten their password asks the founder, who triggers a reset and shares the resulting single-use link with them; the user follows it and sets a new password. The founder can disable an account or trigger a reset, but can never see, set, or recover anyone's password. (Because there is no email provider in v1, reset links are founder-mediated like invitations; a fully self-service email flow is a fast-follow once email delivery is added.)

**Why this priority**: Important for a live deployment but not required for the first end-to-end multi-user demo, so P2. Reuses the same single-use-link mechanism as invitations.

**Independent Test**: As the founder, trigger a password reset for an activated user and copy the reset link; as that user, follow the link, set a new password, confirm sign-in works with the new password and that all prior sessions were ended; confirm an expired/used link fails generically.

**Acceptance Scenarios**:

1. **Given** the founder, **When** they trigger a reset for a user, **Then** a single-use, time-limited reset link is generated for the founder to share with that user.
2. **Given** a valid reset link, **When** the user sets a new password, **Then** the password is updated, all of that user's existing sessions are ended, and they must sign in again.
3. **Given** an expired, used, or revoked reset link, **When** it is opened, **Then** the reset fails generically and no password changes.
4. **Given** the founder, **When** they manage a user, **Then** they can disable the account or trigger a reset, but cannot view, set, email, or recover the user's password.
5. **Given** the reset mechanism is built behind a delivery seam, **When** an email provider is later configured, **Then** a public self-service "forgot password" flow (with neutral, non-enumerating responses) can be enabled without reworking the reset model.

---

### Out of Scope for v1

Explicitly deferred (and not required by any story above), to keep the first release simple:

- **Shared / multi-member workspaces and tenant-switching**: Each user has exactly one private workspace in v1 (one user ↔ one workspace), so there is no shared workspace, no in-workspace roles beyond the owner, and no workspace-switching UI. The isolation and membership model is built so multi-membership could be added later without rework, but it is not exercised now.
- **Automated email delivery and public self-service password reset**: Invitation and reset links are founder-mediated at launch; automated email and a public "forgot password" flow are a fast-follow once an email provider is configured.
- **Public self-registration, social login, SSO, and multi-factor authentication**: Invite-only email-and-password only in v1 (admin MFA is a noted future increment).

### Edge Cases

- **Existing data at launch**: the app already holds a global profile, conversations, tracked raids, graphs, and artifacts created before accounts existed. On turning multi-tenancy on, all of this existing data is migrated into the founder's own workspace, never left orphaned and never exposed to newly invited users.
- **Invitation to an already-active user**: inviting an email that already has an active account into a workspace they already belong to is reported clearly rather than silently duplicating or reactivating.
- **Disabled user mid-session**: when an account is disabled, its active sessions stop working on the next request, not only at next sign-in.
- **Repeated sign-in failures**: repeated failures are slowed progressively (per account and source) rather than permanently locking the account, so the mechanism cannot be abused to lock a user out.
- **Neutral responses**: sign-in failures, "forgot password", and throttling never reveal whether a given email has an account.
- **Link hygiene**: invitation and reset links are single-use and expiring; once opened, the secret in the link is not left visible in the address bar, browser history, or server logs.
- **Founder bootstrap**: the first platform administrator is established through a controlled, non-public mechanism — there is never a public "create the first admin" page.
- **No credential leakage**: passwords and session/link secrets never appear in the database as plaintext, in logs, in exports, in error messages, or in audit records.
- **Non-regression with one user**: with a single signed-in user, every existing capability (chat, raid tracking, profile/characters/guild, spec guides, caching, artifacts, math rendering, PDF/per-message reports) continues to work exactly as before — now scoped to that user.

## Requirements *(mandatory)*

### Functional Requirements

**Identities & access model**

- **FR-001**: The system MUST represent each person as a single global identity keyed by their email address (case-insensitive), and MUST support no public self-registration — accounts come into existence only through an invitation.
- **FR-002**: The system MUST store passwords only as one-way password hashes; plaintext passwords MUST never be persisted, logged, exported, emailed, returned in responses, or recorded in audit data.
- **FR-003**: The system MUST enforce a password policy (minimum length suitable for password-only authentication, allowing long passphrases, rejecting known-compromised passwords) at the server, independent of any client-side check.
- **FR-004**: The system MUST distinguish a platform-administrator privilege (the founder, deployment-wide) from ordinary workspace access, and MUST NOT infer platform-administrator status from workspace membership. The first platform administrator MUST be created through a controlled, non-public mechanism.

**Workspaces & membership**

- **FR-005**: The system MUST provide isolated workspaces such that every user manages their own profile (self character, friend characters, main guild), conversations, tracked raids, captured graphs, artifacts, and exports within their workspace. In v1 each user has exactly one private workspace (one user ↔ one workspace); shared/multi-member workspaces are out of scope but the membership model MUST NOT preclude adding them later.
- **FR-006**: Each user's active workspace MUST be derived from their authenticated session and verified membership, never trusted from a client-supplied body, query parameter, or header.

**Invitations**

- **FR-007**: The platform administrator MUST be able to invite a person by email into a role, which creates an invitation and produces a single-use link that the administrator shares with that person (founder-mediated delivery in v1; the delivery step MUST be behind a seam so automated email can replace it later). Only the platform administrator may create invitations in this version.
- **FR-008**: Accepting an invitation MUST require possession of a cryptographically random, single-use, expiring link tied to the invited email; knowledge of the email alone MUST be insufficient to claim the account.
- **FR-009**: Accepting a valid invitation MUST let the invitee set their first password, activate their account, grant the invited membership, and sign them in; concurrent acceptance of the same invitation MUST result in exactly one success.
- **FR-010**: Invalid, expired, revoked, or already-used invitations MUST fail with a generic message and MUST NOT alter any account.
- **FR-011**: The platform administrator MUST be able to resend an invitation (which invalidates the prior link) and revoke a pending invitation (which disables the link).

**Sign-in, sessions, sign-out**

- **FR-012**: The system MUST authenticate users by email and password and establish an opaque, server-side session carried in a secure, browser-script-inaccessible cookie; the session credential MUST never be readable by page JavaScript nor stored in browser storage.
- **FR-013**: Sign-in failures (wrong password, unknown email, disabled account, unavailable membership) MUST return a single generic failure that does not reveal whether the email exists.
- **FR-014**: Sessions MUST expire by both idle timeout and absolute lifetime, and MUST be revocable server-side; sign-out MUST immediately invalidate the current session and be idempotent.
- **FR-015**: Every state-changing request made with a session MUST be protected against cross-site request forgery; the protection MUST be refreshed on sign-in and on workspace switch.
- **FR-016**: Repeated authentication failures MUST be throttled progressively per account and per source rather than permanently locking the account, and throttling MUST NOT reveal whether an account exists.

**Tenant isolation (applies to all workspace-owned data)**

- **FR-017**: Every read, write, delete, list, count, aggregate, search, export, and background task over workspace-owned data MUST be scoped to the acting user's active workspace.
- **FR-018**: A request for a workspace-owned resource that does not belong to the caller's active workspace MUST respond as "not found", without disclosing that the resource exists in another workspace, and resource lookups MUST combine the resource identity and workspace scope in the same authorization step (listing access MUST NOT imply update/delete access).
- **FR-019**: Workspace scope MUST be applied to all derived and cached data as well — including cached data-lookup results, spec guides, guild summaries, captured graphs, artifacts, and generated reports — so that no cached or derived value crosses workspace boundaries.
- **FR-020**: The system MUST retain defense-in-depth isolation at the data store so that a missing application-level scope filter still cannot return or modify another workspace's rows.

**Administration**

- **FR-021**: The platform administrator MUST have an administration surface to list users (email, status, last sign-in) and pending invitations (status, expiry), and to resend/revoke invitations, disable/enable accounts, and manage memberships.
- **FR-022**: Every administrative operation MUST independently enforce the platform-administrator privilege on the server; hiding the admin page in the UI MUST NOT be treated as authorization.
- **FR-023**: Disabling an account MUST prevent future sign-in and invalidate that account's active sessions; re-enabling MUST restore sign-in.
- **FR-024**: Administrative views MUST never display passwords, password hashes, or any raw or hashed security tokens.

**Password reset**

- **FR-025**: The platform administrator MUST be able to trigger a password reset for a user, producing a single-use, time-limited link that the administrator shares with that user (founder-mediated in v1, behind the same delivery seam as invitations). A public self-service "forgot password" flow — which MUST then return the same neutral confirmation regardless of whether the email exists — is deferred until automated email delivery is available.
- **FR-026**: Completing a reset via a valid link MUST update the password, end all of that user's existing sessions, and require a fresh sign-in; invalid/expired/used reset links MUST fail generically with no change.
- **FR-027**: The platform administrator MUST be able to disable an account or trigger a reset, but MUST NOT be able to view, set, or recover any user's password.

**Links, secrets & auditing**

- **FR-028**: Invitation and reset links MUST point only at the configured canonical site over a secure connection and MUST state their expiry without exposing internal identifiers; links MUST be constructed from trusted configuration, never from an inbound request header.
- **FR-029**: The secret contained in an invitation or reset link MUST not persist in the browser address bar, browser history, referrer, or server access logs after the page loads.
- **FR-030**: The system MUST record audit events for security-relevant actions (sign-in success/failure, sign-out, invitation created/resent/revoked/accepted, password reset requested/completed, account enabled/disabled, membership changes, workspace switch, admin authorization failures) without recording passwords, password hashes, or raw/hashed tokens.

**Launch & migration**

- **FR-031**: Turning on multi-tenancy MUST migrate all pre-existing, previously-global data into the founder's workspace, with no orphaned or ambiguously-owned rows, and MUST NOT expose any pre-existing data to newly invited users.
- **FR-032**: With a single signed-in user and their migrated data, all existing capabilities MUST behave exactly as before (no functional regression); multi-tenancy is additive to existing behavior, now scoped per user.
- **FR-033**: Production authentication traffic MUST be served only over a secure (HTTPS) connection.

### Key Entities *(include if feature involves data)*

- **User**: A global person-identity keyed by normalized email, with account status (invited / active / disabled), a password hash (set at activation), and a platform-administrator flag. Belongs to one or more workspaces.
- **Workspace (Tenant)**: An isolated space that owns a user's application data; the boundary across which all isolation is enforced.
- **Membership**: The link between a user and a workspace, carrying the user's role within it; the authority for what a signed-in user may access.
- **Invitation**: A pending, single-use, expiring grant tying an email to a workspace and role, represented to the recipient as a secret link; has states pending / accepted / revoked / expired.
- **Session**: An opaque, server-side record of a signed-in user's authenticated state and active workspace, carried by a secure cookie, with idle and absolute expiry and server-side revocation.
- **Password reset token**: A single-use, time-limited secret, delivered as a link, that authorizes setting a new password and ending existing sessions.
- **Audit event**: A redacted, append-only record of a security-relevant action, excluding all secrets.
- **Workspace-owned application data** (now scoped per workspace): the existing profile (self/friend **Character References** and the **Guild Reference**), **Spec Guides** and guild summaries, **Conversations** and messages, **Tracked raids**, **Captured graphs**, **Artifacts**, **Cached tool results**, and **Per-message/conversation reports** — each gains a workspace owner and is only ever accessed within that workspace.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A newly invited friend can go from receiving an invitation to a working, signed-in, empty-but-ready workspace in under 5 minutes, with no other person's data visible at any point.
- **SC-002**: 100% of attempts to access another workspace's data — by guessing identifiers or by supplying another workspace's identifiers in request body, query, or headers — fail as "not found", in both normal and deliberately-unscoped (defense-in-depth) test paths.
- **SC-003**: There is no way to create an account without a valid invitation, and no invitation can be accepted without its single-use link, verified across expired, revoked, reused, and concurrent-acceptance cases.
- **SC-004**: Sign-in failures and throttling responses are indistinguishable between existing and non-existing accounts in 100% of tested cases (no account enumeration); the same neutrality applies to any public "forgot password" endpoint once it is enabled.
- **SC-005**: No plaintext password and no raw or hashed link/session token ever appears in the database, logs, exports, error messages, or audit records, verified by inspection.
- **SC-006**: Every administrative operation is refused for non-administrators in 100% of cases when invoked directly, regardless of what the UI displays.
- **SC-007**: Sign-out and password reset end the relevant server-side sessions immediately, verified by the invalidated session failing on its next use.
- **SC-008**: With one signed-in user holding the migrated data, 100% of existing capabilities behave as before (zero functional regressions), and no pre-existing data is visible to any newly invited user.

## Assumptions

- **Stack and grounding**: The implementation follows `documentation/multi_tenancy_guide.md` as the security and behavioral contract. It reuses the existing stack (async FastAPI backend, PostgreSQL, React frontend) and the current data-access layer rather than replacing it; the guide's data model maps onto the existing tables (`conversations`, `messages`, `tracked_raids`, `captured_graphs`, `user_characters`, `guild_profile`, `artifacts`), each of which gains a workspace owner.
- **Schema migrations**: The project currently creates schema additively at startup (new tables only; it does not alter existing tables). This feature requires altering existing tables (adding owner columns, backfilling them in phases, adding constraints/indexes, and enabling row-level security), which the current approach cannot do. A proper migration tool (e.g. Alembic) is therefore expected to be introduced for this feature; the exact tooling is a plan-level decision recorded against the Simplicity-First principle.
- **Invite-only, no SSO/MFA in v1**: No public registration, social login, SSO, or multi-factor authentication in this version (MFA for the admin is a noted future increment). Email-and-password only.
- **Founder is the sole platform administrator**: The user who hosts the deployment is the first and only platform administrator in v1, bootstrapped through a controlled command/migration; only they invite others. Friends are invited as ordinary users.
- **Link delivery (founder-mediated in v1)**: There is no email provider in v1. Invitation and password-reset links are generated in the app; the founder copies each link from the admin area and shares it with the person directly (e.g. Discord/DM). Delivery is kept behind a seam so automated transactional email (and a public self-service "forgot password" flow) can be added later without changing the invitation/reset model.
- **Standard security defaults**: Session lifetimes, link expiry, password length, token entropy, and throttling follow the guide's defaults (e.g. configurable session idle/absolute timeouts, expiring single-use links, long-password policy, progressive throttling) unless deployment configuration overrides them.
- **Desktop-primary**: Consistent with prior phases, desktop remains the primary target; narrow layouts stay usable.
- **Builds on phases 1–5**: Streaming chat, raid tracking, persona, graph capture, PDF/per-message export, caching, and the profile/characters/guild personalization delivered in phases 1–5 are assumed complete and are brought under per-workspace isolation by this feature.

## Dependencies

- A deliverable path for invitation and password-reset links (an email provider in production, or the administrator-mediated fallback), and a configured canonical HTTPS site URL from which links are built.
- A controlled bootstrap mechanism (command or migration) to establish the first platform administrator.
- A schema-migration capability (e.g. Alembic) able to alter existing tables — add owner columns, backfill them in phases, add constraints/indexes, and enable row-level security — since the current startup-time additive table creation cannot perform these changes.
- The ability to run a data migration that assigns existing pre-accounts data to its new owner.
