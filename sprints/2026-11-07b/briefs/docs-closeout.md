# Brief docs-closeout (architecture docs + team facts, one pass)

- Tier S, seat dev-2 (Tomas, fresh run), model sonnet, effort high. Stream type: docs.
- Worktree `/home/rudolf/dev/wcl-worktrees/dev-docs` (detached at 263f34b, the sprint tip after
  the fix round). Branch `docs-2026-11-07b` from **263f34b**. Never push or merge.
- Procedure: `documentation/architecture/pages/maintaining.html`. Owner's rule: the docs show the
  current state of the code; re-verify against the code, not the specs.

## Task 1: architecture docs
`python3 .claude/team/archdocs.py changed` lists six pages whose code moved this sprint:
backend-api, database, deployment, frontend, streaming, wcl-data. What changed (sprint features):
- 072: GET /api/raids/{code}/summary (services/raid_summary.py, new raw_fetches reads,
  in-request re-verify, per-user limit) -> backend-api, wcl-data.
- 073: Raids page inside the app shell (/app/raids/:reportCode?, pages/RaidsPage.tsx,
  components/raids/*, summaryCache) and the sidebar's single Raids entry -> frontend.
- 074: profile_settings table with RLS (migration 0023), GET/PUT /api/profile/settings, POST
  /api/profile/onboarding/skip, onboarding UI, auth/redirect.ts -> database, backend-api, frontend.
- 075: Blizzard portraits (services/portraits.py, api/portraits.py, CHAR_PORTRAIT cache family,
  BLIZZARD_* settings), ClassAvatar portraits, usePortraits -> backend-api, wcl-data (cache
  families), deployment (env), frontend.
- 076: per-chat turn single-flight in ws.py (_ChatTurn, supersede, 'superseded' error) -> streaming.
Add new components, remove what's gone, update `index.html` (layer table, system diagram) if a
layer changed (portraits add an outbound Blizzard dependency). Then `archdocs.py stamp`,
`archdocs.py check`, screenshot each changed page with `browse.py` (desktop and 390 px), and commit.

## Task 2: team facts
`python3 .claude/team/facts.py stale` lists the facts whose anchor moved this sprint. Skip any
fact its author edited and verified this sprint (verified on 2026-11-07 by its author). Re-check
the rest against the code: `facts.py verify <id>` if it still holds, edit then verify if partly,
`facts.py retire <id> --why "..."` if not. Then `facts.py lint` must be clean. Commit.

## Footprint
`documentation/architecture/**`, `.claude/team/facts/**`. Nothing else.

Return about 10 lines: pages changed (names), facts verified/edited/retired (ids), the
`archdocs.py check` and `facts.py lint` output lines, commits, and a `Retro:` line.
