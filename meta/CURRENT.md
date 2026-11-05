# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-05 late (first full-team retro done; P14 captured, build next session)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D22, proposals P1–P14, baseline, change log).

## Where we are

- Sprint 2026-11-05b (back to the app) merged to main bb22117, **unpushed** (plus the meta
  commits after it). 10/10 pts, 1.19/pt, cold 0.44, live 4/4 PASS. Stories Under Review.
- **First full-team retro done** (all six by seat, two rounds). Record:
  `meta/sprints/2026-11-05b/retro.md`. The owner's message on over-testing and the team's
  answers became **D21** (test the building blocks, then the whole, once), **D22** (GitNexus
  gates only for code-symbol diffs, owner approved) and **P14**. Owner preferences 26–28.
- Owner: "implement all these things, but not now ... for tomorrow, we evolve." **Nothing in
  P14 is built yet.**

## NEXT (meta session): build P14

Shortcut epic 525 "Agent team: ways of working and tools (retro 2026-11-05b)", built in this order:

1. Testing shape (sc-526, 3)
2. GitNexus gates only for code (sc-527, 1; CLAUDE.md local section)
3. PO process (sc-528, 2)
4. Facts for the paths a developer runs (sc-529, 2)
5. Test tools (sc-530, 3)
6. Board noise (sc-531, 3)
7. Scrum master (sc-532, 1)
8. New tools (sc-533, 5)

Rewrite agent files rather than append, and cut the rules each change replaces. Then measure on
the next sprint (P14, last paragraph).

App backlog for a sprint: the prompt-pin helper (sc-534, 2). Embeddings follow a pinned model
location (sc-512, 1 pt): the owner said yes, and the design is in the ticket comment.

## Open with the owner

1. Push main? (bb22117 + meta commits; ask, never assume)
2. Move the 7 sprint stories to Done (the owner's call).
3. Wipe the pre-fix Mimir series? (local only)
4. Gemini Flash list price changes 2027-01-01 (pricing.yaml commit that day).

## How to resume

1. Read `meta/README.md`, then this file, then P14 and D21/D22 in `meta/team-optimisation.md`,
   then `meta/sprints/2026-11-05b/retro.md`.
2. Owner preferences: `meta/owner-preferences.md` (26–28 are new).
