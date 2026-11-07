# Research: 074 onboarding

## R1 Where the settings live
- Decision: a new tenant-owned table `profile_settings` (PK `tenant_id`), RLS as
  `profile_proposals` (ENABLE + FORCE, `tenant_isolation`, runtime grant); upserts with
  `ON CONFLICT (tenant_id)`. The body can't name the tenant (`extra="forbid"`).
- Rejected (tried first): four columns on `tenants`. `backend/cli/bootstrap_admin.py` inserts a
  `Tenant` through the ORM between `upgrade 0002_auth_tenancy` and `upgrade head`, and the ORM
  names every mapped column, so the documented first-admin setup (and `pg.py up`) failed.
- Also rejected: `guild_profile` (replaced/deleted with the guild); `users` (same bootstrap
  problem; the profile is per workspace elsewhere).

## R2 What "new account" means
- Decision: state: pending = no `profile_settings` row or no skip time, and no own character.
  0023 inserts a skipped row for every existing tenant.
- Rationale: covers invitation activation, the bootstrap admin (`backend/cli/bootstrap_admin.py`,
  no invitation) and an invitee who closed the tab; existing workspaces are untouched.
- Alternatives: a flag at invitation acceptance (misses the bootstrap admin; `auth.py` and
  `invitation_service` are outside the footprint); localStorage (per device, lost on clear).

## R3 Roster validation
- Decision: `roster_snapshot().classes()` / `.specs_for(class)`, exact match; `max_length=40`
  first. Same SSOT as `api/guides.py::_require_known`.
- Frontend lists the roster from `listGuides()` (already used by the Class Guides tab).

## R4 Redirects
- Decision: activation → literal `/profile`. Login → `from` (set by `RequireAuth` from
  `location.pathname`) only if it starts with a single `/` and has no `//`, `\` or control
  characters; else `/app`. When the target is `/app` and settings say pending → `/profile`.
  A failed settings read keeps the target.
- There is no `?next=` parameter today; none is added.
