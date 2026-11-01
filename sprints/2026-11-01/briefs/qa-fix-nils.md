# QA fix: Nils (seat dev-3), worktree /home/rudolf/dev/wcl-worktrees/dev-b, branch qa-fix-nils

Read `qa-fix-common.md` first.

## Findings to fix
1. **BUG-002 (Medium)** `backend/app/kb/search.py:481-511` (+ `backend/app/agent_tools/kb_tools.py:218-222`): one timeout covers every relaxation pass, so a slow later pass throws away hits earlier passes found and the tool says "Knowledge search failed". Time-box per pass or by remaining budget; when a later pass times out, return the hits so far with a note (e.g. which relaxation didn't finish). The total time bound stays.
2. **SEC-006 (Low, but protects the owner's data; team-lead runs the eval this sprint)** `backend/evals/kb/__main__.py:39-52`: the guard against the app database compares URL strings, so `127.0.0.1` vs `localhost` (or `::1`, a socket URL) seeds the real database. Check the database itself after connecting (e.g. `current_database()` + `pg_control_system().system_identifier`, or `inet_server_addr()`/port, compared with the app DB when that is reachable), or require a marker only a throwaway eval DB has. Fail closed when unsure. Update `specs/044-kb-search/quickstart.md` if the recipe changes.

## Footprint
backend/app/kb/search.py, backend/app/agent_tools/kb_tools.py, backend/evals/kb/__main__.py (and other files in backend/evals/kb/ if needed), specs/044-kb-search/quickstart.md, and tests for these.
