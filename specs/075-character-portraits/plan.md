# Implementation Plan: Character portraits from Battle.net

**Branch**: `075-character-portraits` | **Date**: 2026-11-07 | **Spec**: [spec.md](spec.md)

## Summary

A new backend service looks up each profile character's avatar image from Blizzard's Profile API
(character-media, client-credentials token) and caches the outcome in the shared Redis cache as a
new `get_or_load` family. A new router serves `GET /api/profile/portraits` for the caller's own
and friend characters, read from the tenant's stored profile. The frontend fetches it once per
page through a small hook, and the shared `ClassAvatar` shows the image (lazy, same size) with
the initials as fallback, on the Characters tab, the chat confirmation card and the welcome
page's recent raids and runs. Board decisions: `scope:075:endpoint-shape`, `scope:075:cache`,
`scope:075:outbound`, `scope:075:image-url`.

## Technical Context

**Language/Version**: Python 3.14 (FastAPI, httpx 0.28, redis.asyncio), TypeScript/React 19 + Tailwind v4 + shadcn
**Primary Dependencies**: existing only (httpx, pydantic, `wcl_agent.cache.cache.get_or_load`, radix Avatar via shadcn `ui/avatar`)
**Storage**: Redis only (new cache family `char_portrait`); no migration
**Testing**: pytest with a fake `httpx.MockTransport` and an in-memory fake Redis (as `test_wcl_cache`); vitest + Testing Library
**Constraints**: no live Blizzard calls in tests; endpoint bounded at ~4 s; outbound 3 s / 64 KiB / no redirects
**Scale/Scope**: up to MAX_OWN_CHARACTERS own + 50 friends per tenant

## Constitution Check

- I Reuse: cache through `get_or_load` (family + key builder added there, granted #83); realm slug starts from `server_slug`; avatar is the existing `ClassAvatar` on shadcn `Avatar`/`AvatarImage`; REST through the exported `send`. PASS
- III Simplicity: no background jobs, no DB; token cached in process memory. PASS
- IV Typed: Pydantic response models in the router; a Pydantic cache value; a frozen dataclass for the character identity. PASS
- V Async: httpx.AsyncClient; endpoint `async def`. PASS
- VI GitNexus: impact on `ClassAvatar`, `CacheFamily`, `keys`, `Settings` before editing. PASS
- VII shadcn: the avatar stays the registry `Avatar`/`AvatarFallback`; the portrait is a plain lazy `<img>` inside it, because the registry's `AvatarImage` preloads eagerly with `new Image()` (no `loading="lazy"`). Hand-built exception, named here. PASS

## Project Structure (files touched)

```text
backend/app/services/portraits.py      # new: Blizzard client, URL guards, cache wrapper, lookup_many
backend/app/api/portraits.py           # new: GET /api/profile/portraits + response models
backend/app/main.py                    # include the router
backend/app/config.py                  # blizzard_client_id / blizzard_client_secret (SecretStr)
wcl_agent/cache/cache.py               # CacheFamily.CHAR_PORTRAIT, FAMILIES entry, keys.char_portrait
backend/tests/test_075_portraits.py    # new
frontend/src/api/portraits.ts          # new: getPortraits() on send
frontend/src/hooks/usePortraits.ts     # new: shared, de-duplicated fetch + lookups
frontend/src/components/profile/ClassAvatar.tsx   # optional portrait_url
frontend/src/components/profile/CharactersTab.tsx # pass portraits
frontend/src/components/ProposalCard.tsx          # pass portraits by character id
frontend/src/components/ProposalCard.test.tsx     # mock portraits; one portrait row test
frontend/src/components/WelcomePanel.tsx          # avatars beside character names
frontend/src/components/profile/ClassAvatar.test.tsx, CharactersTab.test.tsx, WelcomePanel.test.tsx, hooks/usePortraits.test.tsx  # new
```

## Complexity Tracking

None.
