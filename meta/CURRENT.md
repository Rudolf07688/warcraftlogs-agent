# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-01 (end of sprint 2026-10-31c)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D17, proposals P1–P6, baseline table, change log).

## Where we are

- **Sprint 2026-10-31c finished:** 19/19 pts, local-first data (039) and small fixes (040),
  with a QA fix round split by author (041, 042). Branch `sprint-2026-10-31c` (tip 6bfaabe,
  code 6dd57e7), not merged to main yet. Cost per point 0.92, 78 minutes, zero escalations.
  Team report: `meta/sprints/2026-10-31c/team-report.html`.
- **Live pass done** on 6dd57e7. The live DB is at 0018 (backup in
  `.git/db-backups/pre-0018-2026-11-01.dump`). The app stack runs from the sprint worktree.
  New bug sc-302 (large-report chart turn ends without an answer).
- **New owner preferences:** 18 (team-lead owns `.claude/skills/`, D17) and 19 (small
  progress updates during sprints). First skills pass done: pruned unused stacks, applied
  the sprint's learnings.

## Open threads

- Owner: merge `sprint-2026-10-31c` into main? 9 stories Under Review in iteration 290.
- After the merge: remove worktrees, restart the stack from main, re-index GitNexus.
- Memory quality review after a few sprints (open question 3).

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
