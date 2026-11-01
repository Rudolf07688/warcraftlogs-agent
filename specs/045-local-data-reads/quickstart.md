# Quickstart: 045

```bash
cd /home/rudolf/dev/wcl-worktrees/dev-c
env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q backend/tests/test_raw_store*.py backend/tests/test_raw_fetch*.py backend/tests/test_cache_stats.py backend/tests/test_local_answer.py backend/tests/test_stored_data_tools.py
```

Postgres-only (`specs/039-local-first-data/quickstart.md` §2, image `pgvector/pgvector:pg17`, port 15445, name `wcl-045-pg`, `--rm`, stop after), then
`env -i HOME=$HOME PATH=$PATH TEST_DATABASE_URL=... uv run --extra test pytest -q backend/tests/test_raw_store_pg.py`.

Live check (team-lead): ask two report questions, repeat one; `GET /api/admin/cache-stats` shows `store` counts and `local_answers.rate`; with Postgres paused (`docker pause`) a report question still answers with ≤ 0.5 s extra and logs one breaker opening.
