# Quickstart: verify 051

```bash
cd /home/rudolf/dev/wcl-worktrees/dev-b
python3 .claude/team/check.py run backend/tests/test_051_tombstones.py backend/tests/test_051_own_summary.py --as ansel
python3 .claude/team/pg.py up ansel                       # schema at head via init_db
python3 .claude/team/check.py run --pg ansel --as ansel   # full suite incl. *_pg tests, 0 skipped
python3 .claude/team/pg.py down ansel
```

Migration up/down (a scripted check on the throwaway database, not a test: it changes the
schema under the suite): with the owner URL from `pg.py url ansel`, run
`alembic downgrade 0019_kb_chunks` → `upgrade head` → `downgrade 0020_raw_fetch_summary_index`
→ `upgrade head`, logging the statements to confirm `CONCURRENTLY` outside a transaction. The
backfill itself is tested in `test_051_raw_store_pg.py` by calling the migration's backfill helper.

Live check (team-lead, optional): ask the agent for "stored reports for <character>" on a workspace
that fetched the character's raids; the list matches the reports it fetched.
