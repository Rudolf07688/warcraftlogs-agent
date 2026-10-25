# Brief 020 — Fetch persistence foundation (plan F3 / 020)

| Field | Value |
|---|---|
| Feature number | 020 |
| Branch | `020-fetch-persistence` (set `GIT_BRANCH_NAME=020-fetch-persistence` for `/speckit-specify`) |
| Spec dir | `specs/020-fetch-persistence/` |
| Worktree | `/home/rudolf/dev/wcl-worktrees/dev-a` (track A) |
| Base ref | `sprint-2026-10-25` tip **after 018 merged** (the worktree is detached there) |
| Model / effort | opus / medium |
| Shortcut stories, in order | sc-127 (2), sc-128 (2) |
| Peer developer | `dev-b-019-v2` (track B, sidebar & conversations) |
| Scrum master | `scrum-master` (your only channel upward) |
| Plan | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/plan.md` (section F3 / 020, plus the "Same-file overlaps" table) |
| Ownership ledger | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/ownership.md` |
| Decisions | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/decisions.md` (entry 6: the table is global, not tenant-scoped) |

## Plan section (verbatim)

## F3 / 020 — Fetch persistence foundation (Track A, second)

- **Stories, in order:** sc-127 (2) Raw WCL fetch schema; sc-128 (2) Write-through
  persistence of every WCL fetch.
- **Why now:** these open epic 103 ("Every fetch stored in the DB"), which is the
  foundation for sc-129..132, epic 100 (semantic search) and epic 106 (Raids page
  data). Stored data starts building up the day this ships.
- **Complexity:** medium.
- **Footprint:** the `wcl_agent` WCL client and cache (new paths after F1),
  `backend/app/db/models.py`, migration `0013`, `backend/app/db/repository.py` (or a
  new small repository module).
- **Depends on:** F1.
- **Acceptance criteria:**
  1. Migration `0013` creates a raw-fetch table (query key, operation name, params
     JSONB, report code (nullable, indexed), fetched_at, payload JSONB), and upgrade
     and downgrade both work.
  2. Every successful GraphQL response through the single WCL client is persisted,
     including cache-miss fetches from tools, guides, the welcome/recent-raids
     service and background jobs.
  3. Persisting never blocks or slows the tool call: it runs off the event loop and is
     bounded (for example a bounded queue or task set, with overflow dropped and
     logged). A persistence error is logged, never raised to the agent or the user.
  4. Repeated identical fetches of a finished report upsert one row instead of piling
     up duplicates. Live, still-changing data may be stored again, with its new
     `fetched_at`.
  5. The table is global, not tenant-scoped, matching the shared Redis WCL cache from
     feature 014 (Warcraft Logs data is public).
  6. Tests cover the write-through, the error isolation (the DB is down and the fetch
     still succeeds), and the upsert. Nothing reads from the table yet; DB-first reads
     are sc-129, next sprint.

## Context

- Feature 018 just restructured `wcl_agent` into sub-packages (`client/`, `cache/`,
  `tools/`, `guides/`, `llm/`, `game/`). The map is in
  `specs/018-wcl-agent-subpackages/contracts/module-map.md`. The shared GitNexus index
  (owner's checkout) still has the **old** paths: re-index your worktree first
  (`node /home/rudolf/dev/warcraftlogs-agent/.gitnexus/run.cjs analyze --index-only`), or
  confirm `wcl_agent` paths by text search.
- The single WCL client is `wcl_agent/client/wcl_client.py`. The shared Redis cache
  (feature 014) is `wcl_agent/cache/cache.py` (`get_or_load`). Persist only the
  responses that actually reach the WCL API (cache misses), as AC 2/3 and the plan's
  risk table say.

## Tentative footprint (becomes a grant after `/speckit-plan`)

- `wcl_agent/client/**` and `wcl_agent/cache/**` (write-through hook). F5 (022) adds its
  M+ query here only after you merge.
- **New** `backend/app/repositories/raw_fetches.py`. Follow the existing
  `backend/app/repositories/` pattern for new tables. Do **not** edit
  `backend/app/db/repository.py`, which 019 holds.
- `backend/app/db/models.py`, one new `RawFetch` class appended at the end. **This file
  is currently granted to 019**, which edits `Conversation`. I'll transfer it to you
  once 019 confirms its edits there are final, so the two of you hold it one after the
  other, never at the same time. Your hunk is a new class at the end of the file and
  doesn't touch `Conversation`. Until the transfer, put the model last in your tasks.
- Migration `backend/migrations/versions/0013_<name>.py`. **You hold slot 0013** with
  `down_revision = "0012_conversation_pin_title"` (019's migration). If you're ready to
  merge before 019, tell me: I'll either hold your merge until 019 lands or have you
  re-point to `0011_guide_content_types`.
- `backend/app/config.py` if you need a setting (e.g. queue bound). 018 released it.
- New test files (`backend/tests/test_raw_fetch_*.py`).
- **Not yours:** `backend/app/db/repository.py`, `backend/app/schemas.py`,
  `backend/app/api/ws.py`, `backend/tests/conftest.py` (019 phase 2), `wcl_agent/llm/**`
  (F4), `CLAUDE.md`, `AGENTS.md`, `todo.md`, `.specify/*`.

## Notes from the scrum master

- Concurrency is the risky part. In the plan, describe the background writer: who owns
  the task, the bound and the overflow policy, shutdown behaviour (lifespan: flush or
  drop, and how long), and how it works in CLI and test contexts that have no app
  lifespan. It must never block or slow the tool call. Test "DB down, fetch still
  succeeds".
- Upsert key: define "finished report" precisely (the cache already has finality helpers
  in `wcl_agent/cache/normalize.py`; reuse them, constitution I).
- Ports for any live check: app 18018, Postgres 15418, Redis 16318 (your own
  `docker run --rm` containers, no compose, no owner .env). Migration up, down and up on
  real Postgres is expected (JSONB).
- Shortcut: move sc-127 to In Progress when you start, and sc-128 when its work starts.
