# Brief 076-turn-serialization

- Feature **076**, branch `076-turn-serialization`, tier **S** (short plan, then implement; no
  Spec Kit). Model opus, effort high.
- Seat **dev-4** (Vera). Worktree `/home/rudolf/dev/wcl-worktrees/dev-d`. Stream type: app backend.
- **Security-core: yes** (a per-conversation single-flight/lock key path in the chat loop).
  PO runs one qa-security review at hand-off, including liveness.

## Story
sc-511 (3) "QA BUG-001 (2026-11-05b): a new turn can run alongside a dropped turn on the same
chat" (verbatim): "The backend runs a turn inline in the socket's receive loop and notices a
gone client only when the next frame send fails (`backend/app/api/ws.py:340-373`). Since sc-376
the composer unlocks ~1.5 s after a drop. After a network blip / proxy timeout / laptop sleep
(not a backend restart), the player can send Q2 on the new socket while T1 is still in a tool
round on the old one. T1's `_persist_partial` (`ws.py:243-267`) then adds its partial at the
next seq, after Q2, and `assign_message_seq_to_turn_captures` links T2's charts to T1's
partial. Both turns append to the same ADK session.
Suggested fix: serialize turns per conversation (lock or turn-in-flight, cancel or await the
old one when a new turn for the same chat arrives), or a concurrent `receive()` watchdog in
`_handle_turn` that cancels the turn when the socket closes; anchor the partial at
`user_seq + 1`.
Acceptance: a test where T1 is mid tool round, the socket closes, and T2 starts on a new socket
for the same chat: T1 is cancelled (or finishes) before T2 writes; message order is Q1,
partial-A1, Q2, A2; T2's charts link to A2."

## File footprint
- `backend/app/api/ws.py`, `backend/tests/test_076_*.py` (new); existing ws tests only where
  your change forces it (`test_proposal_ws.py`, `test_model_fallback_ws.py`, `test_ws_rate_limit.py`).
- `backend/app/db/repository.py` is 074's this sprint. If anchoring the partial truly needs a
  repository change, post a `blocker` with the exact hunk; prefer doing it in `ws.py`.

## Hazards and hostile inputs (rule 10)
- **Liveness:** no turn may wait forever behind another. A T1 stuck in a long tool round must
  be cancelled (or bounded) when T2 arrives, not awaited without a limit. Test: T1 blocks
  forever in a tool; T2 still completes within a bounded time.
- **Cross-workspace:** the lock/registry key is built after the ownership check, from the
  server-verified conversation (and tenant), never from the raw id in the frame: workspace B
  sending workspace A's conversation id must not cancel, block or delay A's turn (assert A's
  turn completes and nothing of B is written).
- **Same chat, two tabs, one user:** decide (decision `scope:076:two-tabs`) whether a second
  live socket's turn cancels the first or waits; either way the order rule holds.
- Registry growth: entries are removed when a turn ends (incl. cancel and exceptions); a test
  that the registry is empty after 100 turns with errors.
- Cancellation must still save the partial in the right place (seq right after its own Q),
  and must not leave the ADK session with a dangling half-turn.
- One mutate.py bite on the serialization guard and one on the ownership-before-key order.
- See Known facts: reuse the ws test helpers in `test_proposal_ws.py`; don't add a keyword to
  the `set_refresh_actor` call.

## Live pre-check
If a question needs the real stack, post `live-check:076-pre` with the exact command; team-lead
runs it at once.

## Common rules for this sprint
- Base ref **de66bdd** (sprint branch tip; restClient `send` is exported there). Create your
  branch from it in your worktree. Never push, never merge, never move a ticket to Done.
- Parallel streams: 072 Nils (dev-3), 073 Tomas (dev-2), 074 dev-5 (new seat), 075 Ansel
  (dev-1), 076 Vera (dev-4). PO is Maren (`--to maren` not needed for questions).
- Footprint: only the files below (board `owner:` keys). Shared files (`backend/app/schemas.py`,
  `backend/app/db/repository.py`, `backend/app/db/models.py`, `backend/app/api/profile.py`,
  `frontend/src/types.ts`, `frontend/src/api/restClient.ts`) belong to 074 alone; everyone
  else keeps new types and calls in their own new modules. Need anything outside: `blocker`.
- **Live pre-check:** if a question needs the real stack (real LLM, WCL, Blizzard, `.env`),
  post a `question` keyed `live-check:<NNN>-pre` with the exact command while building;
  team-lead runs it at once. End-of-sprint live steps go under `live-check:<NNN>`.
- Testing (D21): targeted tests while building; one honest contract test per promise; hand-off
  receipt `python3 .claude/team/check.py run --as <you> --base de66bdd` on your committed head.
- Hand-off as in `developer.md` (about 20 lines, AC mapping, RESULT line, `Retro:` line).
## Known facts for this footprint

Team facts for `backend/app/api/ws.py`, `backend/app/db/repository.py`, and the paths you run: `.claude/team/check.py`, `.claude/team/pg.py` (`python3 .claude/team/facts.py for ...`). Trust them, but re-check one marked STALE before relying on it; record a new lesson with `facts.py add`.

- **chat-drop-ends-turn-locally** (direct: sym:backend/app/api/ws.py::_persist_partial is in backend/app/api/ws.py; verified 32010a6 2026-11-05): App.handleStatus ends a streaming turn when the socket drops (partial text kept, note in the error line, composer free); the next open reloads that chat (reloadAfterDrop). The backend saves a status=partial message only when the process survives (_persist_partial); after a restart the reload re-appends the local partial. The Composer is disabled while disconnected, so tests cannot click send mid-drop. Partial and `done` answers go only into the open chat; dropRef is cleared by sendText and selectConversation.
- **runner-outcome-flag-on-record** (direct: file:backend/app/api/ws.py; verified b9cf9a3 2026-11-05): To tell `ws.py` about a turn's outcome, put a flag on the yielded record, never match on its text. The closing no-answer token carries `"empty": True`; `ws.py` pops it before sending (the wire frame is unchanged) and then skips the KB offer, the title and follow-up suggestions.
- **ws-refresh-actor-patch-signature** (direct: file:backend/app/api/ws.py; verified b9cf9a3 2026-11-05): The ws tests (`test_turn_path`, `test_048_empty_outcome`, `test_model_fallback_ws`, `test_conversation_titles` and others) patch `ws_mod.set_refresh_actor` with `lambda *_: None`. Adding a keyword argument where `ws.py` calls it breaks all of them. Add a new function instead, as `abandon_turn` did.
- **ws-test-helpers** (direct: file:backend/app/api/ws.py; verified b9cf9a3 2026-11-05): For backend WebSocket tests, reuse the helpers in `backend/tests/test_proposal_ws.py` (`_identity`, `_quiet`, `_ctx_stream`, `_tool_end`, `_run`) rather than building a new chat harness.
- **fetch-visible-clause-one-rule** (component: comp:postgres covers backend/app/db/repository.py; verified b9cf9a3 2026-11-05): Visibility for the global tables (`raw_fetches`, `kb_chunks`) lives in the SQL of every read branch, and it has one definition: `raw_fetches.fetch_visible_clause`, the 039 rule (every code public or granted to the tenant since `since`). Rows derived from a fetch must also pass `fetch_names_code` (a chunk's `report_code` is one of its fetch's codes). Join these two; never re-implement the rule.
- **fk-checks-bypass-rls** (component: comp:postgres covers backend/app/db/repository.py; verified b9cf9a3 2026-11-05): Postgres foreign-key checks ignore RLS. A tenant-scoped row that references another tenant table needs a composite FK `(x_id, tenant_id) -> (id, tenant_id)` plus `UNIQUE(id, tenant_id)` on the target, as `kb_chat_chunks -> conversations` has (0019). Without one, a workspace's insert can name another workspace's row. `messages.conversation_id` is still a plain FK (backlog); the callers check ownership first.
- **index-migrations-concurrently** (component: comp:postgres covers backend/app/db/repository.py; verified b9cf9a3 2026-11-05): Index migrations run `create_index`/`drop_index` with `postgresql_concurrently=True` inside `op.get_context().autocommit_block()` (see 0020 and 0021), so they don't lock `raw_fetches`. Prove each one up, down and up again against the `DATABASE_OWNER_URL` that `pg.py up <you>` prints (the owner role), not the runtime URL.
- **pg-partial-index-literals** (component: comp:postgres covers backend/app/db/repository.py; verified b9cf9a3 2026-11-05): Under asyncpg, Postgres uses a partial index only when the query's predicate value is a SQL literal, not a bound parameter. That is why `_candidate_codes` uses `literal_column("'public'")`, so `ix_raw_reports_public_checked` matches. To prove a plan, run EXPLAIN after `SET LOCAL enable_seqscan = off` and assert the index appears, as `test_047_stored_reports_pg.py` does.
- **pg-tests-shared-db** (component: comp:postgres covers backend/app/db/repository.py; verified d4ccc69 2026-11-07): The Postgres tests (`*_pg.py`, `test_rls.py`, via `TEST_DATABASE_URL`) share one long-lived database with no reset between tests. Use unique test data (fresh UUIDs and report codes), and never assert exact result lists over global tables (`raw_fetches`, `kb_chunks`, `spec_guides`): other tests' rows are there too.
- **stored-reports-lookup-candidates** (component: comp:postgres covers backend/app/db/repository.py; verified b9cf9a3 2026-11-05): On Postgres the stored-reports lookup reads only own-summary rows that name a code confirmed public, or granted to the tenant, since `since` (`_candidate_codes`). The partial GIN index `ix_raw_fetches_own_summary_codes` serves it. Visibility itself still comes from `fetch_visible_clause`. `SUMMARY_LIST_TIMEOUT_MS` is set as a transaction-local statement_timeout and stays in force for the rest of the caller's transaction.
- **dialect-sql-compiles** (neighbour: file:backend/app/repositories/raw_fetches.py calls backend/app/db/repository.py::_insert; verified b9cf9a3 2026-11-05): Dialect-specific SQL inside a clause with a fixed signature is written as a `ColumnElement` subclass with one `@compiles` per dialect. In `raw_fetches.py`, `_NonEmpty` uses `jsonb_array_length` on Postgres and `json_array_length` on SQLite, and `_CodesVisible` works the same way. Callers keep one function that runs on both test engines.
- **raw-fetches-no-query-text** (neighbour: file:backend/app/repositories/raw_fetches.py calls backend/app/db/repository.py::_insert; verified b9cf9a3 2026-11-05): `raw_fetches` rows keep the params, report codes and payload, never the GraphQL query text. Anything that depends on the query's shape has to be decided when the row is written, the way `own_summary` is, or inferred from the body. The KB backfill skips stored tables whose metric it can't infer from the body.

(1 more: `facts.py brief --all ...`)
