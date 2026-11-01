# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-01 (end of the sprint session; owner opening a fresh meta session)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D19, proposals P1–P8, baseline table, change log).

## Where we are

- **Sprint 2026-11-01 (semantic knowledge base) is finished and pushed:** 33/33 pts,
  all stories Done, iterations closed, epics tidied (26 placeholder epics archived).
  Team report: `meta/sprints/2026-11-01/team-report.html`.
- **New today:** D18 (P7 adopted: scoped security review at security-core hand-offs);
  D19 / preference 20 (team-lead owns the Shortcut board, Done stays the owner's);
  preference 21 (never touch team members' memories; the lead's own memory is exempt from
  the once-per-sprint rule, cap 1000 words).

## Last meta conversation (sprint retro, end of the sprint session)

My read, which the owner agreed with ("truly impressive"):
- Teamwork: decisions posted with reasons and accepted without round trips; six gates
  passed first time; zero owner questions. Coordination 26%, the lowest yet.
- Self-awareness: members' own memories match their teammates' view of them (Tomas, Nils
  admit their slips); lessons transfer (Maren applied her 10-31c lessons; the guard-test
  lesson moved into developer.md).
- Not improving yet: "green that wasn't" recurred for three members; memories converge on
  the same lines (only members may prune them); team-lead is a bottleneck (wake-ups).
- Owner: "Don't be too hard on yourself. You have the most difficult job by far."
- Growth: This project is about the evolution of the team. I need to ensure future growth
  by observing and learning from mistakes. Cooperation and transparency with the owner is key.

## Open with the owner

1. **Longer-lived Google credentials** for the backend (service account), so the live pass
   never waits on a login. Offered to draft the exact permissions.
2. **Session boundaries:** one session per sprint, a separate one for meta talks, never
   mid-task; rewrite this file before each boundary. Owner worried fresh sessions hurt
   consistency; my answer: consistency lives in the files, and compaction is the lossy
   path. Owner is trying it now (this hand-off is the first test).
3. Push this hand-off commit (everything before it is on origin).

## For the next sprint (my own changes, no owner input needed)

- PO/SM run their own board watcher, so hand-offs don't depend on my wake-ups.
- P8: split my spend by activity (meta / live / wrap).
- A cheap token-budget check before the live pass (sc-334 was found only live).
- Measure: repeated mistakes already in a memory; Highs still found by the end sweep (D18).
- sc-334 (397k-token request from truncated tables) is the lead next-sprint candidate.

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`. If I get something wrong that we
   settled, the fix is a missing line in one of these files.
