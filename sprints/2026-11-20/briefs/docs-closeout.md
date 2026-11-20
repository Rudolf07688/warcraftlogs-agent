# Brief docs-closeout (dev-2 Tomas, sprint 2026-11-20 close-out)

- **Branch:** `docs-closeout-1120`. **Tier:** S. **Model / effort:** sonnet, high.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a` (new branch from the base). **Base ref:** the sprint-2026-11-20 tip at launch (`git -C /home/rudolf/dev/wcl-worktrees/sprint rev-parse sprint-2026-11-20`), after the QA fix round (083) merged.
- **Seat:** dev-2 (Tomas). Nobody else is building.
- **Security-core:** no. Docs, facts only: no code edits.

## 1. Architecture docs to the tip (owner's rule: they show the current state)
Follow `documentation/architecture/pages/maintaining.html`. `python3 .claude/team/archdocs.py changed` lists the pages whose code moved since their stamp. At the brief's writing (before 083) that was agent, backend-api, deployment, frontend, knowledge-base, models, observability and streaming. Re-run it at your base.
- Re-verify those sections against the code, not the specs. What this sprint changed:
  - 078: WCL event windows always send an end time; whole-report player details are a startTime/endTime window; Raids page keys come from the tools' helpers; damage_fields notes.
  - 079: Claude prompt-cache breakpoints, the turn-pinned time block, the 32k/16k output limit, one low-effort re-run (`TurnStats.budget_retries`).
  - 080: `thinking` and `interim` stream events (ThinkingFrame/InterimFrame), interim retraction rules, the status line in the chat UI.
  - 081: `get_boss_mechanics` and `backend/app/kb/mechanics/` notes in the "Stored knowledge" tool group.
  - 082/082b/083: prompt defaults, player-context class fill and saved main class/spec.
  - deployment/observability: the start script mode change and the Agent Team dashboard Decisions panel (committed on main before the sprint). Check, stamp.
- Add new components, remove what's gone, and update `index.html` (layer table, system diagram) where a layer changed.
- Then `python3 .claude/team/archdocs.py stamp` and `archdocs.py check` (must pass). Screenshot each changed page (headless chrome via `python3 .claude/team/browse.py`, window taller than the page) and look at it once.

## 2. Team facts, same pass
`python3 .claude/team/facts.py stale` lists the facts whose anchor moved this sprint. Skip one its author edited and verified this sprint. Re-check the rest against the code:
- still true: `facts.py verify <id>`
- partly true: edit, then verify
- no longer true: `facts.py retire <id> --why "..."`

Then `facts.py lint` must be clean.

## Footprint (owner:* keys to tomas)
- `documentation/architecture/**`, `.claude/team/facts/**`

## Hand-off
Commit on your branch (docs and facts only), post a `handoff`, and return about 10 lines: the pages changed, the facts verified, edited and retired, the `archdocs.py check` and `facts.py lint` lines, and your `Retro:` line.
