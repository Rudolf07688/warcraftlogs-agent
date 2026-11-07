# Research: 074 onboarding

## R1 Where the settings live
- Decision: four nullable columns on `tenants`, written only `WHERE id = <session tenant>`.
- Rationale: one row per workspace already exists (no upsert), the profile is per workspace
  (v1: one user each), and no new RLS surface. `tenants` has no RLS (it is the tenant itself);
  every read/write keys on `identity.tenant_id` from the session, and the body can't carry it
  (`extra="forbid"`).
- Alternatives: a new `tenant_profile_settings` table with RLS (more surface, an RLS test, a
  security review, and an upsert path, for one row per tenant); `guild_profile` (wrong
  lifecycle: replaced/deleted with the guild); `users` (profile is per workspace elsewhere).

## R2 What "new account" means
- Decision: state: pending = `onboarding_dismissed_at IS NULL` and no own character. 0023
  sets `onboarding_dismissed_at = now()` on existing tenants.
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
