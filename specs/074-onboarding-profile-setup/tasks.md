# Tasks: 074 onboarding to profile setup

## Phase 1: Foundational (backend data + API)

- [ ] T001 Add `main_class`, `main_spec`, `main_content` (+ CHECK), `onboarding_dismissed_at` to `Tenant` in backend/app/db/models.py
- [ ] T002 Migration backend/migrations/versions/0023_profile_main_spec.py (columns, CHECK, backfill existing tenants as skipped; downgrade drops); prove up/down/up on `pg.py up edda`
- [ ] T003 Repository: `get_profile_settings`, `set_main_selection`, `skip_onboarding` in backend/app/db/repository.py (keyed on tenant id only)
- [ ] T004 Schemas: `MainContent`, `ProfileSettingsIn` (extra=forbid, required nullable keys, max 40, roster validator), `ProfileSettingsOut` in backend/app/schemas.py
- [ ] T005 Routes GET/PUT `/api/profile/settings`, POST `/api/profile/onboarding/skip` in backend/app/api/profile.py

## Phase 2: US1 + US2 backend tests

- [ ] T006 [US1] backend/tests/test_074_onboarding.py: fresh workspace pending; skip → not pending on every later read; own character → not pending
- [ ] T007 [US2] same file: save/reload/clear; hostile values → 422 and stored row unchanged; `tenant_id` in body → 422; another workspace's row unchanged

## Phase 3: Frontend

- [ ] T008 [P] types.ts + restClient.ts: `MainContent`, `ProfileSettings`, `ProfileSettingsInput`; `getProfileSettings`, `saveProfileSettings`, `skipOnboarding`
- [ ] T009 [P] [US1] frontend/src/auth/redirect.ts (+ redirect.test.tsx): `PROFILE_PATH`, `CHAT_HOME`, `safeInternalPath`, `afterLoginPath`
- [ ] T010 [US2] frontend/src/components/onboarding/MainSelector.tsx (roster from `listGuides`, NativeSelect class/spec, ToggleGroup content, Save)
- [ ] T011 [US1] frontend/src/components/onboarding/OnboardingPrompt.tsx (+ OnboardingPrompt.test.tsx: Skip calls the API and reports skipped; selector saves the exact body)
- [ ] T012 [US1] ProfilePage.tsx: load settings; prompt when pending, else the "Your main" card
- [ ] T013 [US1] AcceptInvitePage.tsx → `PROFILE_PATH`; LoginPage.tsx → `afterLoginPath`

## Phase 4: Polish

- [ ] T014 shadcn audit checklist; detect-changes; check.py receipt; board hand-off
