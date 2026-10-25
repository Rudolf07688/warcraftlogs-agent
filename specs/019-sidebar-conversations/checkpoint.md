# Checkpoint: feature 019 (dev-b-019-v2)

**Status 2026-10-25: phase B done and handed off.** The branch is rebased on the sprint tip
f32b771 (after 018); `ast_refs.py` reports 0 findings. All 34 tasks are done. Full suite:
981 passed, 3 skipped, 1 deselected, 0 xfail (926 existing tests unchanged + 55 new).
Postgres API smoke on 18019/15419 (the pin flow, a foreign tenant gets 404, no CSRF gets 403,
a bad body gets 422, the pin survives a re-login) passed. A live title generation check
needs model credentials, so it is left to the product owner's live test. The phase A notes
below are history.


Resume from here after a context reset.

## Where things stand (2026-10-25, end of phase A)

- Worktree `/home/rudolf/dev/wcl-worktrees/dev-b`, branch `019-sidebar-conversations`,
  base `4227a86` (the sprint-2026-10-25 tip). Never push.
- Gates:
  - Spec signed off: the product owner chose A on Q1–Q5, plus FR-004a (a11y) and FR-018 (explicit at creation).
  - Plan and tasks approved.
- Phase A is **done** (commits `dad5f8c`, `39be321`, `739caa8`, `01a62d5`):
  - migration 0012, the model columns, and `create_conversation` setting `title_source`;
  - sc-154 (sidebar order);
  - sc-165 repository and UI (Pinned group, accessible `Toggle`s);
  - the sc-155 repository claim and write, `clean_title`, the explicit-caller tests, and the client `conversation_title` handling.
- Tests: 959 passed, 3 skipped, 1 deselected, **6 xfailed** (the PATCH route tests, strict). Baseline: 926 passed. The frontend build is green.
- Postgres check (T033 part 4) is done: a throwaway `postgres:17` on 127.0.0.1:15419 with dummy credentials, founder seeded by SQL, upgraded to 0011, 2 conversations seeded.
  - 0012 up: the existing rows are `legacy` with `pinned_at` NULL; the column default is `'auto'`; a new raw insert gets `auto`.
  - The runtime role (RLS) updates only with `app.tenant_id` set and sees 0 rows without it.
  - Down: both columns are dropped and all 3 rows are kept.
  - Up again: version `0012_conversation_pin_title`.
  - The container is stopped.
- Shortcut: sc-154 and sc-165 are In Progress. sc-155 is in Shortlist until phase B starts.
- GitNexus: an incremental `analyze --index-only` produced a corrupt index once (null-byte ids). Always use `--force` before `detect-changes`.

## Phase B (after the scrum master says 018 has merged)

1. Rebase onto the sprint tip (or reset and cherry-pick). Re-run `analyze --index-only --force` in the worktree. Move sc-155 to In Progress.
2. T012/T013 (first):
   - `ConversationOut.pinned_at` and `ConversationUpdate` in `schemas.py`;
   - the PATCH route in `conversations.py`;
   - remove the `_needs_schema` xfail marker in `test_conversation_pinning.py`, and tighten `test_patch_without_csrf_is_refused` to `(401, 403)`.
   - **No xfail may remain at hand-off.**
3. T022–T028:
   - `generate_title`, `retitle_conversation` and `schedule_title` in `services/conversation_titles.py`, importing `generate_with_retry`/`RetryPolicy`/`current_turn` from 018's new `model_retry` path;
   - `ConversationTitleFrame` in `schemas.py`;
   - the ws hook;
   - the conftest autouse stub (it must not change any existing test's count or behaviour; say so at hand-off);
   - the tests.
4. T032 (ai_guide lines), T033 manual UI checks 1–3 on port 18019, T034 final verification and hand-off.

## Open questions

None.
