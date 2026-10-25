# Quickstart: verifying feature 019

All commands run from the worktree root (`/home/rudolf/dev/wcl-worktrees/dev-b`).

## Automated

```bash
uv run --extra test pytest -q                                  # whole backend suite
uv run --extra test pytest -q backend/tests/test_conversation_pinning.py \
  backend/tests/test_conversation_migration.py                 # phase 1
uv run --extra test pytest -q backend/tests/test_conversation_titles.py   # phase 2
cd frontend && npm run build                                   # tsc + vite
```

| Acceptance criterion (plan F2) | Covered by |
|---|---|
| AC1: Conversations above Raids, both toggles and counts | Manual check 1; `Sidebar.tsx` render order |
| AC2: pin and unpin from the sidebar and the header, Pinned group, survives reload and re-login | Manual check 2; `test_conversation_pinning.py` (state persisted and listed) |
| AC3: `pinned_at`, migration 0012 up and down, tenant-scoped PATCH, another tenant gets 404 | `test_conversation_pinning.py::test_patch_foreign_conversation_is_404`, `test_conversation_migration.py`, manual check 4 (Postgres) |
| AC4: title of at most 60 chars, plain, from the first exchange, via the retry helper | `test_conversation_titles.py` (`clean_title` cases, generation with a fake model, the policy passed to `generate_with_retry`) |
| AC5: off the chat path, at most once, failure or 429 keeps the excerpt | `test_conversation_titles.py` (once-only, rate-limited, timeout, `done` sent before the job runs) |
| AC6: an explicit title is kept | `test_conversation_titles.py::test_explicit_title_never_claimed` (raid investigation path) |
| AC7: the sidebar updates without a reload | `test_conversation_titles.py` (frame sent after save); manual check 3 |
| AC8: backend tests with the model faked | all of the above; `conftest.py` makes `schedule_title` a no-op for every other test |

## Manual (needs the app running; ask the scrum master for a port)

1. **Order**: sign in with at least one chat and one raid. Conversations is above Raids.
   Collapse and expand each one; the counts stay.
2. **Pinning**:
   - Hover a chat, click the pin. It moves to "Pinned" at the top.
   - Open another chat and pin it from the header (the toggle shows as pressed). It goes
     above the first pin.
   - Reload, then sign out and back in: both are still pinned.
   - Unpin one from the header: it goes back to its place by last activity.
   - Delete a pinned chat: it disappears.
3. **Generated names** (phase 2):
   - Start a new chat with a long rambling question. The reply streams as usual, and
     within about 10 s the sidebar name changes to a short title with no reload.
   - Send a second message: the name doesn't change.
   - Click "Investigate" on a raid: the raid name stays after the reply.
   - With `WCL_SUGGEST_MODEL` set to a bogus id, start a new chat: the reply works, there
     is no error, and the excerpt name stays.
4. **Migration on Postgres** (local db only):

   ```bash
   cd backend
   uv run alembic upgrade head
   uv run alembic downgrade 0011_guide_content_types
   uv run alembic upgrade head
   ```

   Before the first upgrade, `SELECT count(*) FROM conversations` shows a non-zero
   number. After upgrading, every existing row has `title_source='legacy'` and
   `pinned_at IS NULL`. After the downgrade, both columns are gone and the row count is
   unchanged.
