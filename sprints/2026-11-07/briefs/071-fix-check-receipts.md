# Fix brief 071-fix-check-receipts (seat dev-2, Tomas), tier S, sonnet high

QA fix round of sprint 2026-11-07. Fresh run.

- **Branch:** `071-fix-check-receipts` from the sprint tip `894274d` (`git -C /home/rudolf/dev/wcl-worktrees/dev-b switch -c 071-fix-check-receipts 894274d`).
- **Worktree:** /home/rudolf/dev/wcl-worktrees/dev-b
- **Footprint:** `.claude/team/check.py`, `backend/tests/test_team_check.py`.
- **Stories:** fixes under sc-530 (stays Under Review).
- **Reports (cited sections only):** /home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-07-sweep/bugs.md (BUG-004) and /home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-07-sweep/security.md (SEC-010).

## Fix (each gets one contract test that bites)

1. **BUG-004 (Medium):** a receipt's area depends on the `--base` the developer chose; `verify` neither shows the base nor checks the area against the tree's real diff, so a branch with backend changes can get REUSE from an `area=config` receipt that ran only targeted tests. This breaks the promise of sc-530/526 that a receipt never overstates what ran. Required: `verify` prints the receipt's base and refuses REUSE when the branch touches an area the receipt didn't run (computed against the merge target: `--base`, default as `run`).
2. **SEC-010 (Low, same hunk):** `--base` goes into git argv without a guard, so `--base "--output=..."` writes a file. Refuse a base starting with `-` or pass it after `--` / via `rev-parse --verify`.

## Rules

- D21: targeted tests; hand-off proof `check.py run backend/tests/test_team_check.py --as tomas` RESULT on the committed head.
- If `contract:check-cli` changes, post a superseding `decision` on it; Maren updates the agent files.
- No other changes; the other Lows are ticketed by Maren.
- Hand-off: about 12 lines, plus your `Retro:` line.
