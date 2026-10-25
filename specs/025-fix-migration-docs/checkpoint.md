# 025 fix-migration-docs checkpoint

FN-3 (BUG-001): migration 0012 wraps the `legacy` backfill in `NO FORCE` / `FORCE ROW LEVEL SECURITY` (Postgres only).

Postgres 17 check (throwaway container on 15419, dummy credentials, role `mig_owner` NOSUPERUSER NOBYPASSRLS CREATEROLE owning the DB; bootstrap admin run between 0002 and 0003):
- 3 conversations seeded at 0011 (under the tenant GUC).
- Old 0012: all 3 rows stayed `auto` (bug reproduced).
- Fixed 0012: all 3 rows `legacy`; `relforcerowsecurity` is true afterwards.
- Downgrade to 0011 then upgrade to 0012 again: 3 rows `legacy`, FORCE on. `upgrade head` reaches 0014.
- Failure injection (throwaway, not committed): replaced the closing FORCE with `SELECT 1/0`; the upgrade aborted, FORCE stayed on and `title_source` did not exist (whole revision rolled back). Alembic runs the revision inside `context.begin_transaction()` and Postgres DDL is transactional.
- SQLite `test_conversation_migration.py`: 3 passed.

FN-4: docs only (README, ai_guide §18 and Redis families, redis_cache_spec key, 018 T024, 019 T033/FR-012, 023 spec/plan/tasks/checkpoint).
