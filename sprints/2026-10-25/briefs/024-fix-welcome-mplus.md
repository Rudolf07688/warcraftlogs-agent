# Brief 024 — QA fix: welcome M+ resilience and per-fight characters (fix feature X)

| Field | Value |
|---|---|
| Feature number | 024 (QA fix, light flow) |
| Branch | `024-fix-welcome-mplus` (create it with `git switch -c 024-fix-welcome-mplus` from the worktree's detached HEAD; no `/speckit-specify` needed) |
| Worktree | `/home/rudolf/dev/wcl-worktrees/dev-a` |
| Base ref | `sprint-2026-10-25` tip (bff3d31 or later; the worktree is detached there) |
| Model / effort | opus / medium |
| Stories | none new (QA fix-now on sc-153 / feature 022) |
| Peer developer | `dev-b-025` (fix feature Y: migration 0012 and docs; no shared files) |
| Scrum master | `scrum-master` (your only channel upward) |
| QA reports (gitignored, read them here) | `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-10-25/README.md`, `spec-conformance.md` (SPEC-001, -002, -006, -008), `bugs.md` (BUG-002) |
| Feature context | `specs/022-welcome-mplus/` (spec, plan, tasks, checkpoint) and decisions.md entries 19–21 |
| Ownership ledger | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/ownership.md` |

## Fix-now items (product owner, verbatim)

**FN-1 (SPEC-001 + BUG-002): welcome M+ resilience.**
- (a) The M+ step's errors are isolated. A WCL 429 or timeout in `_refresh_mplus_runs` is
  logged and doesn't mark the refresh `failed` when the raid step succeeded. Don't mark M+
  reports final when their fetch failed.
- (b) WelcomePanel renders stored M+ runs whatever the raid state: with no raids, while
  `running`/`idle` it shows the runs (plus a small refresh indicator, not a skeleton), and
  on `failed` it shows the runs plus the error/retry alert.
- Tests: a raid-less player with stored runs during a running refresh and after a failed
  one (a frontend-free backend test of the payload is fine, plus a component check if
  cheap); an M+ fetch failure alone leaves the refresh status ok and the stored runs
  intact. That also closes SPEC-006 (022 T021's missing assertions).

**FN-2 (SPEC-002): each run names only the own characters who were in that fight**, per
decision 19. Use the fight's friendlyPlayers (FightSummary.player_ids → summary.players
names), matched to the report's own characters by name, case-insensitive (by server too
if the summary has it). If nothing matches, fall back to the report-level characters, so a
run is never dropped or left unnamed. Add a test with two own characters in one report and
only one of them in the key.

**Docs for the area: SPEC-008**, the 022 spec edge case per decision 20 (a missing key
level means the run isn't listed).

## Light flow

No new Spec Kit spec: these restore behaviour the 022 spec already requires. Steps:
1. Read the findings and the code, then send me **one plan message**: the root cause of each
   item, the fix approach, the exact file list, and GitNexus `impact` (upstream) on every
   symbol you'll change (`_refresh`, `_refresh_mplus_runs`, `extract_mplus_runs`,
   WelcomePanel). Wait for my grant.
2. Fix, test, and commit in small slices (one commit per FN item is ideal).
3. Hand off: branch, commits, files, test counts (baseline 1060/3/1), build, forced
   `detect-changes`, and the item → test mapping.

## Tentative footprint

- `backend/app/services/recent_raids.py`, `backend/app/services/recent_raid_types.py`
  (only if a type needs it), `backend/app/api/recent_raids.py` (only if the payload needs it),
  `frontend/src/components/WelcomePanel.tsx`, `backend/tests/test_recent_mplus.py`,
  `specs/022-welcome-mplus/**`.
- Read-only: `wcl_agent/cache/cache_models.py` (FightSummary.player_ids, players) and
  `report_tools.py`. If you think you need to edit them, ask first.
- **Not yours:** migration 0012, README.md, `documentation/ai_guide.md`, `specs/018,019,023`
  (fix feature Y), `CLAUDE.md`, `AGENTS.md`, `todo.md`, `.specify/*`.

## Notes

- Live checks if needed: app 18018, Postgres 15418, Redis 16318 (`docker run --rm`, dummy
  credentials, no owner .env). The shadcn MCP needs `registries: ["@shadcn"]` named
  explicitly; run add commands from `<worktree>/frontend`.
- Re-index GitNexus with `--force` (incremental runs give stale results).
- Reply "ACK" to every grant before you go idle.
