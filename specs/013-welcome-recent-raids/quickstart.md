# Quickstart: Welcome Page with My Recent Raids

**Feature**: 013-welcome-recent-raids

How to run and verify the feature. Each section maps to a user story and its success criteria.

## Setup

```bash
uv sync --extra test
uv run alembic -c backend/alembic.ini upgrade head      # applies 0010_recent_raids
docker compose up --build                                # or run backend + vite dev server
```

You need `WCL_CLIENT_ID` and `WCL_CLIENT_SECRET` in `.env`, and at least one own character with public raid logs on the profile page.

New optional settings (the defaults are fine):

| Variable | Default | Meaning |
|---|---|---|
| `WCL_BACKGROUND_CONCURRENCY` | 2 | Background-lane slots out of `WCL_MAX_CONCURRENCY` (6) |
| `WCL_QUERY_TIMEOUT_S` | 75 | Overall cap per WCL fetch |
| `RECENT_RAIDS_REFRESH_MIN_S` | 900 | Minimum gap between refreshes per user (FR-013) |
| `RECENT_RAIDS_STALE_S` | 300 | A running refresh older than this can be claimed again (FR-026) |

`WCL_TOOL_THREADS` is removed in Phase C.

## Automated checks

```bash
uv run --extra test pytest -q                                   # full suite
uv run --extra test pytest -q backend/tests/test_recent_raids.py   # US1–US3
uv run --extra test pytest -q backend/tests/test_wcl_async.py      # US4: cache, single-flight, cancel, timeout, lanes
uv run --extra test pytest -q -m perf backend/tests/test_wcl_loop_lag.py   # SC-008
cd frontend && npx tsc -b && npx vite build
```

## Manual verification

### US1: see my recent raids (SC-001, SC-002, SC-005)
1. Sign in with a user who has one or more own characters. The welcome page shows skeleton cards, then up to 20 raids, newest first, within about 10 s.
2. Each card shows the zone, date and time, difficulty, your character(s) and "N/M bosses".
3. Add an alt that attended one of the same raids. After the next refresh, that raid shows **once**, naming both characters.
4. Reload. The list appears within about 1 s, with no skeleton.

### US2: click to investigate (SC-003)
1. Click a raid card. A new chat opens and Barnaby starts the bounded raid overview with no typing.
2. The raid now appears under tracked raids in the sidebar, and the chat appears under conversations.
3. **New chat** in the sidebar takes you back to the welcome page.

### US3: stored list and background refresh (SC-004, SC-006, SC-010)
1. Restart the backend and reload. The raids appear at once.
2. Check the backend logs: final raids get no detail query again. The `recentReports` list query runs at most once every 15 minutes.
3. Stop network access to WCL (or set a bad `WCL_CLIENT_SECRET`), clear the gate with `UPDATE recent_raid_refresh SET finished_at = now() - interval '1 hour'`, and reload. The stored raids still show, with a "Couldn't refresh" note. **Retry** schedules a new run.
4. Crash test: kill the backend while `recent_raid_refresh.status = 'running'`. Restart, wait 5 minutes, reload. A new run is claimed and finishes.
5. Two instances: run two backends on the same database and open the welcome page on both at the same moment. `recent_raid_refresh.run_id` changes once, and only one `recentReports` query is logged.

### US4: async WCL access (SC-007, SC-008, SC-009)
1. Start a tool-heavy turn (for example "compare me to the top 50 on every boss") and close the tab or cancel the turn mid-tool. Within 5 s, the WCL in-flight gauge in the logs (`wcl inflight=`) returns to its baseline.
2. With two browser tabs, start a tool-heavy chat in tab A while tab B (a user with 10 own characters) opens the welcome page. Tab A's tool calls start without delay, and the background lane never goes over 2 slots (`wcl lane=background in_use≤2` in the debug log).
3. During 4 concurrent tool-heavy turns, streaming stays smooth. The `perf` test above asserts a worst-case loop lag under 20 ms.
4. Regression: run each existing tool through a chat (rankings, report tables or events, character rankings, benchmark, cooldowns, chart) and the CLI (`uv run python main.py`). The results match what they returned before the migration.
