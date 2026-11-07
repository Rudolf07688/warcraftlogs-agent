# Fix brief 070-fix-browse-stack (seat dev-1, Ansel), tier S, opus medium

QA fix round of sprint 2026-11-07. Fresh run. These are security findings in the 068 tools.

- **Branch:** `070-fix-browse-stack` from the sprint tip `894274d` (`git -C /home/rudolf/dev/wcl-worktrees/dev-d switch -c 070-fix-browse-stack 894274d`).
- **Worktree:** /home/rudolf/dev/wcl-worktrees/dev-d
- **Footprint:** `.claude/team/browse.py`, `.claude/team/stack.py`, `backend/tests/test_team_browse.py`, `backend/tests/test_team_stack.py`, and your two 068 fact files if a fact changes.
- **Stories:** fixes under sc-533 (stays Under Review).
- **Reports (cited sections only):** /home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-07-sweep/security.md (SEC-001, SEC-003, SEC-004) and /home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-07-sweep/bugs.md (BUG-005).

## Fix (each gets one contract test that bites)

1. **SEC-001 (Medium):** URL parser differential: `http://<A>\\@127.0.0.1:<port>/` passes `check_url` (Python urlsplit) but Chrome (WHATWG) goes to `<A>`, an external host or the owner's port 3000. Required: the guard decides on the URL as Chrome will parse it (e.g. refuse backslashes, userinfo and anything that isn't a plain `scheme://host:port/path`, or re-check the URL Chrome reports after navigation).
2. **SEC-004 (Medium):** only the first URL is checked; redirects, JS navigation, `eval:` steps and subresources can reach refused ports or IP-literal external hosts. Required: every request the page makes is held to the same loopback-and-port rule (e.g. the DevTools Fetch domain intercepting all requests and failing the rest), with a test that a redirect to a refused port is blocked.
3. **SEC-003 (Medium):** run from a checkout that has a `.env`, `up` and `down` make docker compose open and parse it through backend's and db's `env_file`, even when those services aren't selected (confirmed with Compose v5.3.1). The test cleanup at `test_team_stack.py:101` does the same. Required: stack.py never lets compose read a `.env` (e.g. refuse up and down in a checkout with a `.env`, or run compose on a project dir without one).
4. **BUG-005 (Medium, same function you touch for 2):** a Chrome process leaks when `launch()` fails after Popen. Kill it on every failure path.

## Rules

- D21: targeted tests; hand-off proof `check.py run backend/tests/test_team_browse.py backend/tests/test_team_stack.py --as ansel` RESULT on the committed head. One bite per guard.
- No credentialed calls, no owner's `.env` (you're fixing exactly that), stacks only through your own names, never `lead`.
- If `contract:stack-env` changes, post a superseding `decision` on it.
- No other changes; the other Lows are ticketed by Maren.
- After the merge Maren asks team-lead to re-run `live-check:068-browse` (the path changed). Put the exact command and EXPECT facts in your hand-off.
- Hand-off: about 15 lines, one line per finding with its test, plus your `Retro:` line.
