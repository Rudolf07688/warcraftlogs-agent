# Fix brief 069-fix-board (seat dev-3, Nils), tier S, opus medium

QA fix round of sprint 2026-11-07. Fresh run: you didn't build this round's history; read only
what you need. Not security-core under D18, but these findings are exactly the failure the
067 brief named: a hook that hides an entry from the reader it concerns.

- **Branch:** `069-fix-board` from the sprint tip `894274d` (`git -C /home/rudolf/dev/wcl-worktrees/dev-c switch -c 069-fix-board 894274d`; the worktree has your 067 branch checked out, commit or stash nothing there, it is merged).
- **Worktree:** /home/rudolf/dev/wcl-worktrees/dev-c
- **Footprint:** `.claude/team/board.py`, `backend/tests/test_team_board.py`, the fact `.claude/team/facts/board-hook-reader-and-filter.md`.
- **Stories:** fixes under sc-531 (stays Under Review; don't move it).
- **Reports (read the cited sections only):** /home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-07-sweep/bugs.md (BUG-001, 002, 003) and /home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-07-sweep/security.md (SEC-002, SEC-005).

## Fix (each must get one contract test that bites)

1. **BUG-001 (High):** when the hook output is truncated (HOOK_MAX_ENTRIES / HOOK_MAX_CHARS), the newest entries are hidden, labelled "older", and the cursor skips past them for good. Required: no entry the reader should see is ever lost. E.g. advance the cursor only to the last entry actually shown (the rest arrive on the next tool call), or show the newest and point to `log --since` for the older ones while keeping them reachable. Your call; post it as `decision` key `scope:069:truncation`.
2. **BUG-002 / SEC-002 (Medium, one root cause):** the reader alias is learned from the last `--as <name>` anywhere on a Bash line that mentions board.py (quoted text, echo, `check.py --as`), keeps a trailing `.`, and can rename an agent mid-run, so it reads and moves another member's or a coordinator's cursor. Required: an agent's identity can't be taken over by text in a command. E.g. learn the alias only from an actual `board.py` invocation parsed with shlex (program + subcommand), validate the name against the roster, and never overwrite an alias once set. This happened twice live today (QA agents relabelled as ansel and `nils.`).
3. **BUG-003 (Medium) + SEC-005 (Low, same hunk):** `--to` isn't validated or normalised: a seat id (`dev-3`), a typo or a group name reaches nobody and the cursor skips it; newlines in `--to` forge board lines. Required: `post --to` accepts roster names and `all` (map seat ids to names if you like), refuses anything else with a clear error, and stores only clean tokens.

## Rules

- D21: targeted tests while building; hand-off proof `check.py run backend/tests/test_team_board.py --as nils` RESULT line on the committed head. Mutation only for these guards, one bite each.
- Test only in temporary git repos; never `board.py init/close` in a real checkout.
- If `contract:board-to` changes (e.g. --to validation), post a superseding `decision` on that key; Maren updates the agent files.
- No other changes. Lows not listed here are ticketed by Maren.
- Hand-off: about 15 lines, one line per finding with its test, plus your `Retro:` line.
