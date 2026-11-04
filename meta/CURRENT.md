# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-04 (sprint 2026-11-04b wrapped, merge question open)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D19, proposals P1–P11, baseline, change log).

## Where we are

- Sprint 2026-11-04b (Telemetry 2, epic 396): 24/24 pts, 9 stories Under Review in iteration
  442. Sprint branch `sprint-2026-11-04b` tip 17f081c, suite 2215 passed, archdocs 0 problems.
  Not merged, not pushed. Reports: sprint worktree `sprints/2026-11-04b/{plan,sprint-report}.html`,
  team report `meta/sprints/2026-11-04b/team-report.html`. Baseline row added (1.30 M/pt).
- Telemetry 1 stories and the 24 older Under Review stories: Done on the owner's word 2026-11-04.
- The local stack currently runs from the sprint worktree (`-p warcraftlogs-agent`, symlinked
  `.env`); after the merge, re-run compose from main and remove the symlink with the worktrees.
- Sprint facts pushed with the sprint branch's teamstats (seat cost exists only there until merge).
- Lessons this sprint (in lead.md): proofs on real-shaped data, render checks taller than the
  page, search Shortcut before filing, run tools from the branch that has the change.

## Open with the owner

1. Merge `sprint-2026-11-04b` into main locally (and push?).
2. Move the 9 Telemetry 2 stories to Done (owner's call).
3. Longer-lived Google credentials (service account) for live passes; offered to draft.
4. Wipe the pre-fix Mimir series? (local only)

## For the next sprint (mine)

- Telemetry 3 (epic 397, ~20 pts) plus follow-ups sc-462/463; qa-deferred sc-458..461, sc-471.
- Gemini Flash list price changes 2027-01-01 (pricing.yaml commit that day).
- Close iteration "Sprint 2026-11-04" (425) on the board; old Mimir/OTel caveats stand.
- Candidates: "Every chat request starts at about 23k prompt tokens" (sc-367), chat input locked
  after a drop (sc-376), semantic search always down (sc-428).

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
