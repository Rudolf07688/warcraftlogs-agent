# Implementation Plan: Onboarding to profile setup

**Branch**: `074-onboarding-profile-setup` | **Date**: 2026-11-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/074-onboarding-profile-setup/spec.md`

## Summary

New accounts land on `/profile` with a skippable welcome prompt; the profile page gets a main
class/spec/content selector saved per workspace. "Onboarding pending" is server state (no own
characters and never skipped), stored as four nullable columns on `tenants` (migration 0023,
which marks existing workspaces as skipped). Three small endpoints under `/api/profile`; the
roster check reuses `roster_snapshot()`; redirects only to fixed or safe internal paths.

## Technical Context

**Language/Version**: Python 3.12 (FastAPI, async SQLAlchemy, Pydantic v2); TypeScript + React 19
**Primary Dependencies**: existing only (no new package); shadcn `NativeSelect`, `ToggleGroup`, `Card`, `Button` already in `components/ui`
**Storage**: Postgres (`tenants` + 4 columns); SQLite in tests via `create_all`
**Testing**: pytest (SQLite route tests with `as_user` / `make_authed_client`), vitest
**Target Platform**: web app
**Project Type**: web (backend + frontend)
**Performance Goals**: one extra small GET at sign-in (settings), one at profile load; no WCL calls
**Constraints**: backward-compatible shared files (add, don't rename); `CharactersTab.tsx`, `App.tsx`, `routes.tsx` are other streams'
**Scale/Scope**: one row per workspace

## Constitution Check

- I Reuse: roster check via `wcl_agent.game.roster.roster_snapshot()` (the SSOT `api/guides.py` uses); the frontend selector lists classes/specs from the existing `listGuides()` roster; `NativeSelect`/`ToggleGroup`/`Card` reused. PASS
- II Steps: backend (migration, model, repo, API, tests) → frontend (types/client, redirect helper, components, pages). PASS
- III Simplicity: columns on an existing per-workspace row, no new table, no new service. PASS
- IV Typed: `ProfileSettingsIn` (extra=forbid, roster validator) / `ProfileSettingsOut`. PASS
- V Async FastAPI: async handlers on `get_tenant_db`. PASS
- VI GitNexus: impact on `ProfileOut`-adjacent code, `AcceptInvitePage`, `LoginPage` before edits; detect-changes before hand-off. PASS
- VII shadcn: registry components already present; no hand-built control. PASS

## Project Structure

### Documentation (this feature)

```text
specs/074-onboarding-profile-setup/
├── spec.md  plan.md  research.md  data-model.md  quickstart.md  tasks.md  checkpoint.md
└── contracts/profile-settings.md
```

### Source Code (repository root)

```text
backend/migrations/versions/0023_profile_main_spec.py   (new)
backend/app/db/models.py          Tenant: main_class, main_spec, main_content, onboarding_dismissed_at
backend/app/db/repository.py      get_profile_settings, set_main_selection, skip_onboarding
backend/app/schemas.py            MainContent, ProfileSettingsIn, ProfileSettingsOut
backend/app/api/profile.py        GET/PUT /api/profile/settings, POST /api/profile/onboarding/skip
backend/tests/test_074_onboarding.py (new)
frontend/src/types.ts             MainContent, ProfileSettings, ProfileSettingsInput
frontend/src/api/restClient.ts    getProfileSettings, saveProfileSettings, skipOnboarding
frontend/src/auth/redirect.ts (new) + redirect.test.tsx   safe internal paths, post-login target
frontend/src/components/onboarding/MainSelector.tsx (new)
frontend/src/components/onboarding/OnboardingPrompt.tsx (new) + OnboardingPrompt.test.tsx
frontend/src/pages/ProfilePage.tsx      prompt when pending, else the selector card
frontend/src/pages/AcceptInvitePage.tsx → /profile
frontend/src/pages/LoginPage.tsx        safe `from`, /profile when pending
```

**Structure Decision**: existing web layout; `profile_service.py` stays untouched (it is the
character write path; the settings are not characters).

## Complexity Tracking

None.
