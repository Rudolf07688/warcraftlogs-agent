# Checkpoint: 022 welcome M+ runs (dev-b-022)

Worktree `/home/rudolf/dev/wcl-worktrees/dev-b`, branch `022-welcome-mplus`, base 6aa641d. Spec signed off; plan approved with a condition (impact results sent; waiting for OK on HIGH `_refresh`). `.specify/feature.json` and `CLAUDE.md` belong to the scrum master: `git checkout -- .specify/feature.json CLAUDE.md` before each commit (set feature.json to this spec dir locally only for speckit scripts).

Decisions: run = keystone fight (report+fight); completed = kill true and keystone_level > 0; timed = keystone_bonus >= 1; abandoned dropped. Same refresh/claim as raids; M+ detail for newest 10 non-raid reports. New tables recent_mplus_runs + recent_mplus_run_characters, migration 0014 (down 0013_raw_fetches). Display caps are new settings; `recent_raids_limit` keeps meaning listing depth. Report summary key bumped v1->v2. Kickoff + explicit title "M+ <dungeon> +<level>" (PO decisions 19-21).

Granted now: see scrum-master grant (recent_raids services/api/types, schemas.py, repository.py, queries.py, cache_models.py, cache.py key only, report_tools.py _summary_from only, frontend 4 files, migration 0014, test_recent_mplus.py, test_recent_raids.py, wcl cache tests if they pin v1, specs/022). Waiting on 020: models.py (append), config.py (2 settings). Keep schemas.py and App.tsx edits small (021 may need them); tell the scrum master when final.

Start implementation at T001 in tasks.md. Open: live WCL semantics (depleted `kill`, fight name = dungeon) unverified; no live credentials.

## Postgres / RLS verification (2026-10-25)

Real Postgres 16 in `docker run --rm` on port 15419 (dummy credentials, no compose, no owner .env), stopped afterwards. `backend.cli.init_db` brought it to head; then `alembic downgrade -1` (0014 -> 0013_raw_fetches), `upgrade head` (back to 0014_recent_mplus_runs): all clean. As the runtime role `wcl_app` with `app.tenant_id` set: tenant A inserted a character, a run and a link under RLS; inserting a run for tenant B while scoped to A was rejected by the policy; tenant B saw only its own run and 0 links; tenant A saw only its own run and 1 link; with `app.tenant_id` unset both new tables returned 0 rows and an insert was rejected. Tenant privacy (FR-011) holds at the database level. No code changes were needed.
