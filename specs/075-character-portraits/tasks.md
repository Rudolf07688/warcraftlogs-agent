# Tasks: 075 character portraits

## Phase 1: Backend (sc-363)
- [X] T001 Add `CHAR_PORTRAIT` family, its FamilyConfig and `keys.char_portrait` in wcl_agent/cache/cache.py
- [X] T002 Add `blizzard_client_id` / `blizzard_client_secret` (SecretStr) to backend/app/config.py
- [X] T003 backend/app/services/portraits.py: region allow-list, realm slug + name allow-list, URL builder, token cache, bounded fetch (no redirects, 64 KiB, 3 s), avatar URL guard, `get_or_load` wrapper with callable TTL, `lookup_many` under a 4 s budget
- [X] T004 backend/app/api/portraits.py: `GET /api/profile/portraits` (own + friends from repo), response models; include in backend/app/main.py
- [X] T005 backend/tests/test_075_portraits.py: contract + hostile-input tests (encoding, region, image URL, redirect/body/timeout, secret, key, scope, negative cache)
- [X] T006 mutate.py bites: URL host check, region allow-list, scope to own profile

## Phase 2: Frontend (sc-364)
- [X] T007 frontend/src/api/portraits.ts `getPortraits()` on `send`
- [X] T008 frontend/src/hooks/usePortraits.ts: shared de-duplicated fetch, `byId`, `byIdentity`, refresh key
- [X] T009 ClassAvatar optional `portrait_url` (AvatarImage lazy, initials fallback); pinning test without portrait
- [X] T010 CharactersTab, ProposalCard, WelcomePanel use portraits
- [X] T011 ProposalCard.test mock + one portrait test; usePortraits test

## Phase 3: Hand-off
- [ ] T012 cache tests (test_wcl_cache, 047 local rate), detect-changes, check.py receipt, board handoff
