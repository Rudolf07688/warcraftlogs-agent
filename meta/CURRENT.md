# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-22 (P17 built, first 1:1 done)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D22, proposals P1–P16, baseline, change log).

## Where we are

- 2026-11-22: main pushed at 883f5a9 (sprint 2026-11-20 + the 11-20 retro rules, which
  landed after Maren's seat review; see the change log). Owner marked all 32 Under Review
  stories Done (the nine 11-20 stories plus older Raids, onboarding, portraits, telemetry).
  Board: nothing in Under Review.
- Next app work, my recommendation to the owner: a chat-reliability sprint from the 11-20
  QA follow-ups sc-580..587 (~17 pts; Gemini empty STOP answers sc-586 first, Claude output
  budget sc-580, history cache rewrite sc-581), one developer straight through, QA sweep at
  the end. Owner hasn't said go yet.
- Cost 1.08 M/pt on 11-20, the cheapest app sprint so far (team report
  `meta/sprints/2026-11-20/team-report.html`).

## In discussion now

- **P17 built and first run.** `member.py goal` + wrap-up step 10 "Teach"; Nils's 1:1 done (goal 1:
  volume test at the bound); bounds now in briefs (PO) and developer hard rule 11; sc-597
  for a shared volume-test fake. Next: follow up dev-3 `unbounded` at the next wrap-up.

## Next meta session

1. Seat review (P16 step 5) of the 11-07b retro proposals plus my `board.py … --instead`
   decision field.
2. P16 steps 2–4 (lessons that fire via hooks, fewer tools, cost per point by stream type).

## Open with the owner

- Board tidy-up: sc-534 now in iteration 576; iterations 536/553/472 still open.
- Wipe the pre-fix Mimir series? (local only)
- Gemini Flash list price changes 2027-01-01 (pricing.yaml commit that day).

## How to resume

1. Read `meta/README.md`, then this file, then P16 in `meta/team-optimisation.md`, then
   `meta/sprints/2026-11-20/team-report.html` (retro lines).
2. Owner preferences: `meta/owner-preferences.md`.
