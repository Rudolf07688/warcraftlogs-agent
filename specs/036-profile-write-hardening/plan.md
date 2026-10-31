# Implementation Plan: Profile write-path hardening

**Branch**: `036-profile-write-hardening` | **Date**: 2026-10-31 | **Spec**: [spec.md](spec.md)

## Summary

Five QA-debt stories on the agent's profile write path, all in one file cluster: keep
uploader-written report titles out of the standing context and bound what a proposal can
store or show (sc-221); scope the acting identity to the turn and add user-level RLS on
`profile_proposals` (sc-222, migration 0017); serialise character adds and key the working
profile by (identity, target) (sc-223); apply an approval in bulk, reuse transactions for
proposal reads and bound the guide fan-out (sc-225); refresh the architecture docs (sc-244).

## Technical Context

**Language/Version**: Python 3.12 (backend, FastAPI + asyncio, SQLAlchemy 2 async), TypeScript (React 19, Vitest)
**Primary Dependencies**: existing only; no new packages
**Storage**: PostgreSQL 17 (RLS, advisory locks); SQLite for the unit suite
**Testing**: pytest (`uv run --extra test pytest -q`), Postgres tests behind `TEST_DATABASE_URL`, Vitest
**Target Platform**: the existing web app
**Project Type**: web service + SPA
**Performance Goals**: approve round trips independent of item count; at most 3 concurrent guide jobs per approval
**Constraints**: footprint in the brief; REST manual entry rules unchanged (029 AC 4)
**Scale/Scope**: 1 migration, ~10 source files, docs

## Constitution Check

| Principle | How this plan complies |
|---|---|
| I Reuse | `roster.resolve_spec` for class/spec, `server_slug`, existing repo list functions, `tenant_scope`; the follow-up line's `_INVALID` set mirrors the card rule |
| II Small steps | one story at a time, each with its own tests and commit |
| III Simplicity | an advisory lock (no new table or queue); a local semaphore per approval (no worker pool); optional `db` params instead of new service functions |
| IV Typed boundaries | proposal items stay `ProposalItemOut`; no new untyped dicts across boundaries |
| V Async | all DB calls async; no blocking work added |
| VI GitNexus | impact before each symbol edit; detect-changes before each commit |
| VII shadcn | the card keeps its existing `Item`/`Badge` components; no new component needed |
| VIII Backlog | stories In Progress → Under Review; follow-ups as board `backlog:` notices |

No violations; Complexity Tracking empty.

## Design per story

### sc-221
- `profile_context._raid_run_ident`: zone name only. `_recent_block`: a tracked raid's label is
  used only when it was built from guild/zone/date (else `report CODE`).
- `capabilities._CAN_CHANGE`: add the own-message rule.
- `profile_proposals`: `_roster_class_spec(class, spec)` via `resolve_spec`; realm rule tightened
  to the realm form (≤ 24). Applied in `_validate` and `_skipped`.
- `ProposalCard.ItemRow`: identity-refused rows render the target and reason only.

### sc-222
- `ws._handle_turn`: `token = current_identity.set(...)` just before the stream `try`, reset in its
  `finally`.
- `background.spawn`: `loop.create_task(coro, context=contextvars.Context())`.
- `0017_proposal_user_rls`: drop `tenant_isolation`, create `tenant_user_isolation` (tenant AND
  user, USING and WITH CHECK); downgrade restores the tenant-only policy.

### sc-223
- `repository.lock_profile(session, tenant_id)`: `pg_advisory_xact_lock(hashtextextended(...))`,
  no-op off Postgres; called in `add_character` and at the start of `_apply`.
- `_profile` keyed by `(identity, target)`; `_check` looks up both roles explicitly.

### sc-225
- `_apply`: lock, load own + friends once, re-validate, then `repository.add_characters`
  (one batch), `set_raid_roles` (one `UPDATE … CASE … RETURNING id`), `delete_characters`
  (one `DELETE … IN … RETURNING id`); an id not returned is `failed · not_found`.
- `list_proposals`/`get_proposal(…, db=None)`; conversations route and ws capture pass theirs.
- `guide.schedule_character_guides(ids, tenant_id)`: one spawned task, semaphore of 3.

### sc-244
Docs only, per the story's locations.

## Project Structure

```text
specs/036-profile-write-hardening/  plan.md research.md data-model.md quickstart.md contracts/ tasks.md
backend/app/services/{profile_context,profile_proposals,background,guide}.py
backend/app/api/{ws,conversations}.py
backend/app/db/repository.py
backend/migrations/versions/0017_proposal_user_rls.py
wcl_agent/capabilities.py
frontend/src/components/ProposalCard.tsx (+ test)
backend/tests/…  documentation/architecture/…  documentation/designs/self-aware-agent/…
```

## Complexity Tracking

None.
