# Quickstart: 022

1. `uv run --extra test pytest -q backend/tests/test_recent_mplus.py backend/tests/test_recent_raids.py`
2. `cd frontend && npm run build`
3. Live (app 18019, Postgres 15419, Redis 16319, own containers): register an own character with M+ logs, open the welcome page, see at most 6 raids and 6 runs; click a run, see the chat titled "M+ <dungeon> +<level>" start the review.
