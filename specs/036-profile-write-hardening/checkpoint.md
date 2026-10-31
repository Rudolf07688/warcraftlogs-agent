# Checkpoint: 036 profile write-path hardening

Written in place of `/compact` (tier M step 4); updated after the 20:13Z machine crash.

- **Baseline (7989d61)**: backend 1308 passed / 9 skipped; frontend 24 tests.
- **Decisions**: board keys `clarify:036-sc221`, `clarify:036-sc222`, `clarify:036-sc223`,
  `clarify:036-sc225`; impact risks under `risk:036`.
- **Order**: one commit per story, sc-221 → 222 → 223 → 225 → 244, rebased on the sprint tip
  after 037's merge.
- **Approve round trips (sc-225)**: measured by `test_approve_round_trips_dont_grow_with_the_item_count`
  on SQLite: before 17 statements for 3 items and 125 for 30; after 7 for both. Postgres adds a
  fixed 3 (two `set_config`, one advisory lock).
- **Environment note**: after the reboot the agent shells carry the app's env vars; run pytest
  as `env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q`.
