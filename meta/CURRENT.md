# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-04 (sprint 2026-11-04b merged, all Done; push pending)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D19, proposals P1–P11, baseline, change log).

## Where we are

- Sprint 2026-11-04b (Telemetry 2, epic 396): 24/24 pts, merged into main 2c7a67f on the
  owner's "close it all out"; 9 stories + epic 396 Done, iterations 425/442 end 2026-11-04.
  Worktrees and sprint/feature branches removed, QA reports copied to qa-reports/2026-11-04b*,
  stack recreated from main. Push to origin was blocked by the permission classifier: the
  owner runs `git push origin main` (35 commits ahead). Team report meta/sprints/2026-11-04b/.
- Telemetry 1 stories and the 24 older Under Review stories: Done on the owner's word 2026-11-04.
- Lessons this sprint (in lead.md): proofs on real-shaped data, render checks taller than the
  page, search Shortcut before filing, run tools from the branch that has the change.

## Open with the owner

1. Push main to origin (owner, after the classifier block).
2. Longer-lived Google credentials (service account) for live passes; offered to draft.
3. Wipe the pre-fix Mimir series? (local only)

## For the next sprint (mine)

- Telemetry 3 (epic 397, ~20 pts) plus follow-ups sc-462/463; qa-deferred sc-458..461, sc-471.
- Gemini Flash list price changes 2027-01-01 (pricing.yaml commit that day).
- Candidates: "Every chat request starts at about 23k prompt tokens" (sc-367), chat input locked
  after a drop (sc-376), semantic search always down (sc-428).

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
