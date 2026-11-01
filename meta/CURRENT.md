# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-01 (retro on sprint 2026-11-01b with the owner)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D19, proposals P1–P11, baseline, change log).

## Where we are

- Sprint 2026-11-01b merged and pushed (89d9355). 20/20 at 1.03 M/pt; P9 held on every
  measure. Report: `meta/sprints/2026-11-01b/team-report.html`; per-agent data:
  `meta/sprints/2026-11-01b/usage.txt`; board export alongside.
- Retro in progress. The owner asked: how did the team do, better/worse, what would I do
  differently, how will I evolve it. My answer:
  - Better: process discipline (P9), almost no messages, PO in planning, big product win.
  - Worse: dearer than the earlier tier-M sprints (0.83, 0.92); the QA High came from our own
    rework; two timing flakes; my planning claim and bare ids were corrected.
  - Evolve: P10 (lighter PO admin in tier M), the liveness line now in `product-owner.md`,
    expected-answer checks in `livecheck.py`, fresh session per sprint.
- Owner: "Go ahead with both, and commit it". Built and committed: P10 (measured first:
  Shortcut re-reads 36% + report copying 10% of Maren's context, so `report.py`, read-once
  tickets, one owner glob per stream) and P11 (`livecheck.py` judges answers via EXPECT).
  Trial both next sprint; targets in team-optimisation.md.

## Open with the owner

1. Longer-lived Google credentials (service account) for the live pass; offered to draft.
2. Session boundaries: one session per sprint, separate meta sessions (this session ran
   planning → sprint → merge → meta and needed a compaction: evidence for the trial).

## Mine, not yet done

- Close stale Shortcut iterations 161 and 290. The 10 stories in iteration 338 are Under Review.
- Delete the merged local branches 046–049 and sprint-2026-11-01b.

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
