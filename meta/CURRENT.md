# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-07 evening (sprint 2026-11-07b launched)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D22, proposals P1–P16, baseline, change log).

## Where we are

- Retro 11-05b gave D21 (test the blocks, then the whole, once), D22 (GitNexus for code only)
  and P14; the team built P14 in sprint 2026-11-07. P15 (steady ~23 pts plus reserve stories)
  is in `product-owner.md` and first applies in the next backlog sprint.

## Sprint 2026-11-07 (P14): merged, pushed, Done, retro held

Merged 23c73aa and pushed (c732dd5 and later). All 16 stories (11-05b + 11-07) Done; the
iteration is renamed 2026-11-07. QA prompts and the qa-sweep skill installed as project copies
(source of truth) and in ~/.claude. Full-team retro round 1: `meta/sprints/2026-11-07/retro.md`.

## Sprint 2026-11-07b: running (launched 2026-11-07 ~19:30Z)

- P16 step 1 landed on main 516aa0d (seat-reviewed by Maren, Ilse, Vera); tool gaps in sc-552.
- App sprint ~23 pts: Raids page rework, onboarding to profile setup, character portraits,
  chat dropped-turn bug (sc-511), cheaper prompts (sc-514/515); reserves sc-538..542.
- Board `sprint-2026-11-07b`; branch base 516aa0d; worktrees in /home/rudolf/dev/wcl-worktrees.
  PO (Maren) launched as named teammate `product-owner`. Measure like 11-05b, by stream type.
- P16 steps 2-4 wait for their own meta sprint. Main has 10 local commits (unpushed).

## Open with the owner

3. Wipe the pre-fix Mimir series? (local only)
4. Gemini Flash list price changes 2027-01-01 (pricing.yaml commit that day).

## How to resume

1. Read `meta/README.md`, then this file, then P14 and D21/D22 in `meta/team-optimisation.md`,
   then `meta/sprints/2026-11-05b/retro.md`.
2. Owner preferences: `meta/owner-preferences.md` (26–28 are new).
