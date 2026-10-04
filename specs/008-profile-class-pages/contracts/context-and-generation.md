# Contract: Spec-guide generation & context reuse (US2/US3)

Internal (non-HTTP) contracts for generating guides into the shared library and surfacing
them to characters and the agent. Reuses `services/guide.py` machinery.

## Generation service (`backend/app/services/guide.py`, EXTENDED + `spec_guides.py` NEW helper)

```python
async def ensure_spec_guide(class_name: str, spec: str, *, force: bool = False) -> None:
    """Idempotent, best-effort generation of the (class, spec) guide into the shared library.

    - ready & not force, or pending  → no-op (dedup; FR-013, SC-004)
    - absent | failed | force        → upsert status=pending, spawn off-loop generation;
                                        success → ready+markdown, error/empty → failed (retryable)
    Never raises into the caller.
    """
```

- Reuses `_generate_text(_GUIDE_PROMPT.format(cls=class_name, spec=spec))` (unchanged off-loop disposable-session path) and the in-flight dedup set (re-keyed to `(class, spec)`).
- Concurrency: the `uq_spec_guide_identity` constraint guards concurrent inserts (loser catches `IntegrityError`, reads the winner).

## Repository helpers (`backend/app/db/repository.py`, NEW)

```python
async def get_spec_guide(session, *, class_name, spec) -> SpecGuide | None
async def upsert_spec_guide(session, *, class_name, spec, status, guide_markdown=None) -> SpecGuide
async def list_spec_guides(session) -> list[SpecGuide]                      # all rows (global)
async def get_spec_guides_for(session, pairs: list[tuple[str,str]]) -> dict[tuple[str,str], SpecGuide]
```
- These use a **non-tenant** session (global table); no `tenant_id` parameter.

## Character flow (`run_character_guide`, EDIT)

```
resolve (class, spec) from WCL (as today)  →  persist class_name/active_spec on the character
                                           →  await ensure_spec_guide(class, spec)
```
- No longer writes per-character markdown/status. Auto-fetch on add (FR-015) thus reuses an existing ready guide (zero regeneration) or triggers one.
- Unresolved spec ⇒ no guide attached (unchanged behavior; FR-016).

## Context preamble (`services/profile_context.build_preamble`, EDIT) — FR-016

Extend the single preamble builder to take a guide lookup instead of reading per-character
markdown:

```python
def build_preamble(self_character, friends, guild, *, known_raids=(), known_players=(),
                   known_encounters=(), known_guilds=(),
                   spec_guides: dict[tuple[str, str], str] = {}) -> str: ...
```
- For each profile character with a resolved `(class_name, active_spec)`, include its guide from `spec_guides` (bounded exactly as today via the existing `_PER_GUIDE_CHARS`/`_TOTAL_GUIDE_CHARS` caps). Empty map / unresolved ⇒ byte-identical to pre-feature output (SC: no regression).
- `ws._handle_turn` builds the `spec_guides` map by fetching `get_spec_guides_for(...)` for the distinct `(class, spec)` of the tenant's profile characters (global read, no tenant scope) and passes it in.

## Profile read-path (`CharacterOut`, EDIT) — FR-016

- `CharacterOut.guide_status` / `guide_updated_at` become **derived** from the character's spec guide (looked up by `(class_name, active_spec)`), so the existing UI badge keeps working with the shared store. `GET /api/profile` resolves these by batch-loading the relevant `spec_guides` rows.

## Rate limiter (`backend/app/auth/rate_limit.py`, REUSE)

- Add a module-level `guide_limiter = InProcessRateLimiter(per_minute=settings.wcl_guide_generate_per_minute)`; the generate endpoint gates on `guide_limiter.allow_request(str(user_id))`.

## Config (`backend/app/config.py`, EDIT)

- `wcl_guide_generate_per_minute: int = 10` — per-user cap on manual generation requests.

## Acceptance mapping
- FR-013 dedup; FR-015 auto-fetch reuse; FR-016 derived status + preamble reuse; FR-017 remove-character leaves shared guide; FR-014 rate limit; SC-004 zero duplicate generation.
