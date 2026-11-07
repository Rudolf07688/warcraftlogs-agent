# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-07 (P14 merged to main, unpushed)

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

## Sprint 2026-11-07 (P14) merged

Merged to main 23c73aa (owner go), plus 236f251: QA prompts + qa-sweep skill installed (project
copies in `.claude/agents/qa-*.md`, `.claude/skills/qa-sweep/` are the source of truth; also
copied to `~/.claude`, originals in `~/.claude/backups/qa-files-2026-11-07/`), and D18
security-core now covers team tools that guard secrets, ports or identity. Worktrees removed,
QA reports copied, GitNexus reindexed and sound. 0.56 M/pt, build 0.20/pt, 2 full suites.
**Next app sprint** = the real test of P14 and the first use of the P15 reserve rule; compare
against 11-05b. In scope there: the prompt-pin helper (sc-534) and embeddings following a pinned
location (sc-512).

## Open with the owner

1. Push main? (23c73aa + 236f251 + wrap-up commits; ask, never assume)
2. Move the 7 stories from 11-05b and the 9 from 11-07 to Done (the owner's call).
3. Wipe the pre-fix Mimir series? (local only)
4. Gemini Flash list price changes 2027-01-01 (pricing.yaml commit that day).

## How to resume

1. Read `meta/README.md`, then this file, then P14 and D21/D22 in `meta/team-optimisation.md`,
   then `meta/sprints/2026-11-05b/retro.md`.
2. Owner preferences: `meta/owner-preferences.md` (26–28 are new).
