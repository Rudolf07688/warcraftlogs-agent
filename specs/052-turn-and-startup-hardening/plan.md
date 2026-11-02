# Implementation Plan: Turn and startup hardening

**Branch**: `052-turn-and-startup-hardening` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

## Summary

Seven small, independent hardening stories, one commit each, in the brief's order (sc-355,
sc-332, sc-352, sc-357, sc-356, sc-270, sc-297). No data model, no migration, no UI. Each story
starts with its failing edge-case tests (the state machines first: breaker, turn accounting).

## Technical Context

**Language/Version**: Python 3.12 (backend + `wcl_agent`)
**Primary Dependencies**: FastAPI, SQLAlchemy async, redis.asyncio, ADK (unchanged)
**Storage**: Postgres (RLS scope GUCs only), Redis metrics hashes (one more field family)
**Testing**: pytest (+ `check.py run --pg` for RLS), fake clocks, the ws test harness
**Target Platform**: Linux server (Docker Compose locally)
**Project Type**: web service
**Performance Goals**: no added round trip; sc-270 removes one per tenant transaction
**Constraints**: no new lock or wait on the turn path (sc-357 AC4); in-process limiters
**Scale/Scope**: ~10 source files, all in stream C's footprint plus one `schemas.py` hunk (grant asked, board #15)

## Constitution Check

- I Reuse: `InProcessRateLimiter` for investigate; `record_store` and `summarize_local` extended, not copied; `_turn` reused as the breaker's turn identity. PASS
- II Small steps: one story per commit, tests first. PASS
- III Simplicity: one sliding window (deque) replaces the consecutive counter; no new service. PASS
- IV Typed: per-op stats as a Pydantic model in `StoreStats` (needs the schemas.py grant). PASS
- V Async: no blocking calls added. PASS
- VI GitNexus: impact before each edit, detect-changes before each commit. PASS

## Design per story

**sc-355 breaker** (`raw_fetch_reads.py`, `cache.py`): `Breaker` keeps a deque of recent probe
outcomes `(t, turn, timed_out)` over `WINDOW_S = 60`. `timed_out(trial, turn)` opens when the
window holds ≥ `TIMEOUTS_TO_OPEN` timeouts from ≥ 2 distinct turns and timeouts are ≥ half of its
outcomes; a trial's timeout opens at once (unchanged). `succeeded` records an outcome (no reset of
a count). `admit(turn)` additionally returns None for a turn that already has `TIMEOUTS_TO_OPEN`
timeouts in the window (the per-turn cap). Turn identity: `cache.current_turn_key()` returns the
running `_Turn` object, or None (one shared "no turn" bucket). A side-effect-free `is_open()`
for sc-352.

**sc-332 per-op counters** (`cache.py`, `raw_fetch_reads.py`, `schemas.py` hunk): `record_store(outcome, op)`
also counts `store_<outcome>@<op>` in the local hash; `summarize_local` adds
`store.by_operation: {op: {hits, misses, not_visible, timeouts, hit_rate}}`; `StoreStats` gets
`by_operation: dict[str, OpStoreStats] = {}`. Ops are WCL GraphQL operation names (bounded set from
our own query constants), "anonymous" when unnamed.

**sc-352 investigate** (`raids.py` endpoint hunk, `rate_limit.py`, `config.py`, `kickoff_prefetch.py`):
`investigate_limiter = InProcessRateLimiter(per_minute=settings.wcl_investigate_per_minute)` (5),
checked first → 429 like the guide report endpoint. `schedule()` returns False while
`raw_fetch_reads.breaker.is_open()`. The endpoint `await db.commit()`s before `schedule()`.

**sc-357 turn accounting** (`ws.py`, `cache.py`): setup (conversation, user message, preamble,
the setup transaction's commit) wrapped so any failure after the turn opened calls
`cache.abandon_turn()` (clears the actor, closes the turn uncounted) and re-raises; the stream's
`finally` keeps closing a counted turn. `_save_answer` moves inside the turn's error handling: a
failure logs with a ref and sends the agent error frame. In `_shared`, a joiner of an unshareable
load returns its own reload before the shared load's external mark is applied.

**sc-356 startup** (`config.py`, `main.py`, `.env.example`): `insecure_defaults(settings)` lists
the names in use (`SECRET_KEY`, `DATABASE_URL`); `check_startup_secrets(settings)` warns once
naming them and raises `RuntimeError` for the dev secret with a non-local `SITE_URL` host. Called
first thing in `lifespan`.

**sc-270** (`context.py`, `config.py`, `rate_limit.py`): one `SELECT set_config(...), set_config(...)`;
`trusted_proxy_networks` reads an `lru_cache`d parse keyed by the string (tests that monkeypatch
`trusted_proxies` still see the new value), returning a tuple.

**sc-297** (`model_retry.py`): `generate_with_retry(..., deadline=None)` refuses a retry whose
wait would end past the deadline (`_clock()`, monotonic); the both-limited path sets one deadline
`_clock() + _BOTH_LIMITED_BUDGET_S` for probe and sibling, and skips the sibling's first request
when the deadline has passed. The sc-268 tests' `sleeps` fixture advances a fake `_clock`.

## Project Structure

```text
specs/052-turn-and-startup-hardening/  spec.md plan.md research.md data-model.md quickstart.md contracts/ tasks.md
backend/app/services/raw_fetch_reads.py   breaker (355), per-op record (332), is_open (352)
backend/app/services/kickoff_prefetch.py  breaker gate (352)
backend/app/api/raids.py                  investigate_raid limit + commit-then-schedule (352)
backend/app/api/ws.py                     turn setup / save handling (357)
wcl_agent/cache/cache.py                  turn key, abandon_turn, joiner, per-op counters (355/357/332)
backend/app/config.py, main.py, .env.example   startup check (356), investigate limit (352), proxies (270)
backend/app/auth/rate_limit.py            investigate_limiter (352)
backend/app/tenancy/context.py            one set_config (270)
wcl_agent/llm/model_retry.py              deadline (297)
backend/app/schemas.py                    StoreStats.by_operation (332, grant pending)
backend/tests/test_052_*.py               new tests
```

## Complexity Tracking

None.
