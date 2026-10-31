# Quickstart: verifying 034 (crucial epic-203 QA fixes)

All checks use fakes (no live model or WCL). Run from the worktree root.

## 1. Acceptance criteria → checks

| Plan AC | Check | Expect |
|---|---|---|
| 1 (sc-241) | `uv run --extra test pytest -q backend/tests/test_profile_tools.py -k raw_items` | Raw dicts through `FunctionTool.run_async`: realm null, region "", action "promote", played_role "Healer", 1 valid → 5 rows: 3 skipped (`invalid_realm`, `invalid_region`, `invalid_item`), 2 valid ("Healer" stored as `healer`); `status == "success"`; no exception |
| 1 (codes, roles) | `uv run --extra test pytest -q backend/tests/test_profile_proposals.py` | Blank / missing realm → `invalid_realm`, region → `invalid_region`; "DPS"/"TANK" accepted; unknown played_role dropped; unknown raid_role → `invalid_item`; non-dict element → `invalid_item` |
| 2 (sc-241) | `uv run --extra test pytest -q backend/tests/test_profile_tools.py -k unexpected` | A forced exception in the service → `{"status": "error", "error_message": <plain>}`, no exception text; scripted turn still ends with Barnaby's text |
| 3 (sc-242) | `uv run --extra test pytest -q backend/tests/test_proposal_routes.py` + §2 | Only the transitioning call saves the line (SQLite); Postgres overlap: one apply, 1 line, no 500, for approve x2 and cancel x2 |
| 4, 5 (sc-243) | `cd frontend && npm test` | `App.test.tsx`: switch / new chat mid-turn → no card in the open chat (done and error); reopen → once; no switch → attaches as before; status "Preparing profile changes" and a non-default spell |
| 6 | `uv run --extra test pytest -q` and `cd frontend && npm run build && npm test` | No new backend failures; build (incl. `tsc`) and tests pass |

## 2. Postgres overlap test (sc-242, required in the hand-off)

Throwaway container on the feature's port 15434 (never `docker compose`, never 5432):

```bash
docker run -d --rm --name wcl-034-pg -e POSTGRES_USER=wcl -e POSTGRES_PASSWORD=wcl \
  -e POSTGRES_DB=wcl -p 15434:5432 postgres:17
# migrations as the owner create the runtime role (0004_rls, APP_DB_USER/APP_DB_PASSWORD):
APP_DB_USER=wcl_app APP_DB_PASSWORD=wcl_app \
DATABASE_OWNER_URL=postgresql+asyncpg://wcl:wcl@localhost:15434/wcl \
DATABASE_URL=postgresql+asyncpg://wcl_app:wcl_app@localhost:15434/wcl \
  uv run alembic -c backend/alembic.ini upgrade head
TEST_DATABASE_URL=postgresql+asyncpg://wcl_app:wcl_app@localhost:15434/wcl \
  uv run --extra test pytest -v backend/tests/test_proposal_race_pg.py
docker stop wcl-034-pg
```

Expect both tests to pass (not skip). Without `TEST_DATABASE_URL` they are reported as skipped.

## 3. Live (owner, at Under Review)

- Ask Barnaby to add the players of a run where one player has no server: the card shows that row
  as "Skipped · realm unknown, add by hand", the others as normal rows; no error bubble.
- While he prepares it, the status line reads "Preparing profile changes".
- Start a request in chat A, switch to chat B before the answer ends: no card in B; back in A the
  card is under the answer.
- Approve the same card in two tabs at once: one "Done…" line, no "Couldn't apply" in either tab.
