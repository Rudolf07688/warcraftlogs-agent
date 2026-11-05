# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-05 (sprint 2026-11-05 Telemetry 3 wrapped; merge question with the owner)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D19, proposals P1–P12, baseline, change log).

## Where we are

- Sprint 2026-11-05 (Telemetry 3) wrapped: 26+2 pts on sprint-2026-11-05 tip 9a5eabf, docs gate
  clean, live pass + re-check done; team report meta/sprints/2026-11-05/team-report.html
  (1.61/pt, P12: PO cold 2.05 -> 0.06, sprint cold 1.92). Waiting on the owner's merge answer;
  after merge: team-launch skill live-pass env + restart step, Mimir naming fact to developer.md.

## Meta session 2026-11-05 (done)

- Measured where Telemetry 2's extra cost went: P12 in team-optimisation.md. Build got
  cheaper per point; the extra is fix rounds, docs pass run twice, PO cold-cache wakes, lead.
- Owner go: built lever 1 (`board.py wait --since N --warm`, 25-min window; probe showed the
  cache stays warm, 2 calls per tick; saving ≈ 0.7/sprint) and lever 2 (docs pass once,
  after every fix round). `usage.py --cold` measures it at the next wrap-up. Lever 3 (split
  big fix rounds) stays a measurement.
- Next sprint, first trial: arm PO/SM waits with `--since N --warm`; check at wrap-up: cold
  weight < 1.5 (`usage.py --cold`), PO cost per point (0.26 on 11-04b), docs ≤ 1.8.

## Open with the owner

1. Longer-lived Google credentials (service account) for live passes; offered to draft.
2. Wipe the pre-fix Mimir series? (local only)

## For the next sprint (mine)

- Telemetry 3 (epic 397, ~20 pts) plus follow-ups sc-462/463; qa-deferred sc-458..461, sc-471.
- Gemini Flash list price changes 2027-01-01 (pricing.yaml commit that day).
- Candidates: "Every chat request starts at about 23k prompt tokens" (sc-367), chat input locked
  after a drop (sc-376), semantic search always down (sc-428).

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
