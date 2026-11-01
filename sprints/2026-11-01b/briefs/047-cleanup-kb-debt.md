# Brief 047-cleanup-kb-debt (stream B)

From Maren (product owner, `maren` on the board). Sprint 2026-11-01b, steer = board #1.

- **You:** seat `dev-1` (Ansel). Parallel developer: Nils (`dev-3`, feature 046, worktree dev-a).
- **Feature / branch:** `047-cleanup-kb-debt`
- **Tier:** M — one Spec Kit pass (specify → plan → tasks → implement), no gates in the middle.
  Answer your own clarify questions; post them as `answer` keyed `clarify:047-<topic>`.
  Six small stories: keep the spec lean (one user story per ticket, ACs below as the FRs).
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b` (detached at `dd0c2df`).
  Branch from the sprint tip: `git -C /home/rudolf/dev/wcl-worktrees/dev-b switch -c 047-cleanup-kb-debt sprint-2026-11-01b`.
- **Base ref:** `sprint-2026-11-01b`.
- **Security-core:** yes (tenant visibility of stored reports, the private-report tombstone, the
  shared breaker and single-flight path). A scoped `qa-security` review runs at your hand-off;
  Highs/Mediums come back to you as your one rework round.
- **Migration:** `0020` is yours if sc-324 needs an index: `revision = "0020_<short_name>"`,
  `down_revision = "0019_kb_chunks"`. No other migration this sprint. sc-322 has **no** migration
  (owner's choice).
- **Owner's line:** "Evolution is key." Small, verifiable steps; no scope creep.

## Stories (order as listed; sc-336 first; drop sc-255 if short)

Move each story to In Progress (`500000008`) when you start it and to Under Review (`500000023`)
in your hand-off. Never Done.

### sc-336 Tests read the real .env (2) — first
`backend/app/config.py:25` calls `load_dotenv()` at import time and `:31` sets
`env_file=".env"`, so `env -i` runs in the main checkout pick up live provider settings (21
failures, live Model Garden calls). `wcl_agent/cli.py:62` also calls `load_dotenv()` (CLI entry
point: fine as is unless tests import it on a path that runs it).

Acceptance criteria:
1. The test suite never reads `.env`: no import-time `load_dotenv()` on any path the tests import, and `Settings` ignore `env_file` under tests.
2. A guard test proves it: with a `.env` holding a sentinel value in the working directory, neither `Settings()` nor `os.environ` contains the sentinel during the suite.
3. The suite gives the same result in a checkout that holds a `.env` as in one that doesn't — prove it with a fake `.env` in your worktree. **Never read the owner's real `.env`.**
4. The app (docker, `uvicorn` dev run, CLI) still loads `.env` as before; say where in the spec/quickstart.

### sc-322 Private report comes back after a race (2)
`backend/app/services/fetch_persistence.py` (`_tombstones`, `_bury`, `_stale`). A report found
private by a **summary** fetch gets no tombstone, so a table request already under way writes the
row back and the old grant serves it again. **Owner chose the in-memory guard:** keep the
per-process tombstone, extend it, and make the spec match.

Acceptance criteria:
1. Every gone/private signal, including a summary fetch that finds the report private, tombstones the code, so a request already under way cannot write the row back.
2. `specs/045-local-data-reads/spec.md` FR-010 describes the in-process tombstone as built (per process, TTL, cap, lost on restart, accepted for one uvicorn worker); spec and code agree.
3. A test reproduces the race (summary finds private while a table fetch is in flight) and shows the stale write is dropped and the old grant can't serve the row.
4. No migration.

### sc-323 One slow read trips the shared breaker (1)
`backend/app/services/raw_fetch_reads.py` (`Breaker`, probe timeout, 30 s).

Acceptance criteria:
1. A single timeout on a slow stored read, or a short wait for a pool connection, does not open the shared breaker; it opens only on connection errors or N consecutive timeouts (N is yours, documented).
2. Tests: one slow read → stays closed; N consecutive timeouts → opens; a connection error → opens.

### sc-324 Stored-reports lookup is lax and slow (2)
`backend/app/agent_tools/stored_data_tools.py` `list_stored_reports_for_character`,
`backend/app/repositories/raw_fetches.py` `list_visible_summaries`.

Acceptance criteria:
1. The lookup selects rows by a server-fixed set of operations and exact report codes only; nothing the model passes chooses the operation, and rows with inexact codes are excluded (the 039 rule).
2. The query is bounded: an index or lookup column serves it (migration 0020 if needed), a statement timeout applies, and only the needed fields are read instead of up to 200 full payloads.
3. Tests: a row with an inexact code or a non-allowed operation is never returned; a Postgres test shows the bounded read (plan uses the index, or payload bytes read are bounded).
4. The 039 guard test in `test_raw_store_visibility.py` stays unchanged and green; reuse `fetch_visible_clause`, don't restate the rule.

### sc-326 Local-answer rate overcounts (1)
`wcl_agent/client/wcl_client.py` (`note_external_call` at ~596/605), `wcl_agent/cache/cache.py`
(~931–1010, `_Turn`, `set_refresh_actor`), `backend/app/api/ws.py` (~310 preamble before
`set_refresh_actor` at ~325).

Acceptance criteria:
1. A turn that joined a shared in-flight WCL load (same-process single-flight, or waited on another process's lock) counts as external, not local.
2. WCL calls made while building the turn preamble count for that turn.
3. Tests for both.

Note: Nils's sc-339 adds a server-side pre-fetch on the recent-raid click that runs outside any
turn. A kickoff turn that joins that pre-fetch's in-flight load should count as external under
your rule — that's correct, no special case.

### sc-255 Chat message numbering race (2) — drop first if short
`backend/app/db/repository.py` `_next_seq` (max(seq)+1 under `uq_message_conv_seq`).

Acceptance criteria:
1. Two concurrent `add_message` calls on the same conversation both succeed, with distinct consecutive `seq`.
2. A real-Postgres race test (`pg.py`, two concurrent sessions) proves it and fails on the old code (`mutate.py`).
3. The SQLite path still works; RLS/tenant scoping of `add_message` is unchanged.

## File footprint (board `owner:` keys; touch nothing else)
- `backend/app/config.py`, `backend/tests/conftest.py`, `wcl_agent/cli.py` (only if needed)
- `backend/app/services/fetch_persistence.py`, and wherever the summary-fetch private signal is
  raised in `wcl_agent/client/` or `wcl_agent/cache/` (yours)
- `specs/045-local-data-reads/spec.md` (FR-010 only)
- `backend/app/services/raw_fetch_reads.py`
- `backend/app/agent_tools/stored_data_tools.py` — **except the `get_stored_fight_table` hunk
  (~line 169)**, which Nils changes to call his compact table projection. Keep clear of it.
- `backend/app/repositories/raw_fetches.py`, `backend/app/db/models.py` (index only),
  `backend/migrations/versions/0020_*.py`
- `wcl_agent/client/wcl_client.py`, `wcl_agent/cache/cache.py`, `backend/app/api/ws.py`
- `backend/app/db/repository.py`
- New test files under `backend/tests/` / `tests/`; `specs/047-cleanup-kb-debt/`
- Not yours: `wcl_agent/tools/report_tools.py`, `wcl_agent/agent.py`, `backend/app/agent_runner.py`,
  `backend/app/api/raids.py`, `backend/app/kb/*` (Nils's).

## Hand-off
Board `handoff` plus your final result: branch, commits, files, `check.py` RESULT and RECEIPT
lines (full suite **with `--pg`**, committed tree, 0 skipped), risks, and the AC-by-AC mapping
with the test that proves each. Anything for team-lead's live pass: board `question` keyed
`live-check:047`.
