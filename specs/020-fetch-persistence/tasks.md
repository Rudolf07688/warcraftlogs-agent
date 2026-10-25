# Tasks: Fetch persistence foundation

**Input**: `specs/020-fetch-persistence/` (plan.md, spec.md, research.md, data-model.md,
contracts/fetch-sink.md, quickstart.md)

**Tests**: Requested (sprint AC 6, plus PO condition decision 17): write-through, DB down,
full queue, upsert including an out-of-order pair, report codes in literal and variable
forms, shutdown drain and timeout.

Serial execution: one developer, no sub-agents (approved). `[P]` marks tasks with no
file overlap, kept for information.

## Phase 1: Setup

- [ ] T001 Record the baseline: run `uv run --extra test pytest -q` in the worktree, note the pass/fail/skip counts in `specs/020-fetch-persistence/checkpoint.md`

## Phase 2: Foundational (blocking)

- [ ] T002 Add `wcl_fetch_persist_enabled` (True), `wcl_fetch_persist_queue_max` (500) and `wcl_fetch_persist_queue_mb` (64) with a short comment block after the WCL lanes settings in `backend/app/config.py`
- [ ] T003 [P] Document `WCL_FETCH_PERSIST_ENABLED`, `WCL_FETCH_PERSIST_QUEUE_MAX` and `WCL_FETCH_PERSIST_QUEUE_MB` (commented defaults) after the WCL cache block in `.env.example`

## Phase 3: User Story 1: Every Warcraft Logs response is kept (P1) 🎯 MVP

**Goal**: Each successful WCL network call is offered once to a sink and upserted into `raw_fetches`.

**Independent test**: a real client over `httpx.MockTransport`, with a writer over the SQLite `session_factory`, produces one row with operation name, params, report codes and payload (without `_cost`).

### Client sink (sc-128 client half)

- [ ] T004 [US1] In `wcl_agent/client/wcl_client.py` add `FetchedResponse` (frozen dataclass), `FetchSink`, `_fetch_sink`, `set_fetch_sink()`, `_offer()` (no-op when unset; swallows sink exceptions with a debug log), `operation_name()` (reuses `_OP_RE`; `_log_cost` switches to it) and `report_codes()` (regex `report\(\s*code\s*:\s*(?:\$(\w+)|"([^"]*)")`, resolved, stripped, deduplicated in order)
- [ ] T005 [US1] In `wcl_agent/client/wcl_client.py` pass `key` from `AsyncWCLClient.query` to `_fetch(query, variables, key)` and call `_offer(key, query, variables, content)` just before `return content` (after `raise_for_status` and the `errors` check)
- [ ] T006 [US1] Tests in `backend/tests/test_raw_fetch_client.py`: one offer per call; three concurrent identical queries give one offer; nothing offered on HTTP 500, on GraphQL `errors` or with no sink; a raising sink leaves the result intact; `operation_name` for named and anonymous queries; `report_codes` for the variable form, the literal form, the batch `$c0..$c2`, duplicates, missing variable and no report; `query_key` equals `_flight_key`; `content` still contains `_cost` while the caller's payload does not

### Schema and store (sc-127)

- [ ] T007 [US1] Append `RawFetch` (`__tablename__ = "raw_fetches"`, PK `query_key` String(64), `operation_name` String(120) nullable, `params` `_JSON`, `report_code` String(32) nullable + index, `report_codes` `_JSON` NOT NULL server_default `'[]'`, `fetched_at` timestamptz, `payload` `_JSON`; GIN index on `report_codes` with `postgresql_using="gin"`) at the end of `backend/app/db/models.py`
- [ ] T008 [P] [US1] Create `backend/migrations/versions/0013_raw_fetches.py` (revision `0013_raw_fetches`, down_revision `0012_conversation_pin_title`): table, btree and GIN indexes, Postgres-only `GRANT SELECT, INSERT, UPDATE, DELETE` to `APP_DB_USER`; downgrade drops the indexes and the table
- [ ] T009 [US1] Create `backend/app/repositories/raw_fetches.py` with `upsert_raw_fetch(session, fetched)`: `repository._insert` dialect insert, payload bound as text through `CAST(... AS jsonb) #- '{data,_cost}'` on Postgres or `json_remove(..., '$.data._cost')` on SQLite, `ON CONFLICT (query_key) DO UPDATE … WHERE raw_fetches.fetched_at < excluded.fetched_at`, flush only
- [ ] T010 [US1] Tests in `backend/tests/test_raw_fetch_store.py` (SQLite `session` fixture): one row with every column right; `_cost` stripped; batch row has `report_code` NULL and all codes; a single report sets both columns; no-report row has `[]`

### Writer and wiring (sc-128 backend half)

- [ ] T011 [US1] Create `backend/app/services/fetch_persistence.py`: `store_fetch()` (`db_session.SessionLocal`, upsert, commit), `_Throttle` (one log per 60 s with a count), `FetchWriter` (`start`, `offer`, `_enqueue`, `_run`, `stop`, `dropped`) per contracts W1–W5, a 10 s per-write timeout
- [ ] T012 [US1] Wire it in `backend/app/main.py` `lifespan`: when `settings.wcl_fetch_persist_enabled`, create `FetchWriter(max_items=…, max_bytes=… * 1024 * 1024)`, `start()` it before the boot task, keep it on `app.state.fetch_writer`; on shutdown `await writer.stop(5)` after the boot task is cancelled and before `aclose_clients()`
- [ ] T013 [US1] Write-through tests in `backend/tests/test_raw_fetch_writer.py`: real client (mock transport) plus a writer over `patched_db`. A tool-like `query` stores one row, a second identical query after drain still gives one row, and a `get_or_load` cache hit (fake_redis) stores nothing new

## Phase 4: User Story 2: Saving never slows or breaks a chat (P1)

**Goal**: The hand-off never blocks; DB errors and overflow are logged, never raised.

**Independent test**: with the store raising, or blocked forever, queries return normally and the log shows the throttled warning.

- [ ] T014 [US2] DB-down test in `backend/tests/test_raw_fetch_writer.py`: the store raises `OSError` (and a variant using the default `store_fetch` against a `SessionLocal` bound to an unreachable URL); the query returns its payload and one warning is logged for several failures
- [ ] T015 [US2] Full-queue test in `backend/tests/test_raw_fetch_writer.py`: the store blocks on an `asyncio.Event`; `max_items=2`, then 5 queries return without waiting, `dropped == 2` (1 in flight + 2 queued), one warning; the byte-cap variant drops a response larger than the remaining budget
- [ ] T016 [US2] Shutdown tests in `backend/tests/test_raw_fetch_writer.py`: a timely drain (fast store, 3 items, `stop()` writes all, `dropped == 0`, sink uninstalled); the timeout path (blocking store, `stop(0.2)` returns in under 1.2 s, remaining items counted and logged, task cancelled)
- [ ] T017 [US2] Cross-thread test in `backend/tests/test_raw_fetch_writer.py`: `offer` from a worker thread (`asyncio.to_thread`) is delivered and stored

## Phase 5: User Story 3: A finished report is stored once (P2)

**Goal**: One row per query key; the newest fetch wins.

**Independent test**: upsert the same key twice gives 1 row with the newer payload; an older `fetched_at` after a newer one leaves the newer row.

- [ ] T018 [US3] Upsert tests in `backend/tests/test_raw_fetch_store.py`: same key twice gives 1 row with the latest `fetched_at` and payload; an out-of-order pair (newer first, then older) keeps the newer; different variables give 2 rows

## Phase 6: Polish and cross-cutting

- [ ] T019 Live Postgres check per quickstart §2–3 on port 15418 (apply 019's `0012` temporarily, uncommitted): upgrade → downgrade → upgrade, `\d raw_fetches`, the upsert guard and `_cost` strip with `#-`, and the `report_codes ?` lookup; record the results in `checkpoint.md`
- [ ] T020 Full suite `uv run --extra test pytest -q`: baseline counts plus the new tests; GitNexus `analyze --index-only` and `detect-changes --scope all`; ownership check of `git diff --name-only f32b771...HEAD`; restore `.specify/feature.json`/`CLAUDE.md` before every commit

## Dependencies

- T002 → T011/T012 (settings). T004 → T005 → T006. T007 → T008/T009 → T010 → T011 → T012/T013.
- US2 (T014–T017) needs T011. US3 (T018) needs T009.
- T019 needs T008/T009. T020 is last.

## Implementation strategy

MVP is US1 (T001–T013): rows land in the DB. US2 adds the isolation proofs, and the
behaviour already exists from T011. US3 proves the upsert guard. Commit after each
phase.
