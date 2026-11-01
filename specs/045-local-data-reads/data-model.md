# Data model: 045 (no migration)

## Existing tables, new uses
- `raw_reports`: a row with `visibility = 'gone'`, `end_time_ms = NULL`, `checked_at = seen_at` is a **tombstone** (was: deleted). Never public, never "finished". Replaced by a newer summary status (existing `checked_at <` upsert guard).
- `raw_fetch_grants`: refreshed only when the stored `granted_at` is more than 1 h older than the new one.
- `raw_fetches`: unchanged.

## In-process types
- `StoredFetch(content: bytes, shared: bool)` — client ↔ fetch source.
- `ProbeOutcome = Literal["hit", "miss", "not_visible", "timeout"]`.
- `_Breaker(state: closed|open|half_open, until: float, trial: bool)` — transitions in plan.md.
- `BatchResult(gone: list[str], changed: list[FetchedResponse])` — writer result (contract 5, Ansel's post-store hook).
- `FetchedResponse.requested_at: datetime | None` (request start; `None` → `fetched_at`).
- Load holder (`cache`): `unshareable: bool`. Turn holder (`cache`): `external: bool`.

## Redis
- `wcl:v1:gone:<code>` — tombstone, TTL `WCL_CACHE_LOCK_MS`.
- `wcl:metrics:v1:local:<day>` — fields `store_hit`, `store_miss`, `store_not_visible`, `store_timeout`, `turns`, `local_turns`; retention as family hashes.
