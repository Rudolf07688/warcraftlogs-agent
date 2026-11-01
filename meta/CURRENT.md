# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-01 (sprint 2026-11-01 merged to main, wrap-up done)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D17, proposals P1–P8, baseline table, change log).

## Where we are

- **Sprint 2026-11-01 (semantic knowledge base) is merged to main** at 497e117, **not
  pushed**: 33/33 pts, 11 stories Under Review (iteration 161), plus sc-335 (tool labels).
  Worktrees and branches are removed; the stack runs from main.
- **DB:** pgvector/pgvector:pg17-trixie at 0019, KB backfilled (440 chunks). Backup:
  `.git/db-backups/pre-pgvector-20261101-1229.dump`.
- **Team report:** `meta/sprints/2026-11-01/team-report.html` (1.18 M/pt, coordination 26%).
- **Applied at wrap-up:** developer.md + team-launch updates (see the change log), lead
  memory rewritten (idle agents need wake-ups, pre-flights before the live pass).

## Waiting on the owner

1. P7: adopt the scoped security review (recommendation in team-optimisation.md P7)?
2. Push main?
3. Maren's housekeeping: four active Team 1 iterations; default workflow still The Classic.

## Open threads

- 31 stories Under Review (iterations 161, 266, 290) until the owner names Done.
- New bug sc-334 (397k-token request from truncated tables) is a good next-sprint candidate.

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
