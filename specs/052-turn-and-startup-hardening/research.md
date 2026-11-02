# Research: Turn and startup hardening

- **Breaker rule (sc-355)**. Decision: sliding 60 s window of outcomes; open on ≥3 timeouts from
  ≥2 turns with timeouts ≥ half the outcomes; per-turn cap of 3 timeouts per window. Rationale:
  one turn's burst can't open it (AC1), a mostly slow store opens it despite an odd success (AC2),
  an outage across two turns opens after the same 3 timeouts as today (AC3). Alternatives:
  failure ratio only (one turn's burst would still open it); time-decayed score (more knobs).
- **Turn identity**. Decision: the cache's `_Turn` object (one per chat turn, already copied into
  tool contexts). Alternatives: `RequestIdentity.session_id` (per socket, not per turn).
- **Per-op counters (sc-332)**. Decision: extra fields `store_<outcome>@<op>` in the existing
  local metrics hash. Alternatives: a hash per op (more keys and pipeline slots in `read_stats`).
- **Commit before schedule (sc-352)**. Decision: explicit `await db.commit()` in the endpoint
  before scheduling; `tenant_session`'s own commit then has nothing to do. Alternatives: a
  background task after the response (FastAPI's dependency exit order differs across versions).
- **Abandoned turn (sc-357)**. Decision: a separate `abandon_turn()` rather than a keyword on
  `set_refresh_actor` (a dozen tests patch it with `lambda *_: None`).
- **Startup check (sc-356)**. Decision: a lifespan check, not a settings validator, so CLIs
  (`init_db`, alembic) and the test suite import settings unchanged.
- **Proxy parse cache (sc-270)**. Decision: `lru_cache` on the parse keyed by the string. A
  `cached_property` would keep a stale value when tests monkeypatch `trusted_proxies`.
- **Deadline (sc-297)**. Decision: a module `_clock` (monotonic) deadline passed into the retry
  loop. Rationale: request time counts; tests drive a fake clock without patching `time`.
