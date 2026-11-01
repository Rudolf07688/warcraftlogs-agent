# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-01 late (session f6f1e132 ended by the owner; everything pushed)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D19, proposals P1–P11, baseline, change log).

## Where we are

- Sprint 2026-11-01b merged and pushed: 20/20 at 1.03 M/pt; P9 held on every measure. Report:
  `meta/sprints/2026-11-01b/team-report.html`; data in `usage.txt` and `board.jsonl` beside it.
- Retro done with the owner. Built, committed and pushed on the owner's go:
  - **P10 lighter PO admin:** `report.py` + `report-shell.html`; read-once tickets; one
    `owner:<glob>` per stream; batched ticket writes; a liveness line in the end-sweep prompt.
    `usage.py --context` measures it.
  - **P11:** `livecheck.py` judges answers against EXPECT (`--facts <code>`). Not yet run live.
- Clean state: local sprint branches deleted, no worktrees, origin/main up to date.
  Shortcut iterations 161 and 290 end 2026-11-01 and close themselves. The 10 stories in
  iteration 338 are Under Review; Done is the owner's call.

## Open with the owner

1. Longer-lived Google credentials (service account) for the live pass; offered to draft.
2. Session boundaries: one session per sprint, separate meta sessions. This session ran
   planning → sprint → merge → meta and needed a compaction, which is evidence for the trial.

## For the next sprint (mine)

- Start it in a fresh session. Trial P10: Maren's cost per point 0.17 → ≤ 0.12, Shortcut
  share 36% → < 15%, html share → ≈ 0. Read them with `usage.py --context`.
- Trial P11 in the live pass. Add EXPECT entries for the sprint's prompts.
- Candidate: "Agent picks the wrong last boss kill" (sc-365); P11 now detects it.

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
