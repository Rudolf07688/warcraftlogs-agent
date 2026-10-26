# Quickstart: verify 029 (capability summary + profile proposals)

All commands run from the worktree `/home/rudolf/dev/wcl-worktrees/dev-a`. No model and no
WCL calls are needed. Never read the owner's `.env`; boot only with dummy credentials.

## 1. Backend suite (AC 8, SC-006)

```bash
uv run --extra test pytest -q
```

Baseline on 1da8bca: 1066 passed, 3 skipped, 1 deselected. Expect the same plus the new
tests, with no new failures. `backend/tests/test_profile.py` is unchanged (AC 4).

## 2. Feature tests by acceptance criterion

| AC | Command | Shows |
|---|---|---|
| 1, 2 | `uv run --extra test pytest -q backend/tests/test_capabilities.py backend/tests/test_prompt_contract.py` | Generated summary; add/remove a fake tool; budget ≤ 4,000 chars and ≤ 160 per line; can/cannot and app-facts lines; no web-search line on Claude |
| 3, 6 | `uv run --extra test pytest -q backend/tests/test_profile_tools.py` | Tool returns the contract shape and never writes; > 30 items error; fails closed without an identity; hostile name → `invalid_name`; declarations for Gemini and Claude; scripted agent turn |
| 4, 5 | `uv run --extra test pytest -q backend/tests/test_profile_proposals.py` | Execution through `profile_service` (spy); cross-tenant / cross-user → not_found; expired; double execute; per-item applied/skipped/failed; guide tasks after commit; `friend_limit` and the realm-slug duplicate over REST |
| 7 | see §3 | Migration 0016 up/down, RLS |

## 3. Postgres: migration 0016 and RLS (AC 7)

Throwaway container on the sprint's port 15429 (never `docker compose`, never 5432):

```bash
docker run -d --rm --name wcl-029-pg -e POSTGRES_USER=wcl -e POSTGRES_PASSWORD=wcl \
  -e POSTGRES_DB=wcl -p 15429:5432 postgres:17
# create the non-privileged runtime role (as the repo's postgres-init does), then:
DATABASE_OWNER_URL=postgresql+asyncpg://wcl:wcl@localhost:15429/wcl \
DATABASE_URL=postgresql+asyncpg://wcl_app:wcl_app@localhost:15429/wcl \
  uv run alembic -c backend/alembic.ini upgrade head
uv run alembic -c backend/alembic.ini downgrade -1   # drops profile_proposals + policy
uv run alembic -c backend/alembic.ini upgrade head
TEST_DATABASE_URL=postgresql+asyncpg://wcl_app:wcl_app@localhost:15429/wcl \
  uv run --extra test pytest -q backend/tests/test_rls.py backend/tests/test_profile_proposals.py
docker stop wcl-029-pg
```

Expect upgrade, downgrade and upgrade to complete with no errors. `\d profile_proposals`
shows the `tenant_isolation` policy and FORCE RLS. The Postgres-only tests pass, where they
are skipped in the SQLite run.

## 4. Frontend (D8 message)

```bash
cd frontend && npm run build
```

A 51st friend add on the Profile page shows "You've reached the friend limit. Remove a
friend before adding another." (live check by the owner at Under Review).

## 5. Live (optional, owner)

In chat: "add Thrall-Tarren Mill EU and Jaina-Tarren Mill EU to my friends". Barnaby calls
`propose_profile_changes` once and says nothing has changed yet. The profile is unchanged
until 031's card approves it. "What can you do?" lists his tools, what he can change, and
the app features from D13.
