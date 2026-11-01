# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-01 (sprint finished: pushed, P7 adopted, stories Done, iterations closed)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D19, proposals P1–P8, baseline table, change log).

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

## Board state (2026-11-01)

- All 41 Under Review stories moved to Done on the owner's word (iterations 161, 254, 266,
  290; includes the 9 epic-203 stories from 2026-10-26). All four iterations closed (end
  dates 10-31 / 11-01). No active iteration until the next sprint creates one.
- Team 1 default workflow is now Standard (owner switched it). 26 placeholder epics
  "2025-04-DD Epic" (ids 36–61) archived. 13 project epics remain; 100, 103, 105, 203 set
  to in progress (shipped work plus open backlog).
- D19: team-lead owns the board (iterations, workflows, epics, labels, Shortlist, meta
  notes there). Done stays the owner's.
  Epics 100 and 203 stay open: backlog QA tickets sc-318..329 and sc-214.

## Open threads

- New bug sc-334 (397k-token request from truncated tables) is a good next-sprint candidate.
- P8 (split lead spend by activity) still a proposal.

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
