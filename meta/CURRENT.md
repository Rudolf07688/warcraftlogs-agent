# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-07 late (P14 done + retro; P16 agreed, start fresh)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D22, proposals P1–P16, baseline, change log).

## Where we are

- Sprint 2026-11-05b (back to the app) merged to main bb22117 and pushed (with the meta
  commits after it). 10/10 pts, 1.19/pt, cold 0.44, live 4/4 PASS. Stories Under Review.
- **First full-team retro done** (all six by seat, two rounds). Record:
  `meta/sprints/2026-11-05b/retro.md`. The owner's message on over-testing and the team's
  answers became **D21** (test the building blocks, then the whole, once), **D22** (GitNexus
  gates only for code-symbol diffs, owner approved) and **P14**. Owner preferences 26–28.
- **2026-11-07 meta talk:** reviewed levers vs outcomes for 11-04b/11-05/11-05b (each lever hit
  its target; the cost per point is confounded by the type of work). Owner floated kanban flow closed by a fixed number of points
  → **P15**, narrowed with the owner to a fixed ~23-pt plan plus 1–2 reserve stories the PO
  may backfill. Owner go: in `product-owner.md` now, first used in the next backlog sprint
  (inactive in P14).
- Owner: "implement all these things, but not now ... for tomorrow, we evolve." **Nothing in
  P14 is built yet.**

## Sprint 2026-11-07 (P14): merged, pushed, Done, retro held

Merged 23c73aa and pushed (c732dd5 and later). All 16 stories (11-05b + 11-07) Done; the
iteration is renamed 2026-11-07. QA prompts and the qa-sweep skill installed as project copies
(source of truth) and in ~/.claude. Full-team retro round 1: `meta/sprints/2026-11-07/retro.md`.

## Next: P16 (owner go 2026-11-07, "I agree"), start in a fresh session

Read P16 in `meta/team-optimisation.md`. Step 1 first, on main, as lead (agent files are mine):
- Hostile inputs in briefs (product-owner.md).
- The developer.md hard rule for security-core work and trusted artefacts.
- Agreeing shared formats before launch, as a standard PO step.
- Ilse's three scrum-master.md gaps, plus two rituals cut.
- Take back the blanket D18 team-tool rule I added on 11-07 (product-owner.md, D18 paragraph).
- One backlog ticket for the five tool gaps, deduplicated against sc-538..542.

Per P16 step 5, the affected seats review the agent-file diff read-only before I commit.
Then steps 2–4 (hazards fired by a hook, about 5 entry points, stream types) as designs. Ask
the owner whether they become a small meta sprint or reserve stories; the next app sprint
stays a clean P14 test.

## Open with the owner

3. Wipe the pre-fix Mimir series? (local only)
4. Gemini Flash list price changes 2027-01-01 (pricing.yaml commit that day).

## How to resume

1. Read `meta/README.md`, then this file, then P14 and D21/D22 in `meta/team-optimisation.md`,
   then `meta/sprints/2026-11-05b/retro.md`.
2. Owner preferences: `meta/owner-preferences.md` (26–28 are new).
