# Brief 074-onboarding-profile-setup

- Feature **074**, branch `074-onboarding-profile-setup`, tier **M** (one Spec Kit pass, no
  gates; answer clarify yourself as `scope:074:<topic>` decisions). Model opus, effort high.
- Seat **dev-5** (new seat: claim it with `member.py claim` as `member.py me` shows).
  Worktree `/home/rudolf/dev/wcl-worktrees/dev-e`. Stream type: app full-stack.
- Security-core: **no**, as long as the new data lives in columns of an existing
  tenant-scoped table or in a new table with the same RLS shape as its neighbours. If you add a
  table, say so in a `notice`: the PO then runs a qa-security review at hand-off.
- **Migration granted:** revision `0023_profile_main_spec`, `down_revision =
  "0022_pg_stat_statements"`, file `backend/migrations/versions/0023_profile_main_spec.py`.
  Prove it up, down, up against `DATABASE_OWNER_URL` from `pg.py up <you>`.

## Stories (epic 162 "onboarding", plus one prompt-size chore)
- sc-166 (2) "Onboarding: send new accounts to profile setup (skippable)": "As a new player, I
  want to land on the profile page right after creating my account, with a prompt to add at
  least one character that I can skip, so the app knows who I am without forcing me."
  Todo: "On account creation take the player straight to the profile page and ask them to fill
  in at least one character — not forced / skippable".
- sc-167 (3) "Onboarding: main class/spec and main content selector": "As a new player, I want
  a simple selector for my main class (and spec) and my main content (Raid, M+ or both), saved
  to my profile, so the app can tailor guides and answers to what I play."
  Todo: "Also include a simple selector to select their main class — Also select main content
  (Raid / M+ or both)". Saving it is the AC; using it in guides/answers is **not** in scope
  (that is sc-168 and later: post `backlog:` notices, no code).
- sc-514 (1) "Profile change schema sends developer notes to the model on every request":
  "`ProfileChangeIn`'s class docstring in `backend/app/schemas.py` is developer text (\"D4,
  C14\", \"no length limits on purpose\"). Pydantic sends it to the model as the `$defs`
  description of `propose_profile_changes`, about 70 tokens on every request of every turn.
  Fix: move the developer notes to a comment; keep only what the model needs (or nothing).
  Acceptance: `test_064_prompt_budget` budget lowered by the saved amount; the schema
  description no longer contains the notes." It's here because you own `schemas.py`.
  `tokens.py` measures the request size offline.

## Notes from the PO
- Account creation is invitation acceptance (`AcceptInvitePage.tsx` sends the browser to
  `/app` today); check whether an admin-created first login also counts as "new account".
- Class/spec values come from the one class/spec map the app already has; the server rejects
  anything else. Content is one of raid / mplus / both (or unset).
- The selector lives on the profile page (and is part of the onboarding prompt); `CharactersTab.tsx`
  belongs to Ansel (075) this sprint, so put your UI in `ProfilePage.tsx` or new components.

## File footprint (you own the shared files this sprint; others build around them)
- Backend: `backend/app/db/models.py`, `backend/app/db/repository.py`, `backend/app/schemas.py`,
  `backend/app/api/profile.py`, `backend/app/services/profile_service.py`,
  `backend/migrations/versions/0023_profile_main_spec.py` (new),
  `backend/tests/test_074_*.py` (new), `backend/tests/test_profile.py`,
  `backend/tests/test_064_prompt_budget.py` (budget number only), `backend/tests/test_rls.py`
  (only if you add a table)
- Frontend: `frontend/src/types.ts`, `frontend/src/api/restClient.ts`,
  `frontend/src/api/restClient.test.tsx`, `frontend/src/pages/ProfilePage.tsx`,
  `frontend/src/pages/AcceptInvitePage.tsx`, `frontend/src/pages/LoginPage.tsx`,
  `frontend/src/auth/**`, new files under `frontend/src/components/onboarding/**`, new tests
  beside them
- `specs/074-onboarding-profile-setup/**`
- Others build on base de66bdd without your changes: keep existing exports and response fields
  of the shared files backward compatible (add, don't rename).

## Hostile inputs (rule 10)
- Redirect target after account creation taken from the URL (`?next=//evil.example`,
  `/\evil.example`, `javascript:`) → only fixed internal paths are ever navigated to.
- Class/spec/content values outside the map (`"Warrior "`, `"warrior"` vs `"Warrior"`, a
  spec of another class, 10 000 chars, `null` where required) → 422, nothing stored.
- Tenant comes from the session only, never the body: a body with another `tenant_id` or
  character id changes nothing elsewhere (assert on the stored rows).
- The "skip" must be honoured: skipping never blocks the app and the prompt does not come
  back on every load (assert the state that decides it, not the text).
- If you add a table: one RLS test that another tenant can't read or write it.

## Live pre-check
If a question needs the real stack, post `live-check:074-pre` with the exact command; team-lead
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

Team facts for `backend/app/db/models.py`, `backend/app/db/repository.py`, `backend/app/schemas.py`, `backend/app/api/profile.py`, `backend/migrations/versions/`, `frontend/src/types.ts`, `frontend/src/api/restClient.ts`, `frontend/src/pages/ProfilePage.tsx`, `frontend/src/pages/AcceptInvitePage.tsx`, `backend/tests/test_064_prompt_budget.py`, and the paths you run: `.claude/team/pg.py`, `.claude/team/tokens.py`, `.claude/team/check.py` (`python3 .claude/team/facts.py for ...`). Trust them, but re-check one marked STALE before relying on it; record a new lesson with `facts.py add`.

- **fk-checks-bypass-rls** (direct: sym:backend/app/db/models.py::KbChatChunk is in backend/app/db/models.py; verified b9cf9a3 2026-11-05): Postgres foreign-key checks ignore RLS. A tenant-scoped row that references another tenant table needs a composite FK `(x_id, tenant_id) -> (id, tenant_id)` plus `UNIQUE(id, tenant_id)` on the target, as `kb_chat_chunks -> conversations` has (0019). Without one, a workspace's insert can name another workspace's row. `messages.conversation_id` is still a plain FK (backlog); the callers check ownership first.
- **index-migrations-concurrently** (direct: file:backend/migrations/versions/; verified b9cf9a3 2026-11-05): Index migrations run `create_index`/`drop_index` with `postgresql_concurrently=True` inside `op.get_context().autocommit_block()` (see 0020 and 0021), so they don't lock `raw_fetches`. Prove each one up, down and up again against the `DATABASE_OWNER_URL` that `pg.py up <you>` prints (the owner role), not the runtime URL.
- **raw-fetches-no-query-text** (direct: sym:backend/app/db/models.py::RawFetch is in backend/app/db/models.py; verified b9cf9a3 2026-11-05): `raw_fetches` rows keep the params, report codes and payload, never the GraphQL query text. Anything that depends on the query's shape has to be decided when the row is written, the way `own_summary` is, or inferred from the body. The KB backfill skips stored tables whose metric it can't infer from the body.
- **pg-tests-shared-db** (file: file:backend/tests/ contains backend/tests/test_064_prompt_budget.py; verified d4ccc69 2026-11-07): The Postgres tests (`*_pg.py`, `test_rls.py`, via `TEST_DATABASE_URL`) share one long-lived database with no reset between tests. Use unique test data (fresh UUIDs and report codes), and never assert exact result lists over global tables (`raw_fetches`, `kb_chunks`, `spec_guides`): other tests' rows are there too.
- **vitest-no-jest-dom** **STALE** (file: file:frontend/src/ contains frontend/src/types.ts; verified 1ee750a 2026-11-05): The frontend's Vitest setup has no `@testing-library/jest-dom`, so matchers like `toBeInTheDocument` don't exist. Assert on `textContent`, `toBeTruthy()` and plain values.
- **fetch-visible-clause-one-rule** (component: comp:postgres covers backend/app/db/models.py; verified b9cf9a3 2026-11-05): Visibility for the global tables (`raw_fetches`, `kb_chunks`) lives in the SQL of every read branch, and it has one definition: `raw_fetches.fetch_visible_clause`, the 039 rule (every code public or granted to the tenant since `since`). Rows derived from a fetch must also pass `fetch_names_code` (a chunk's `report_code` is one of its fetch's codes). Join these two; never re-implement the rule.
- **pg-partial-index-literals** (component: comp:postgres covers backend/app/db/models.py; verified b9cf9a3 2026-11-05): Under asyncpg, Postgres uses a partial index only when the query's predicate value is a SQL literal, not a bound parameter. That is why `_candidate_codes` uses `literal_column("'public'")`, so `ix_raw_reports_public_checked` matches. To prove a plan, run EXPLAIN after `SET LOCAL enable_seqscan = off` and assert the index appears, as `test_047_stored_reports_pg.py` does.
- **stored-reports-lookup-candidates** (component: comp:postgres covers backend/app/db/models.py; verified b9cf9a3 2026-11-05): On Postgres the stored-reports lookup reads only own-summary rows that name a code confirmed public, or granted to the tenant, since `since` (`_candidate_codes`). The partial GIN index `ix_raw_fetches_own_summary_codes` serves it. Visibility itself still comes from `fetch_visible_clause`. `SUMMARY_LIST_TIMEOUT_MS` is set as a transaction-local statement_timeout and stays in force for the rest of the caller's transaction.
- **chat-drop-ends-turn-locally** (neighbour: file:frontend/src/App.tsx calls frontend/src/api/restClient.ts::listConversations; verified 32010a6 2026-11-05): App.handleStatus ends a streaming turn when the socket drops (partial text kept, note in the error line, composer free); the next open reloads that chat (reloadAfterDrop). The backend saves a status=partial message only when the process survives (_persist_partial); after a restart the reload re-appends the local partial. The Composer is disabled while disconnected, so tests cannot click send mid-drop. Partial and `done` answers go only into the open chat; dropRef is cleared by sendText and selectConversation.
- **dialect-sql-compiles** (neighbour: file:backend/app/repositories/raw_fetches.py calls backend/app/db/repository.py::_insert; verified b9cf9a3 2026-11-05): Dialect-specific SQL inside a clause with a fixed signature is written as a `ColumnElement` subclass with one `@compiles` per dialect. In `raw_fetches.py`, `_NonEmpty` uses `jsonb_array_length` on Postgres and `json_array_length` on SQLite, and `_CodesVisible` works the same way. Callers keep one function that runs on both test engines.
- **faro-lazy-context** (neighbour: file:frontend/src/telemetry/context.ts called by frontend/src/api/restClient.ts::send; verified b9cf9a3 2026-11-05): The Faro packages load only through the dynamic `import()` in `telemetry/faro.ts`, and `context.ts` imports types only. New Faro-facing code (the socket, the REST client, error boundaries) calls `context.ts` functions, which are no-ops until `registerFaro`. Never add a static `@grafana/faro-react` import: it pulls Faro into the main bundle. That is why 060 wrote its own error boundary instead of `FaroErrorBoundary`.
- **raw-fetches-own-summary-flag** (neighbour: sym:backend/app/repositories/raw_fetches.py::upsert_raw_fetch calls backend/app/db/repository.py::_insert; verified b9cf9a3 2026-11-05): `own_summary` marks rows written by our own `ReportSummary` query. `is_own_summary` matches the query text whole, so a hand-written look-alike never qualifies. `upsert_raw_fetch` sets the flag on insert and on the unchanged-body update path too (051 QA BUG-002), so a write path that skips it hides that summary from the stored-reports lookup.
