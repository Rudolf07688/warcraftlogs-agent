# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-07 late (retro + card round done; session cleaned for /clear)

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

## Next session: the owner kicks off a sprint ("so I can cleanly kick off the sprint after")

Session cleaned 2026-11-07: tree clean, no worktrees, stacks or active board, all agents done.

1. **Pre-flight:** start through `bin/claude-otel`, run `git status` and reindex GitNexus (stale
   at 23c73aa after meta-only commits), then check `context stream_response`.
2. **P16 step 1 before launch** (small, mine, so the sprint runs on the new rules). Read P16 in
   `meta/team-optimisation.md`.
   - Hostile inputs in briefs, and agreeing shared formats before launch as a standard step
     (product-owner.md).
   - The developer.md hard rule for security-core work and trusted artefacts, plus the
     card-round proposals in the last section of retro.md: consumer-side test, point of
     effect, replay real data.
   - Maren's wait also watches Ilse's questions.
   - Ilse's three scrum-master.md gaps, and cut its two rituals.
   - Take back the blanket D18 team-tool rule I added on 11-07 (D18 paragraph).
   - The affected seats review the diff read-only first (P16 step 5).
   - One backlog ticket for the tool gaps plus the `member.py lint` false matches,
     deduplicated against sc-538..542.
3. **Which sprint:** take the owner's steer. If none is given, recommend the **next app sprint**:
   about 23 pts of app work, with sc-538..542 as P15 reserve stories. Measure it like 11-05b,
   with cost per point by stream type, as the clean test of P14. P16 steps 2–4 (hook-injected
   hazards, about 5 entry points, stream types) wait for their own meta sprint. Cards stay small.

## Open with the owner

3. Wipe the pre-fix Mimir series? (local only)
4. Gemini Flash list price changes 2027-01-01 (pricing.yaml commit that day).

## How to resume

1. Read `meta/README.md`, then this file, then P14 and D21/D22 in `meta/team-optimisation.md`,
   then `meta/sprints/2026-11-05b/retro.md`.
2. Owner preferences: `meta/owner-preferences.md` (26–28 are new).
