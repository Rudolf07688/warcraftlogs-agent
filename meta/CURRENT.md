# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-05 late (retro captured as P14; next sprint 2026-11-06 = P14, steer parked below)

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

## Next sprint steer (owner, 2026-11-05: "prepare this meta-agent enablement as the work for the next sprint")

Sprint 2026-11-06, agent enablement. The team builds P14, its own retro, as Shortcut epic 525
in iteration 536: 8 stories, 20 pts (sc-526..533). Read `meta/sprints/2026-11-05b/retro.md`
and P14 in `meta/team-optimisation.md` first. The stories hold the ACs.
- **Ownership:** agent files, skills and CLAUDE.md are team-lead's (prefs 18, 27). For this
  sprint the team edits them on the sprint branch, and team-lead reviews those diffs before
  the merge question. Members' memories stay their own (pref 21). Rewrite rather than append,
  and cut every rule a change replaces.
- **File overlaps for the PO's shape:**
  - sc-526, 527, 528, 532 and the agent-file part of 531 all edit `developer.md` and
    `product-owner.md`, so they go to **one developer**.
  - Separate streams: `facts.py` (529); `check.py` and `mutate.py` (530, plus 526's receipt by
    area); board and hook (531); new tools (533, splittable).
- **Use D21 already in this sprint:** each developer tests their building block, one suite at
  the merged tip, the QA sweep covers the sprint diff only, and the fix bar is a broken AC,
  security or data loss.
- **Board and hook changes must not break the live board:** test them on a throwaway board.
  They take effect after the merge.
- **Live pass:** small. I run the stack helper and the headless browser once. The agent-file
  changes are measured on the sprint after this one (P14, last paragraph).
- **Not in scope:** the prompt-pin helper (sc-534) and embeddings following a pinned location
  (sc-512, owner yes, 1 pt). They go to the next app sprint.

Lead pre-flight tomorrow:
- Start the session through `bin/claude-otel`.
- `git status` clean on main.
- Reindex GitNexus (stale at bb22117 after meta-only commits) and check `context stream_response`.
- ADC login only if a live app call is needed.
- Remove this section once launched (team-launch 1.1).

## Open with the owner

1. Push main? (bb22117 + meta commits; ask, never assume)
2. Move the 7 sprint stories to Done (the owner's call).
3. Wipe the pre-fix Mimir series? (local only)
4. Gemini Flash list price changes 2027-01-01 (pricing.yaml commit that day).

## How to resume

1. Read `meta/README.md`, then this file, then P14 and D21/D22 in `meta/team-optimisation.md`,
   then `meta/sprints/2026-11-05b/retro.md`.
2. Owner preferences: `meta/owner-preferences.md` (26–28 are new).
