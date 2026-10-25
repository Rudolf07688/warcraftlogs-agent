# Brief 022 — Welcome chat: at most 6 raids + 6 M+ runs (plan F5 / 022)

| Field | Value |
|---|---|
| Feature number | 022 |
| Branch | `022-welcome-mplus` (set `GIT_BRANCH_NAME=022-welcome-mplus` for `/speckit-specify`) |
| Spec dir | `specs/022-welcome-mplus/` |
| Worktree | `/home/rudolf/dev/wcl-worktrees/dev-b` (track B) |
| Base ref | `sprint-2026-10-25` tip after 019 merged (the worktree is detached there) |
| Model / effort | sonnet / high |
| Shortcut stories | sc-153 (3) |
| Peer developer | `dev-a-020` (track A, fetch persistence; it owns `wcl_agent/client/wcl_client.py` until it merges) |
| Scrum master | `scrum-master` (your only channel upward) |
| Plan | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/plan.md` (section F5 / 022, plus the "Same-file overlaps" table) |
| Ownership ledger | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/ownership.md` |
| Decisions | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/decisions.md` |

## Plan section (verbatim)

## F5 / 022 — Welcome chat: at most 6 raids + 6 M+ runs (Track B, second)

- **Stories:** sc-153 (3) Welcome chat: max 6 raids + 6 M+ runs.
- **Complexity:** medium (a new WCL query for the character's recent Mythic+ runs).
- **Footprint:** `backend/app/services/recent_raids.py`,
  `backend/app/services/recent_raid_types.py`, `backend/app/api/recent_raids.py`, the
  `wcl_agent` client/queries (new paths; after F3 has merged),
  `frontend/src/components/WelcomePanel.tsx`, and possibly migration `0014` if the
  runs are stored alongside the raids (feature 013 stores recent raids because they
  don't change).
- **Depends on:** F1. Its WCL client edits wait for F3.
- **Acceptance criteria:**
  1. The welcome panel shows at most 6 recent raids and at most 6 recent Mythic+ runs
     for the user's characters, each list most recent first. With no M+ runs, only the
     raids show, with no empty section or error.
  2. Each M+ run shows at least the dungeon, key level, date and whether it was timed,
     in the same visual style as the raid entries.
  3. Clicking an M+ run opens a new chat with an M+ review kickoff prompt, the same way
     clicking a raid does today (feature 013 flow).
  4. M+ data is fetched through the single WCL client and its cache, so it gets the
     Redis cache and F3's write-through. It follows feature 013's async/background
     pattern, so the welcome page never waits on Warcraft Logs.
  5. Tests cover the 6+6 caps, the ordering, the no-M+ case and the kickoff prompt,
     with WCL responses faked.

## Context

- Feature 013 built the welcome panel and the async recent-raids flow:
  `backend/app/services/recent_raids.py` (`fetch_listed_reports`, `run_recent_raid_refresh`,
  `maybe_start_refresh`), `recent_raid_types.py`, `api/recent_raids.py`, and the
  `RecentRaid*` tables. Read `specs/013-*` first. Reuse that pattern (constitution I).
- Feature 018 restructured `wcl_agent` into sub-packages (`client/`, `cache/`, …). The map
  is in `specs/018-wcl-agent-subpackages/contracts/module-map.md`. The shared GitNexus
  index (owner's checkout) still has the old paths, so re-index your worktree first.
- 020 (fetch persistence) is adding a write-through to `wcl_agent/client/wcl_client.py`.
  Your M+ query must go through the same client, so it gets persisted (AC 4).

## Tentative footprint (becomes a grant after `/speckit-plan`)

- `backend/app/services/recent_raids.py`, `backend/app/services/recent_raid_types.py`,
  `backend/app/api/recent_raids.py`, `frontend/src/components/WelcomePanel.tsx`, plus
  `frontend/src/types.ts` / `frontend/src/api/restClient.ts` if the payload changes.
  These are free once 019 merges.
- Query text: `wcl_agent/client/queries.py` is free now. **`wcl_agent/client/wcl_client.py`
  is held by 020 until it merges.** If you need a new client method there, do it last,
  after 020 merges and you've rebased. Prefer a design that only adds a query in
  `queries.py` and calls the existing generic `query()`.
- Storage: if the M+ runs are stored like recent raids, you get migration slot `0014`
  (`down_revision = "0013_raw_fetches"`), and `backend/app/db/models.py` (append only)
  after 020 merges. Your plan must say whether storage is needed. Prefer no new table if
  the existing refresh/caching pattern covers it (constitution III).
- `frontend/src/App.tsx`: only if needed, after 019 merges (it's free then).
- New tests: `backend/tests/test_recent_mplus*.py`, or additions to
  `test_recent_raids.py` (that file is free).
- **Not yours:** `wcl_agent/llm/**`, `backend/app/agent_runner.py`, `backend/app/api/ws.py`
  (F4/021), `CLAUDE.md`, `AGENTS.md`, `todo.md`, `.specify/*`.

## Notes from the scrum master

- The UI goes through the shadcn MCP (constitution VII). Match the raid entries' visual
  style, then run the audit checklist. Icons come from `react-icons` only.
- The WCL M+ data model is non-trivial (Mythic+ "runs" are reports or fights with
  keystone levels). Put the exact GraphQL query in the plan, and check it against the
  schema the client already uses. No live WCL calls in tests: fake the responses (AC 5).
- Ports for any live check: app 18019, Postgres 15419, Redis 16319 (your own
  `docker run --rm` containers, no compose, no owner .env).
- Shortcut: move sc-153 to In Progress when you start.
- Reply "ACK" to every grant or approval before you go idle.
