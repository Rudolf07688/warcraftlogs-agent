# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-01 (sprint 2026-11-01 finished: merged, pushed, P7 adopted)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D18, proposals P1–P8, baseline table, change log).

## Where we are

- **Sprint 2026-11-01 (semantic knowledge base) is finished:** merged at 497e117 and
  pushed with the wrap-up commits. 33/33 pts, 11 stories Under Review (iteration 161),
  plus sc-335 (tool labels). The stack runs from main.
- **DB:** pgvector/pgvector:pg17-trixie at 0019, KB backfilled (440 chunks). Backup:
  `.git/db-backups/pre-pgvector-20261101-1229.dump`.
- **Team report:** `meta/sprints/2026-11-01/team-report.html` (1.18 M/pt, coordination 26%).
- **D18 (P7 adopted):** the merger runs one scoped `qa-security` pass per security-core
  hand-off, prompted from the code; in `product-owner.md` §3 and `scrum-master.md` §4.
  First real test next sprint: watch whether the end sweep still finds Highs.

## Waiting on the owner

1. Which stories to move to Done (32 Under Review: iterations 161, 266, 290; sc-335).
2. Maren's housekeeping: four active Team 1 iterations; default workflow still The Classic.

## Open threads

- New bug sc-334 (397k-token request from truncated tables) is a good next-sprint candidate.
- P8 (split lead spend by activity) still a proposal.

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
