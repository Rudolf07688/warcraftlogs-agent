# Research: Fetch persistence foundation

## R1. Where to hook the write-through

- **Decision**: At the end of `AsyncWCLClient._fetch`, after `raise_for_status` and the
  GraphQL `errors` check, through a process-wide sink callable.
- **Rationale**: `_fetch` runs exactly once per network call: single-flight waiters share
  its task, and cache hits never reach it, because `get_or_load` sits above the client.
  Callers that bypass the cache (master data, events, run_graphql, benchmark,
  cooldowns) still go through it. Hooking here covers tools, guides, recent raids and
  background jobs with one line, and stores nothing twice.
- **Alternatives**: Hooking `get_or_load` misses the many uncached queries and sees typed
  models, not raw responses. Hooking `query()` runs once per waiter, so single-flight
  joins would be offered several times.

## R2. "Finished report" and the upsert key

- **Decision**: One row per query key (the client's `_flight_key`: sha256 of the query
  text plus sorted variables). Every store upserts the payload and `fetched_at`, guarded
  by `fetched_at < excluded.fetched_at`. A finished report is one whose last event lies
  at least `FINAL_AFTER` (2 h) before the fetch, as decided by
  `wcl_agent.cache.normalize.is_finished` (reused unchanged). With one row per key, a
  finished report can't pile up duplicates. sc-129 can tell whether a stored row was
  final by applying `is_finished(endTime, now=fetched_at)` to the report's summary row.
- **Rationale**: The product owner chose this (Q1, decision 16). Most report responses
  carry no `endTime`, so judging finality at write time would need a lookup per write.
- **Alternatives**: Appending live rows and upserting only finished ones was rejected by
  the PO: no history needed yet, and it needs a finality lookup at write time.

## R3. Keeping JSON work off the event loop

- **Decision**: Bind the raw response body as text and let the database decode it and
  strip the client-injected `_cost`: Postgres `CAST(:p AS jsonb) #- '{data,_cost}'`,
  SQLite `json_remove(:p, '$.data._cost')`.
- **Rationale**: Report payloads can be several MB. `json.loads` in a thread would still
  leave SQLAlchemy's JSON bind processor running `json.dumps` on the loop during
  `execute`. Feature 013 measured stalls of about 80 ms from that kind of work. With the
  DB doing it, Python only does a UTF-8 decode.
- **Alternatives**: Parse in a thread and pass a dict (re-serialises on the loop). Strip
  `_cost` with a bytes regex (fragile on comma placement).

## R4. Writer shape, bound and overflow

- **Decision**: An `asyncio.Queue(maxsize=500)` plus a byte counter (64 MB, from
  `len(content)`), a single consumer task, drop-newest on overflow, and a throttled
  warning (one per 60 s with a count).
- **Rationale**: The scrum master accepted Q3. Drop-newest never touches the
  queue under the producer. A single consumer keeps DB load to one connection and
  makes ordering trivial. WCL calls are rate-limited to a few per second, far below one
  sequential writer's throughput.
- **Alternatives**: Batching several rows per transaction was rejected: per-row
  transactions isolate one bad row (FR-007) and throughput isn't the constraint. A
  bounded task set was rejected: it needs N connections and unordered writes.

## R5. Thread safety of the process-wide sink

- **Decision**: `offer()` compares the running loop with the writer's loop. On a
  mismatch, or with no running loop, it hops over with `call_soon_threadsafe`.
- **Rationale**: `get_async_client` keeps one client per loop (CLI and tests make fresh
  loops), while `_fetch_sink` is global. In the app everything runs on one loop today,
  so the fast path is the norm.

## R6. Shutdown

- **Decision**: Unregister the sink, `wait_for(queue.join(), 5)`, then cancel the task and
  log the remainder as dropped. This runs before `aclose_clients()` and
  `engine.dispose()`.
- **Rationale**: The scrum master accepted Q4. Unregistering first means a fetch
  finishing during shutdown is simply not offered, so it can't race with the drain.

## R7. Report codes in a queryable form

- **Decision**: A separate `report_codes` JSONB array column, NOT NULL with default `[]`,
  and a GIN index (default `jsonb_ops`, so both `?` and `@>` are indexed). The codes are
  extracted from the query text (`report(code: $v)` or a literal) and resolved through
  the variables. `report_code` is set when there is exactly one code.
- **Rationale**: This meets the PO's condition (decision 17) uniformly for single,
  batched and agent-written queries. Keeping the column separate leaves `params` as the
  exact variables sent. The arrays are tiny, so the GIN index is cheap.
- **Alternatives**: A `report_codes` key inside `params` (mixes our metadata into the
  request). Guessing from variable names like `code`/`c{i}` (fragile: `r{i}` is a
  region in the character batch).

## R8. Migration on Postgres

- **Decision**: `0013_raw_fetches`: `create_table`, the btree index on `report_code`,
  GIN on `report_codes` (Postgres only), and `GRANT SELECT, INSERT, UPDATE, DELETE` to
  the runtime role (pattern of `0007`/`0011`). Downgrade drops the table.
- **Verification**: upgrade → downgrade → upgrade on a throwaway `postgres` container on
  port 15418 (quickstart).
