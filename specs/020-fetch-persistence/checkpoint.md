# Checkpoint: feature 020 (fetch persistence)

Resume point for a fresh context. The worktree is `/home/rudolf/dev/wcl-worktrees/dev-a`,
on branch `020-fetch-persistence`, with base `f32b771` (sprint tip after 018).

## Status

- Spec signed off (`spec.md` Clarifications; PO decisions 16, 17). Plan approved, with
  the HIGH/CRITICAL impact on `_fetch`, `query`, `_log_cost` and `Settings` accepted.
- Shortcut: sc-127 In Progress; sc-128 moves to In Progress at T004.
- Baseline (T001): `uv run --extra test pytest -q` gives **926 passed, 3 skipped, 1
  deselected** at f32b771.

## Decisions

- One row per `query_key` (the client's `_flight_key`). Upsert guarded by
  `fetched_at < excluded.fetched_at`.
- A separate `report_codes` JSONB column with GIN, plus `report_code` set when there is
  exactly one code. Codes come from `report(code: $v | "lit")` in the query text.
- Payload bound as text and decoded in the DB: `CAST(:p AS jsonb) #- '{data,_cost}'` on
  Postgres, `json_remove` on SQLite.
- The writer: `asyncio.Queue(500)` plus a 64 MB byte cap; drops the newest; throttled
  warnings (60 s); one consumer; a 10 s write timeout; `stop(5)` before `aclose_clients`.
- Only the backend app persists. The sink stays None elsewhere.

## Files owned (granted)

`wcl_agent/client/wcl_client.py`, `backend/app/db/models.py` (append RawFetch at the end
only), `backend/app/config.py` (3 settings), `backend/app/main.py` (lifespan),
`.env.example`, `backend/migrations/versions/0013_raw_fetches.py`,
`backend/app/repositories/raw_fetches.py`, `backend/app/services/fetch_persistence.py`,
`backend/tests/test_raw_fetch_{client,store,writer}.py`, `specs/020-fetch-persistence/**`.
Not mine: `repository.py` (read-only import of `_insert`), `conftest.py`, `CLAUDE.md`,
`.specify/feature.json` (restore before every commit).

## Open

- The migration chain needs 019's `0012` for a live test: cherry-pick it temporarily
  and don't commit it. 019 merges before 020.

## Implementation status (2026-10-25)

All tasks T001–T020 done. Results:

- Full suite: **953 passed, 3 skipped, 1 deselected** (baseline 926 + 27 new: 12 client,
  6 store, 9 writer).
- Live Postgres 17 on port 15418, with 019's `0012` copied in temporarily and removed
  afterwards (not committed). `upgrade head` → `downgrade -1` (table gone, version 0012) →
  `upgrade head` all succeed. `\d raw_fetches` shows the 7 columns, PK `query_key`, btree
  `ix_raw_fetches_report_code` and GIN `ix_raw_fetches_report_codes`. `wcl_app` has
  `arwd`.
- As the runtime role `wcl_app`, the writer stores through the real client: `_cost` is
  stripped by `#-` (`has_cost = false`). The out-of-order pair keeps the newer row.
  `report_codes ? 'B2'` finds the batch row through a Bitmap Index Scan on the GIN index.
