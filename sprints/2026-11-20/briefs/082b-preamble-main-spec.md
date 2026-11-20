# Brief 082b-preamble-main-spec (dev-3 Nils, follow-up hunk)

- **Feature / branch:** 082 follow-up / `082b-preamble-main-spec`
- **Tier:** S. **Model / effort:** sonnet, medium.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-e` (check out a new branch from the base). **Base ref:** `ef2ae25` (sprint-2026-11-20 tip, all five streams merged).
- **Seat:** dev-3 (Nils). Nobody else is building now.
- **Security-core:** no. **Migration:** none.

## What (decision:082-ws-hunk, sc-575 AC "the agent reads the stored class/spec (main_class/main_spec, stored rankings) before asking")
082 added keyword-only `main_class` / `main_spec` to `profile_context.build_preamble` (merged). The call site
`backend/app/api/ws.py::_build_turn_preamble` doesn't pass them yet. Read the workspace's profile settings
(`backend/app/db/repository.py::get_profile_settings`) in `_build_turn_preamble` and pass `main_class` /
`main_spec` to `build_preamble`. No settings row: pass nothing (preamble unchanged).

One test from the call site (reuse the ws test helpers in `backend/tests/test_proposal_ws.py`, or call
`_build_turn_preamble` directly with a session): a workspace with saved main class/spec gets the main line in the
preamble; one without gets the unchanged preamble. Mind the facts below (don't add a keyword where ws.py calls
`set_refresh_actor`; the preamble must not hold anything across a wait).

## File footprint (board owner:* keys, to nils)
- `backend/app/api/ws.py` (the `_build_turn_preamble` function only; Edda's 080 is merged, the file is free)
- new `backend/tests/test_082b_*.py`
GitNexus: `impact` on `_build_turn_preamble` before editing; `detect-changes` once before hand-off.

## Hand-off
Commit, `check.py run --as nils --base ef2ae25` on the committed head, post a `handoff`, return about 10 lines with
the RESULT/RECEIPT lines and your `Retro:` line. sc-575 is already Under Review: no Shortcut moves.

## Known facts
- **ws-refresh-actor-patch-signature**: ws tests patch `ws_mod.set_refresh_actor` with `lambda *_: None`; never add a keyword argument at its call site.
- **ws-test-helpers**: reuse `_identity`, `_quiet`, `_ctx_stream`, `_tool_end`, `_run` from `backend/tests/test_proposal_ws.py`.
- **profile-context-class-from-known-player** (yours, 082): the preamble fills a missing class from the matching known player.
- **pg-tests-shared-db**: Postgres tests share one DB; unique data, no exact global lists.
