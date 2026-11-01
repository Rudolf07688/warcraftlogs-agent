# QA fix: Tomas (seat dev-2), worktree /home/rudolf/dev/wcl-worktrees/dev-c, branch qa-fix-tomas

Read `qa-fix-common.md` first.

## Finding to fix
**SEC-001 (Medium) = BUG-007**: `wcl_agent/cache/cache.py:549-581` (`_shared`). The cache-layer single-flight is keyed by the Redis key only. Workspace B arriving while workspace A's load runs joins A's task and receives a body the store served to A through A's grant (origin private, `mark_unshareable`). 045 scoped the client flight (`wcl_client.py` query, `key:scope`) but not this layer. The QA agent's scratch repro (two tenants, unlisted summary granted to A, WCL mocked to `report: null`; B alone gets None, `gather(A, B)` gives B the summary) is at `/tmp/claude-1000/-home-rudolf-dev-warcraftlogs-agent/a6f10fe7-0fa2-4b01-9ffb-b9917cd504bd/scratchpad/sec/test_join_probe.py`; turn it into a real regression test.

Fix it at the root, your choice: scope the cache flight by the fetch-source scope, or never hand an unshareable result to a joiner (the joiner loads for itself). Keep Redis sharing for public data and keep the existing single-flight benefit for same-scope callers. A tenant-less background caller must not receive a grant-only body either.

Read the rule from what the store returned (origin / unshareable), not from what was asked.

## Footprint
wcl_agent/cache/cache.py, wcl_agent/client/wcl_client.py only if the scope must be read from there, and tests.
