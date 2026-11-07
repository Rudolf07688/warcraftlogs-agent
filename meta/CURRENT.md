# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-07 18:15Z (P14 sprint done; merge question open)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D22, proposals P1–P15, baseline, change log).

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

## Sprint 2026-11-07 (P14) done, awaiting the merge question

20/20 pts on `sprint-2026-11-07` tip 736ee13 (base 9ff8602), not merged, not pushed. 11.2 M,
0.56/pt (cheapest yet; tooling work), build 0.20/pt, 2 full suites, cold 0.48, 49 min.
QA 1H+7M in tools guarding .env/loopback/identity, fixed in one fresh round. Archdocs and facts
gate clean. Reports: sprint review in the sprint worktree `sprints/2026-11-07/sprint-report.html`,
team report `meta/sprints/2026-11-07/team-report.html`. Teamstats pushed, Mimir has it.
After a merge: install the staged user-level QA files (`sprints/2026-11-07/user-level/README.md`;
I'd keep project copies in `.claude/agents` + `.claude/skills`), add team-tool guards to D18
security-core in product-owner.md, reindex GitNexus, remove worktrees (stack: no wcl-obs-lead
containers left). The live board hook keeps the identity flaw until the merge.

## Open with the owner

2. Move the 7 sprint stories to Done (the owner's call).
3. Wipe the pre-fix Mimir series? (local only)
4. Gemini Flash list price changes 2027-01-01 (pricing.yaml commit that day).

## How to resume

1. Read `meta/README.md`, then this file, then P14 and D21/D22 in `meta/team-optimisation.md`,
   then `meta/sprints/2026-11-05b/retro.md`.
2. Owner preferences: `meta/owner-preferences.md` (26–28 are new).
