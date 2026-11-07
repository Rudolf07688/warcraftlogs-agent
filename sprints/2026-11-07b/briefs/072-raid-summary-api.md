# Brief 072-raid-summary-api

- Feature **072**, branch `072-raid-summary-api`, tier **M** (one Spec Kit pass, no gates;
  answer clarify yourself as board decisions `scope:072:<topic>`). Model opus, effort high.
- Seat **dev-3** (Nils). Worktree `/home/rudolf/dev/wcl-worktrees/dev-c`. Stream type: app backend.
- **Security-core: yes** (tenant visibility over stored WCL data). PO runs one qa-security
  review at hand-off before merging.

## Story (backend half of sc-142, 3 of its 5 pts; Tomas builds the UI half in 073)
sc-142 "Raids page: show previously pulled raid data" (verbatim): "As a user, I want each raid
to show stored data (participants, duration, my character's parse), so I can review it
without a chat." Area: Frontend, Backend, Data.

Your part: `GET /api/raids/{report_code}/summary` returns, for a raid tracked in the caller's
workspace, what we already stored about it: participants, duration, and the parses of the
caller's own characters (profile self characters) in that report. It **never calls Warcraft
Logs** (no live fetch, no back-fill); missing pieces come back null/empty. Read stored data
only through the existing visibility rule (`fetch_visible_clause`, see Known facts).

## Contract (`contract:raid-summary` on the board; you are the producer)
`GET /api/raids/{report_code}/summary` → 200:
```json
{
  "report_code": "a1B2c3D4e5F6g7H8",
  "has_data": true,
  "duration_ms": 9876000,
  "participants": [{"name": "Thrall", "class_name": "Shaman", "spec": "Enhancement", "role": "dps"}],
  "my_characters": [{"name": "Thrall", "class_name": "Shaman", "spec": "Enhancement",
                     "parses": [{"encounter": "Ulgrax the Devourer", "difficulty": "Heroic", "percentile": 87.4}]}],
  "fetched_at": "2026-11-07T19:00:00Z"
}
```
- 404 (the app's usual error body) when the report isn't a tracked raid of the caller's workspace.
- `has_data: false` with `duration_ms: null`, `participants: []`, `my_characters: []`,
  `fetched_at: null` when nothing usable is stored. Each part may be missing independently.
- `role` is `"tank" | "healer" | "dps" | null`; `percentile` is 0–100 or null; `spec` may be null.
- Your pinning test: the endpoint's JSON for a seeded raid equals this shape (keys and types).
  If the build differs, post the "as built" version on the same key `--to all` before hand-off.

## File footprint
- `backend/app/api/raids.py` (add the route; keep the existing two unchanged)
- `backend/app/services/raid_summary.py` (new: the read logic **and its pydantic response
  models**: `schemas.py` belongs to 074 this sprint)
- `backend/app/repositories/raw_fetches.py` (only if you need a new read built on
  `fetch_visible_clause`; never a second visibility rule)
- `backend/tests/test_072_*.py` (new), `specs/072-raid-summary-api/**`
- Read-only use of `backend/app/db/repository.py` functions (`get_tracked_raid`,
  `list_own_characters`, …). Editing it is 074's: post a `blocker` if you truly must.

## Hostile inputs (rule 10: one test each, asserted where the guard takes effect)
- A report code tracked by **another** workspace → 404, and no stored row of it is read into
  the response (assert on the response body and that no other tenant's participants leak).
- A code that is stored and public but **not tracked** by the caller → 404 (the page is for
  tracked raids only).
- A stored fetch that names the code but is grant-only for another tenant → not used.
- Report code with path tricks: `..%2F`, `\`, a newline, 300 chars, unicode lookalikes → 404
  or 422 before any query, never a crash.
- Uploader-controlled text (player names, specs) in stored payloads → returned as data within
  the caps (`neutralise`/`_bounded` style), never as markup; a participant name of 5 000 chars
  or with control characters is capped/cleaned.
- "My character" identity comes from the caller's profile rows on the server, never from a
  query parameter or a name in the payload alone (match by name **and** realm/region where
  the payload has them).
- One mutate.py bite on the visibility guard.

## Live pre-check
If a question needs the real stack, post `live-check:072-pre` with the exact command while
building; team-lead runs it at once.

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

Team facts for `backend/app/api/raids.py`, `backend/app/services/raids.py`, `backend/app/repositories/raw_fetches.py`, `backend/app/schemas.py`, and the paths you run: `.claude/team/pg.py`, `.claude/team/check.py` (`python3 .claude/team/facts.py for ...`). Trust them, but re-check one marked STALE before relying on it; record a new lesson with `facts.py add`.

- **dialect-sql-compiles** (direct: sym:backend/app/repositories/raw_fetches.py::fetch_visible_clause is in backend/app/repositories/raw_fetches.py; verified b9cf9a3 2026-11-05): Dialect-specific SQL inside a clause with a fixed signature is written as a `ColumnElement` subclass with one `@compiles` per dialect. In `raw_fetches.py`, `_NonEmpty` uses `jsonb_array_length` on Postgres and `json_array_length` on SQLite, and `_CodesVisible` works the same way. Callers keep one function that runs on both test engines.
- **fetch-visible-clause-one-rule** (direct: sym:backend/app/repositories/raw_fetches.py::fetch_visible_clause is in backend/app/repositories/raw_fetches.py; verified b9cf9a3 2026-11-05): Visibility for the global tables (`raw_fetches`, `kb_chunks`) lives in the SQL of every read branch, and it has one definition: `raw_fetches.fetch_visible_clause`, the 039 rule (every code public or granted to the tenant since `since`). Rows derived from a fetch must also pass `fetch_names_code` (a chunk's `report_code` is one of its fetch's codes). Join these two; never re-implement the rule.
- **pg-partial-index-literals** (direct: sym:backend/app/repositories/raw_fetches.py::_candidate_codes is in backend/app/repositories/raw_fetches.py; verified b9cf9a3 2026-11-05): Under asyncpg, Postgres uses a partial index only when the query's predicate value is a SQL literal, not a bound parameter. That is why `_candidate_codes` uses `literal_column("'public'")`, so `ix_raw_reports_public_checked` matches. To prove a plan, run EXPLAIN after `SET LOCAL enable_seqscan = off` and assert the index appears, as `test_047_stored_reports_pg.py` does.
- **raw-fetches-no-query-text** (direct: file:backend/app/repositories/raw_fetches.py; verified b9cf9a3 2026-11-05): `raw_fetches` rows keep the params, report codes and payload, never the GraphQL query text. Anything that depends on the query's shape has to be decided when the row is written, the way `own_summary` is, or inferred from the body. The KB backfill skips stored tables whose metric it can't infer from the body.
- **raw-fetches-own-summary-flag** (direct: sym:backend/app/repositories/raw_fetches.py::is_own_summary is in backend/app/repositories/raw_fetches.py; verified b9cf9a3 2026-11-05): `own_summary` marks rows written by our own `ReportSummary` query. `is_own_summary` matches the query text whole, so a hand-written look-alike never qualifies. `upsert_raw_fetch` sets the flag on insert and on the unchanged-body update path too (051 QA BUG-002), so a write path that skips it hides that summary from the stored-reports lookup.
- **stored-reports-lookup-candidates** (direct: sym:backend/app/repositories/raw_fetches.py::list_visible_summaries is in backend/app/repositories/raw_fetches.py; verified b9cf9a3 2026-11-05): On Postgres the stored-reports lookup reads only own-summary rows that name a code confirmed public, or granted to the tenant, since `since` (`_candidate_codes`). The partial GIN index `ix_raw_fetches_own_summary_codes` serves it. Visibility itself still comes from `fetch_visible_clause`. `SUMMARY_LIST_TIMEOUT_MS` is set as a transaction-local statement_timeout and stays in force for the rest of the caller's transaction.
- **fk-checks-bypass-rls** (component: comp:postgres covers backend/app/repositories/raw_fetches.py; verified b9cf9a3 2026-11-05): Postgres foreign-key checks ignore RLS. A tenant-scoped row that references another tenant table needs a composite FK `(x_id, tenant_id) -> (id, tenant_id)` plus `UNIQUE(id, tenant_id)` on the target, as `kb_chat_chunks -> conversations` has (0019). Without one, a workspace's insert can name another workspace's row. `messages.conversation_id` is still a plain FK (backlog); the callers check ownership first.
- **index-migrations-concurrently** (component: comp:postgres covers backend/app/repositories/raw_fetches.py; verified b9cf9a3 2026-11-05): Index migrations run `create_index`/`drop_index` with `postgresql_concurrently=True` inside `op.get_context().autocommit_block()` (see 0020 and 0021), so they don't lock `raw_fetches`. Prove each one up, down and up again against the `DATABASE_OWNER_URL` that `pg.py up <you>` prints (the owner role), not the runtime URL.
- **pg-tests-shared-db** (component: comp:postgres covers backend/app/repositories/raw_fetches.py; verified d4ccc69 2026-11-07): The Postgres tests (`*_pg.py`, `test_rls.py`, via `TEST_DATABASE_URL`) share one long-lived database with no reset between tests. Use unique test data (fresh UUIDs and report codes), and never assert exact result lists over global tables (`raw_fetches`, `kb_chunks`, `spec_guides`): other tests' rows are there too.
- **boss-summary-shared** (neighbour: file:backend/app/services/kickoff_prefetch.py called by backend/app/api/raids.py::investigate_raid; verified 32010a6 2026-11-05): `get_report_fights` caps the fight list (`_acap`, 60k chars) but returns `last_kill` and the per-boss summary (`boss_summary`) outside it, with keystone runs excluded, so "the last boss kill" survives long nights. `kickoff_prefetch` imports `boss_summary` to pick the same fights, so keep its signature and keys (`last_kill_fight_id`, `last_pull_fight_id`) stable.
- **uploader-text-neutralise** (neighbour: file:backend/app/kb/search.py calls backend/app/repositories/raw_fetches.py::fetch_visible_clause; verified b9cf9a3 2026-11-05): Uploader-controlled WCL text (player names, report titles, guilds) reaches the model only through `report_tools.neutralise`, then a cap (`_bounded`/`_bounded_strings`, `MAX_NAME_CHARS`). KB search uses the same neutraliser for its `<data>` blocks. Neutralise after projecting down to the fields you return (QA PERF-001), and cap after neutralising, because NFKC can lengthen text.
