# Brief 052-turn-and-startup-hardening (stream C)

From Maren (product owner, `maren` on the board). Sprint 2026-11-02, steer = board #1
(fully autonomous: no owner questions at any point; decide and record on the board).

- **You:** seat `dev-2` (Tomas). Parallel developers: Nils (`dev-3`, feature 050, worktree dev-a)
  and Ansel (`dev-1`, feature 051, worktree dev-b).
- **Feature / branch:** `052-turn-and-startup-hardening`
- **Tier:** M: one Spec Kit pass (specify, plan, tasks, implement), no gates in the middle.
  Answer your own clarify questions; post them as `answer` keyed `clarify:052-<topic>`.
  Seven small, independent stories: keep the spec short, one commit per story.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-c` (detached at `3b5e3ca`).
  `git -C /home/rudolf/dev/wcl-worktrees/dev-c switch -c 052-turn-and-startup-hardening sprint-2026-11-02`
- **Base ref:** `sprint-2026-11-02`.
- **Security-core:** yes (shared store breaker across workspaces, a per-user rate limit, the secret
  key at startup). A scoped `qa-security` review runs at your hand-off; Highs/Mediums come back as
  your one rework round.
- **Migration:** none (Ansel owns migrations this sprint).
- **Spec dir:** `specs/052-turn-and-startup-hardening/`.
- **Watch:** sc-355 and sc-357 are state machines (breaker states, turn accounting). Write the
  edge-case tests first: concurrent probes, half-open trial, setup failure mid-turn, cancellation.

## File footprint (stay inside; ask on the board before touching anything else)
- `backend/app/services/raw_fetch_reads.py`, `backend/app/services/kickoff_prefetch.py`,
  `backend/app/api/raids.py` (the `investigate_raid` endpoint; `kickoff_prompt_for` is Nils's,
  shared file split by hunk), `backend/app/api/ws.py`, `wcl_agent/cache/cache.py`
- `backend/app/config.py`, `backend/app/main.py` (startup check only), `backend/app/auth/rate_limit.py`,
  `backend/app/tenancy/context.py`, `wcl_agent/llm/model_retry.py`, `.env.example`
- `specs/052-*/**`, tests: new files or files only you touch.
- Not yours: `backend/app/repositories/raw_fetches.py`, `backend/app/services/fetch_persistence.py`,
  migrations (Ansel); `wcl_agent/tools/report_tools.py`, `wcl_agent/agent.py` (Nils).

## Stories (order: 355, 332, 352, 357, 356, 270, 297; drop 297, 270, 332 in that order if short)
Move each story to In Progress (`500000008`) when you start it and to Under Review
(`500000023`) in your hand-off. Never Done. ACs below are mine, derived from each ticket.

### Raw-store breaker counts one turn's parallel timeouts as an outage (sc-355, 1)
Ticket: `raw_fetch_reads.py:89-94, :151-154`. "3 timeouts in a row" is process-wide: one turn's
burst of parallel probes (400 ms timeout, pool of 10) produces three together and opens the breaker
for every workspace for 30 s. A store that is slow for most reads but answers one in between never
opens, so each slow read costs the full timeout. Suggested fix: count timeouts over a time window
and across distinct turns (or a failure ratio), and cap probes per turn.
Acceptance criteria:
1. Timeouts from a single turn alone can't open the breaker (test: one turn, many parallel timeouts).
2. A mostly slow store opens the breaker even when an occasional read succeeds (test: e.g. a failure ratio over a time window).
3. A real outage still opens it as fast as today: connection errors, and timeouts from two or more turns inside the window.
4. Half-open trial behaviour unchanged (existing tests pass).

### Raw-store probe counters per operation (sc-332, 1)
Ticket: the sc-132 store counters are totals. Board decision #66 (keep probing for now) says to
revisit with 7 days of live numbers; a per-operation split (operation_name) answers it directly.
Acceptance criteria:
1. Hit/miss/skip counters are kept per WCL operation name (report family) as well as in total.
2. They appear wherever the totals are exposed today (log line or endpoint), with a test.

### No per-user limit on recent-raid investigate; pre-fetch while breaker open (sc-352, 1, security)
Ticket: `backend/app/api/raids.py` investigate_raid, `kickoff_prefetch.py` schedule(). The 10-minute
cooldown is per (workspace, report): one user can click every tracked/recent raid and start up to 11
WCL requests per raid plus a conversation row each, with no model cost. The pre-fetch also starts
while the raw-store breaker is open (warms nothing), and is scheduled before the endpoint's
transaction commits. Suggested fix: per-user rate limit on investigate (like
`guide_report_limiter`); skip the pre-fetch while the breaker is open; schedule after commit.
Acceptance criteria:
1. Investigate has a per-user rate limit (configurable, sensible default) answering 429 over the limit (test).
2. The pre-fetch is not scheduled while the breaker is open (a side-effect-free "is open" check on the breaker, not `admit()`; test).
3. The pre-fetch is scheduled only after the endpoint's transaction commits (test: a failing commit schedules nothing).

### Local-answer count edge cases and turn-setup reset in ws.py (sc-357, 1)
Ticket: `backend/app/api/ws.py:314-319` (turn starts before the preamble; setup commit failure leaves
the actor set and the turn open); `wcl_agent/cache/cache.py` (unshareable-load joiner counted
external although its own reload was local). A turn whose setup fails after `set_refresh_actor` is
counted as local at the next turn start. A turn that joins an unshareable load is counted external
even when its own reload is answered locally (the 047 spec edge case says the opposite). The actor
reset should sit in a `finally`; the final save can wait on card locks outside the turn's error
handling. Suggested fix: reset in `finally`, close the turn as "not counted" on setup failure, align
the unshareable case with the spec (or the spec with the code).
Acceptance criteria:
1. The refresh actor is reset in a `finally`; a turn whose setup fails is closed as not counted (test).
2. The unshareable-load joiner is counted the way the 047 spec says, or the spec is changed with the reason on the board (test either way).
3. The final save's failure is handled inside the turn's error handling (no unhandled exception, the turn still ends; test).
4. Liveness: no new lock or wait that a turn can block on behind another turn.

### App starts silently on the dev secret key (sc-356, 1, security)
Ticket: `backend/app/config.py:28-36, :85` (`secret_key="dev-insecure-change-me"`, default database
URL). With env vars missing the app starts with the dev secret and default DB URL, no warning.
Suggested fix: refuse to start with the dev secret when the public site is not localhost; log which
defaults are in use.
Acceptance criteria:
1. Startup fails with a clear message when the secret key is the dev default and the public site is not localhost/127.0.0.1 (test).
2. Local dev and the test suite still start without extra setup.
3. A warning names each insecure default in use (secret key, database URL), without printing secret values.

### One set_config round trip; cache parsed TRUSTED_PROXIES (sc-270, 1)
Ticket: `backend/app/tenancy/context.py:45` (two separate `set_config` calls),
`backend/app/auth/rate_limit.py:94` + `backend/app/config.py:280` (`trusted_proxy_networks` re-parsed
per call). Suggested fix: a single `SELECT set_config(...), set_config(...)`; parse TRUSTED_PROXIES once.
Acceptance criteria:
1. A tenant-scoped transaction sets both GUCs in one statement on Postgres (test asserts one execute; RLS tests still pass with `--pg`).
2. `trusted_proxy_networks` is parsed once per settings object (test).

### Both-limited wait budget counts only sleep time (sc-297, 1)
Ticket: `wcl_agent/llm/model_retry.py` (`_BOTH_LIMITED_BUDGET_S`, `generate_with_fallback`): the 10 s
shared budget counts sleep time only, not request time, so the real wait is about 11-16 s. Suggested
fix: a monotonic deadline that covers the requests too.
Acceptance criteria:
1. The budget is a monotonic deadline covering requests and sleeps; "both models are busy" comes within 10 s plus at most one in-flight request (test with a fake clock).

## Hand-off
Board `handoff` plus your final result: branch, commits, files, the `check.py` RESULT and RECEIPT
lines (use `--pg`), risks, AC mapping per story.
