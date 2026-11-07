# Research: 075 character portraits

- **Endpoint**: `GET https://{region}.api.blizzard.com/profile/wow/character/{realmSlug}/{name}/character-media?namespace=profile-{region}&locale=en_US`, `Authorization: Bearer`. Response `assets: [{key: avatar|inset|main-raw, value: url}]`. 404 unknown character; 403 hidden/private. Decision: use `avatar` only. To be confirmed by live-check:075-pre (board #88).
- **Token**: `POST https://oauth.battle.net/token`, `grant_type=client_credentials`, Basic auth; `expires_in` ~24 h. Decision: process memory, refreshed 60 s before expiry; never in Redis (brief: token never in cache values).
- **Realm slug**: stored `server` is what the user typed ("Area 52", "Kel'Thuzad", "Aggra (Português)"). Decision: `server_slug`, then NFKD accent strip, drop everything outside `[a-z0-9-]`, collapse hyphens; then allow-list. Alternatives: raw `server_slug` (fails on accents/parentheses).
- **Path safety**: httpx collapses literal `..` path segments (`/a/x/../y` -> `/a/y`), so quoting is not enough. Decision: allow-list name (letters only, <= 24) and slug before quoting.
- **Cache**: reuse `get_or_load` with a callable TTL: found 24 h, none 6 h, unavailable 5 min. Rejected: a second Redis client in the service (duplicates circuit breaker, lock, stats).
- **Endpoint latency**: lookups run concurrently (semaphore 6) under a 4 s budget; unfinished ones return null for this request.
