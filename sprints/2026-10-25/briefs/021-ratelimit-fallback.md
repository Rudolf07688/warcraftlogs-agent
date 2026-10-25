# Brief 021 — 429 fallback to the sibling model in the same class (plan F4 / 021)

| Field | Value |
|---|---|
| Feature number | 021 |
| Branch | `021-ratelimit-fallback` (set `GIT_BRANCH_NAME=021-ratelimit-fallback` for `/speckit-specify`) |
| Spec dir | `specs/021-ratelimit-fallback/` |
| Worktree | `/home/rudolf/dev/wcl-worktrees/dev-a` (track A) |
| Base ref | `sprint-2026-10-25` tip after 020 merged (the worktree is detached there) |
| Model / effort | opus / high |
| Shortcut stories | sc-164 (3) |
| Peer developer | `dev-b-022` (track B, welcome M+ runs; no shared files) |
| Scrum master | `scrum-master` (your only channel upward) |
| Plan | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/plan.md` (section F4 / 021) |
| Ownership ledger | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/ownership.md` |
| Decisions | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/decisions.md` (entry 7: Claude classes have no sibling, so they get the "try again shortly" message) |

## Plan section (verbatim)

## F4 / 021 — 429 fallback to the sibling model in the same class (Track A, third)

- **Stories:** sc-164 (3) Fall back to the second model in the same class on 429s.
- **Complexity:** high (switching model mid-turn with ADK and Anthropic).
- **Footprint:** `wcl_agent` `model_retry` and `models` (new paths), `backend/app/agent_runner.py`,
  `backend/app/api/ws.py`, `backend/app/model_state.py`, plus a small frontend notice
  (`frontend/src/App.tsx` or `StatusAlert.tsx`, `types.ts`) if a new event type is
  added.
- **Depends on:** F1. Takes the agent-loop files after F2's sc-155 hook has merged.
- **Acceptance criteria:**
  1. When a chat turn's model is still rate limited after the existing retry policy,
     the turn retries on the other discovered model of the same class. Gemini classes
     offer two versions (feature 016). If the turn is already on the second model, it
     switches back to the first.
  2. If both models of the class are rate limited, or the class has only one model
     (Claude classes today), the user gets a clear in-chat message to try again
     shortly. The agent loop and the socket survive, and the next message works.
  3. The user can see which model answered when a switch happened (a notice in the
     chat). There is at most one switch per attempt, so the fallback can't loop.
  4. The developer may implement the fallback at the turn level (re-run the turn on the
     sibling model) instead of per request, as long as 1–3 hold. A half-streamed reply
     must not be duplicated in the stored history.
  5. Tests cover these paths with fake 429 errors, for both the Gemini and the
     Anthropic call paths. No live Vertex call is needed in CI.

## Context

- Retry layer (feature 011): `wcl_agent/llm/model_retry.py` (`RetryPolicy`,
  `ModelRateLimited`, `is_rate_limited`, `generate_with_retry`, `RetryingGemini`,
  `make_before_model_callback`, `current_turn`/`TurnStats`). Turn runner:
  `backend/app/agent_runner.py`. Chat socket: `backend/app/api/ws.py` (`_handle_turn`).
  Model discovery and classes (feature 016): `wcl_agent/llm/models.py`,
  `backend/app/model_state.py`. Read `specs/011-*` and `specs/016-*` first.
- 018 moved `wcl_agent` into sub-packages, and the shared GitNexus index still has the old
  paths, so re-index your worktree with `--force` first.
- 019 added a title hook after `DoneFrame` in `ws.py` (`schedule_title`, a cheap model via
  `generate_with_retry`). Your change must not alter that hook's behaviour. If you
  change `generate_with_retry`'s contract, the title service is a caller.

## Tentative footprint (becomes a grant after `/speckit-plan`)

- `wcl_agent/llm/model_retry.py`, `wcl_agent/llm/models.py`, `backend/app/agent_runner.py`,
  `backend/app/api/ws.py`, `backend/app/model_state.py`.
- `backend/app/schemas.py` (a new frame or notice) is **held by 022** at the moment.
  Prefer reusing an existing frame type for the notice (e.g. the `model_retry` records
  the runner already emits). If you need a new frame, ask me: you get the file once 022
  declares it final or merges.
- Frontend notice: `frontend/src/App.tsx` and/or `frontend/src/components/StatusAlert.tsx`,
  `frontend/src/types.ts`, `frontend/src/api/wsClient.ts`, if a new event type is added.
  **022 holds `types.ts`, `restClient.ts` and `App.tsx`**, so check with me first. `StatusAlert.tsx` and `wsClient.ts` are free.
- Tests: new `backend/tests/test_model_fallback*.py`. Existing `test_model_retry.py`,
  `test_runner_retry.py` and `test_ws_rate_limit.py` only if behaviour there changes.
- **Not yours:** `wcl_agent/client/**` (022 after 020), `backend/app/services/recent_raids*`,
  `backend/app/services/conversation_titles.py`, `CLAUDE.md`, `AGENTS.md`, `todo.md`,
  `.specify/*`.

## Notes from the scrum master

- This is the hardest piece of the sprint: the agent loop and the ADK model binding.
  Before the plan, run GitNexus `impact` on `RetryingGemini`, `make_before_model_callback`,
  `stream_response` and `_handle_turn`, and report any HIGH or CRITICAL to me.
- In the plan, state the fallback level (turn-level re-run vs per request; AC 4 allows
  either), how a half-streamed reply is discarded so it isn't duplicated in stored history
  (AC 4), how "at most one switch per attempt" is enforced (AC 3), and how the Anthropic
  path's 429 surfaces vs Gemini's.
- Tests use fake 429s for both the Gemini and the Anthropic paths (AC 5). No live Vertex.
- Ports for any live check: app 18018, Postgres 15418, Redis 16318 (your own
  `docker run --rm`; no compose, no owner .env).
- Shortcut: move sc-164 to In Progress when you start. Reply "ACK" to every grant.
