# Brief 025 — QA fix: migration 0012 backfill under FORCE RLS, plus docs (fix feature Y)

| Field | Value |
|---|---|
| Feature number | 025 (QA fix, light flow) |
| Branch | `025-fix-migration-docs` (create it with `git switch -c 025-fix-migration-docs` from the detached HEAD; no `/speckit-specify` needed) |
| Worktree | `/home/rudolf/dev/wcl-worktrees/dev-b` |
| Base ref | `sprint-2026-10-25` tip (bff3d31 or later; the worktree is detached there) |
| Model / effort | sonnet / high |
| Stories | none new (QA fix-now on 018/019/021/022/023) |
| Peer developer | `dev-a-024` (fix feature X: welcome M+; no shared files) |
| Scrum master | `scrum-master` (your only channel upward) |
| QA reports (gitignored, read them here) | `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-10-25/README.md`, `bugs.md` (BUG-001), `spec-conformance.md` (SPEC-003, -004, -005, -007, -009) |
| Ownership ledger | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/ownership.md` |

## Fix-now items (product owner, verbatim)

**FN-3 (BUG-001):** migration 0012's `legacy` backfill must work when the migrator owns
the table but isn't a superuser or BYPASSRLS. Wrap the UPDATE in `ALTER TABLE conversations
NO FORCE ROW LEVEL SECURITY` … `FORCE ROW LEVEL SECURITY` (the owner may do this; 0004
already uses NO FORCE in its downgrade). Postgres only, behind the dialect guard. Verify on
real Postgres with a non-superuser owner role and pre-existing rows: every old row ends
`legacy`, FORCE is restored afterwards, and up/down/up still works. The sprint isn't
released, so editing 0012 in place is fine.

**FN-4 (SPEC-003/004/005/007/009): docs only.**
- README: the raid/M+ caps (6 + 6), the 429 sibling fallback and its messages, the
  turn-stats `fallback=` field, a line each for pins, generated titles and M+ runs.
- ai_guide: the 022 note, and fix §18 and the Redis key table (the `:keystone` summary key).
- 019 T033: untick it, or annotate it as "browser checks → owner live test".
- 019 FR-012 amended to "the first completed exchange" (I accept the current behaviour as
  better).
- 023: spec AS 2 and FR-002, plan, T003 and the checkpoint updated to 106.25% and decision
  31; tick T004.
- 018: tick T024.

## Light flow

No new Spec Kit spec. Steps:
1. Read the findings, then send me **one plan message**: the FN-3 approach (including how the
   UPDATE is guarded so a failure between NO FORCE and FORCE can't leave the table un-forced;
   Postgres DDL is transactional, so check that Alembic runs 0012 in a transaction), the
   exact file list, and the Postgres verification recipe. Wait for my grant.
2. Fix FN-3 first (one commit), verify on Postgres, then FN-4 (docs commit).
3. Hand off: branch, commits, files, test counts (baseline 1060/3/1), build, the Postgres
   transcript summary, and the item → change mapping.

## Tentative footprint

- `backend/migrations/versions/0012_conversation_pin_title.py`,
  `backend/tests/test_conversation_migration.py` (only if a SQLite-side assertion changes),
  `README.md`, `documentation/ai_guide.md`, `specs/018-wcl-agent-subpackages/**`,
  `specs/019-sidebar-conversations/**`, `specs/023-larger-font/**`.
- **Not yours:** `specs/022-welcome-mplus/**` and the welcome/M+ code (fix feature X),
  `CLAUDE.md`, `AGENTS.md`, `todo.md`, `.specify/*`.

## Notes

- Postgres verification: `docker run --rm -d` postgres on **15419** with dummy
  credentials. Create a non-superuser, non-BYPASSRLS **owner** role for the migration run
  (mirror how the app's migrator role is set up; read `backend/cli/init_db.py` and
  migration 0004/0006), seed old conversations at 0011, then upgrade to 0012 as that role.
  Stop the container afterwards.
- Reply "ACK" to every grant before you go idle.
