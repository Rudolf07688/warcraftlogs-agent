# Quickstart: 022

1. `uv run --extra test pytest -q backend/tests/test_recent_mplus.py backend/tests/test_recent_raids.py`
2. `cd frontend && npm run build`
3. Live (app 18019, Postgres 15419, Redis 16319, own containers): register an own character with M+ logs, open the welcome page, see at most 6 raids and 6 runs; click a run, see the chat titled "M+ <dungeon> +<level>" start the review.

## Verification status (T025)

Automated: backend 1022 passed (baseline 1008 + 14 new), `npm run build` passes. Not done: the live check against real Warcraft Logs (no credentials in this sprint), so the keystone semantics (depleted `kill`, fight name as dungeon, `keystoneBonus` 0 for depleted) and the `wcl_cost` delta are open hand-off items. The shadcn MCP reported no configured registries in this worktree, so no registry item was added and no audit ran; the new card reuses the installed Item and Badge exactly as RaidCard does.
