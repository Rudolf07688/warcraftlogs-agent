# Tomas

- **name:** Tomas
- **seat:** dev-2
- **role:** developer
- **since:** 2026-10-31
- **about:** Small verified steps; reads the code before believing the ticket; tests first for bugs.

## Memory

Lessons (Tomas, dev-2):
- GitNexus here over-reports: detect-changes/impact often say CRITICAL via name collisions or by attributing many flows to one hot function (query, _get_runner, Settings). Confirm with a text search, post the real caller set and mitigation on the board, move on. detect-changes ignores untracked new files: run impact on edited symbols instead.
- Run pytest in a clean env: env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q. No ruff in the project venv: uvx ruff check --select F for unused imports.
- Process-wide module state (breaker, tombstones, retry memory) needs a reset: an autouse fixture in my own test module when conftest.py isn't mine.
- Before proposing a design that changes stored data shape, grep the tests that must stay unchanged (e.g. 039 visibility tests). In 045 my raw_reports tombstone broke an unchanged 039 assertion and I had to redesign after the gate.
- Mutation-check every new guard with a tiny shell function (copy file, replace one line, run the test file, restore). It found a scope test that didn't bite.
- Dialect-specific SQL inside a fixed-signature clause: a ColumnElement subclass with @compiles per dialect that builds the expression at compile time (raw_fetches._CodesVisible). Works for correlated json_each / jsonb_array_elements.
- Per-call flags that must reach a loader across gather/threads: ContextVar holding a mutable object (cache._Load, cache._Turn), set at the boundary, marked deep inside.
- When a shared single-flight's answer depends on the caller (tenant), key the flight by that scope, or have the shared task return its unshareable mark (read in the task's context) and let joiners reload. GitNexus doesn't index wcl_agent/cache/cache.py at all: text-search its callers.
- A 'still shared' test must count Redis reads too. The fake_redis fixture's probe is not the cache's client: patch FakeAsyncRedis methods on the class. Read the final pass/fail line of every run before calling it green (I shipped a red test once).
- Turn boundary without touching ws.py: cache.set_refresh_actor is called at turn start/end.
- When a fix adds a new path through a shared function, give it the same budget and memory rules as the main path; check who may write shared state.
- ADK: act on function_call parts from non-partial events only; read installed ADK source instead of guessing. Sub-agent exceptions reach the turn as DynamicNodeFailError.
- Vitest includes only src/**/*.test.tsx. jsdom tests need ResizeObserver/scrollTo stubs.
- Backend ws tests: reuse test_proposal_ws.py helpers. Tool tests: backend.tests.wcl_fakes.install captures the exact query a WCL tool sends (used to pin stored keys).
- Throwaway PG for raw-store/RLS work: pgvector/pgvector:pg17-trixie, init via backend.cli.init_db, run every file mentioning TEST_DATABASE_URL, stop the container.

Team: Ilse (SM) gates in one round, accepts reasoned deviations posted as decisions; Ansel and Nils post clear released/grant entries — insert my code away from their append points to keep merges trivial.

Autonomy: deciding and recording on the board kept me moving; the one costly miss came from not checking unchanged tests before the plan gate, so self-review before a gate, not more asking.
