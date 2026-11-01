# Checkpoint 045

- Baseline (sprint tip 63c4e62): 1472 passed, 19 skipped (SQLite).
- Part 1 (sc-295 + sc-296) done: see tasks T001-T015. Race-1 tombstone lives in the writer
  process (board #63), not in `raw_reports`: the 039 test asserts the status row is deleted.
- Next: sc-132 (T016-T017) from `cache.py` (`LOCAL_METRICS` hash already counts store_*), then
  sc-131 (T018-T021) after `raw_fetches.py` comes back from Ansel and the agent_runner.py grant.
