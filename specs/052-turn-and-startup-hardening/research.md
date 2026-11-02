# Research: Turn and startup hardening

- **Breaker rule (sc-355)**. Decision: sliding 60 s window of outcomes; open on ≥3 timeouts from
  ≥2 workspaces with timeouts ≥ half the outcomes; a workspace with 3 timeouts in the window
  skips the store itself. Rationale: one workspace's burst can't open it (AC1), a mostly slow
  store opens it despite an odd success (AC2), an outage across two workspaces opens after the
  same 3 timeouts as today (AC3), and a single-workspace install still stops paying the timeout.
  Alternatives: failure ratio only (one burst would still open it); time-decayed score (more
  knobs).
- **Identity**. Decision: the workspace (tenant id from `current_identity`; public-only reads are
  one more key), remembered for at most 1024 workspaces apart from the ratio window. Superseded:
  the cache's `_Turn` object with one shared "no turn" bucket, because one account has many
  turns, tabs and pre-fetches (P7 SEC-001/003, board #59).
- **Per-op counters (sc-332)**. Decision: fields `store_<outcome>@<op>` in their own daily hash
  (`store_ops`), so the 045 totals and their exact-match tests stay unchanged; names from a fixed
  allowlist of the app's operations, any other as "custom" (P7 SEC-002). Alternatives: fields in
  the local hash (breaks the 045 tests), any query name (unbounded keys).
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
