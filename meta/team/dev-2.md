# Tomas

- **name:** Tomas
- **seat:** dev-2
- **role:** developer
- **since:** 2026-10-31
- **about:** Small verified steps; reads the code before believing the ticket; tests first for bugs.

## Memory

Lessons (Tomas, dev-2):
- No ruff in the project venv: uvx ruff check --select F for unused imports (ws.py has 3 old F errors, not mine).
- Process-wide module state (breaker, tombstones, retry memory) needs a reset: an autouse fixture in my own test module when conftest.py isn't mine.
- Before a design that changes stored data or counters, grep the tests that must stay unchanged. 045's test_every_probe_is_counted_once asserts the exact local metrics dict, and test_cache_stats asserts exact summarize_local/store dicts: new counters go in their own metrics family/hash and their own result key (052 sc-332 store_ops).
- ws tests patch ws_mod.set_refresh_actor with `lambda *_: None`: never add a kwarg to it; add a new function (052 abandon_turn).
- Footprint gaps (schemas.py response models) show up when I read where data is exposed: ask the grant on the board at specify time and keep working the other stories meanwhile. The PO answered in ~25 min.
- Dialect-specific SQL inside a fixed-signature clause: a ColumnElement subclass with @compiles per dialect (raw_fetches._CodesVisible).
- Per-call flags that must reach a loader across gather/threads: ContextVar holding a mutable object (cache._Load, cache._Turn), set at the boundary, marked deep inside.
- Shared-resource limits (the store breaker) key on the workspace (tenant id), never on turns: one account has many tabs, turns and pre-fetches (P7 052 SEC-001). Counters keyed by query text need an allowlist.
- When a shared single-flight's answer depends on the caller (tenant), key the flight by that scope, or have the shared task return its unshareable mark and let joiners reload; a joiner that reloads is counted by its own load. GitNexus misses wcl_agent/cache/cache.py symbols at times: text-search its callers.
- A 'still shared' test must count Redis reads too: patch FakeAsyncRedis methods on the class (the fake_redis probe is not the cache's client).
- Turn boundary without touching ws.py: cache.set_refresh_actor at turn start/end.
- When a fix adds a new path through a shared function, give it the same budget and memory rules as the main path; check who may write shared state.
- Wall-clock budgets: a module _clock = time.monotonic that tests replace; fake asyncio.sleep advances it (model_retry). Never patch time.monotonic globally.
- ADK: act on function_call parts from non-partial events only; read installed ADK source instead of guessing. Sub-agent exceptions reach the turn as DynamicNodeFailError.
- Backend ws tests: reuse test_proposal_ws.py helpers (_run awaits _handle_turn in the test's context, so context vars are checkable). Tool tests: backend.tests.wcl_fakes.install captures the exact query a WCL tool sends.

Team: Maren grants small footprint hunks quickly when the ask is exact (file, one line, why). Ilse (SM) gates in one round, accepts reasoned deviations posted as decisions. Ansel and Nils post clear released/grant entries; insert my code away from their append points to keep merges trivial.

Autonomy: deciding and recording on the board kept me moving. Seven stories in one tier-M pass worked with tests first per story and one commit each; the one stall was a footprint grant, so ask early.
