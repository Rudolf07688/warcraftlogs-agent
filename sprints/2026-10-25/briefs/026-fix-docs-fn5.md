# Brief 026 — QA fix FN-5: three docs edits (light flow)

| Field | Value |
|---|---|
| Feature number | 026 (QA fix, docs only) |
| Branch | `026-fix-docs-fn5` (`git switch -c 026-fix-docs-fn5` from the detached HEAD; no Spec Kit steps) |
| Worktree | `/home/rudolf/dev/wcl-worktrees/dev-b` |
| Base ref | `sprint-2026-10-25` tip (the worktree is detached there) |
| Model / effort | sonnet / low |
| Peer | none |
| Scrum master | `scrum-master` (your only channel upward) |
| QA re-check | `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-10-25-recheck/` (gitignored; read it there) |

## FN-5 (product owner, verbatim)

1. README.md: add a feature 020 bullet. Every successful WCL response is stored in the
   global `raw_fetches` table by a bounded background writer. Name the settings
   WCL_FETCH_PERSIST_ENABLED, _QUEUE_MAX and _QUEUE_MB (default on, 500 responses,
   64 MB), and say that nothing reads the table yet. That's the SPEC-003 remainder.
2. documentation/ai_guide.md §18 (the 022 block): say that an M+-only failure (WCL error
   or timeout in the M+ step) is logged and the refresh still records `succeeded`, so
   stored raids and runs stay visible (decisions 36 and 37). Only the raid step can fail
   a refresh. Add "don't surface it as a refresh failure without a separate retry path".
   That's SPEC-R01, which guards against regressing SPEC-001.
3. specs/023-larger-font/checkpoint.md: `106.25%` came from 8a8ce50; 0c62d18 set 17px.
   That's SPEC-R02.

## Files (granted)

`README.md`, `documentation/ai_guide.md`, `specs/023-larger-font/checkpoint.md`. Nothing else.

## Steps

Make the three edits next to the existing feature 019/021/022 text (match its style;
verify setting names and defaults against `backend/app/config.py` and `.env.example`).
Make one docs commit. No tests are needed (docs only). Then send the scrum master the head,
`git show --stat HEAD`, and the three added lines. Don't touch CLAUDE.md, `.specify/*`
or todo.md.
