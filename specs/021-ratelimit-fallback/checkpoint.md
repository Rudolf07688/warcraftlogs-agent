# Checkpoint: 021 rate-limit fallback (dev-a-021)

Resume from here after a context compaction.

## Where things stand

- Worktree `/home/rudolf/dev/wcl-worktrees/dev-a`, branch `021-ratelimit-fallback`, base `cc3c783`
  (sprint tip after 020). Baseline suite at base: 1008 passed / 3 skipped / 1 deselected.
- Spec signed off; plan and tasks approved by the scrum master (solo, no sub-agents).
- sc-164 is In Progress. Do not move it until the scrum master says Under Review.
- `.specify/feature.json` is locally pointed at specs/021; restore it (`git checkout -- .specify/feature.json CLAUDE.md`) before every commit. Never commit CLAUDE.md, AGENTS.md, todo.md, .specify/*.

## Decisions (see spec Clarifications, research.md)

- Per-request fallback inside `RetryingGemini`/`RetryingClaude` via a new `generate_with_fallback`; on `ModelRateLimited` (only raised when nothing streamed) set `llm_request.model` to the sibling and re-run once. ADK reads the model from the request (research R2 line citations).
- One switch per turn via `TurnStats.fallback_model` / `switched_to` / `switch_index`; only the chat socket sets `fallback_model`; only requests with `llm_request.model == stats.model` are touched.
- Sibling: `sibling_model(model, served)` by the discovery regexes; first peer ↔ second, others → first. Generic for Claude (Q3=A), which has no sibling today.
- Messages: no sibling → feature 011 `RATE_LIMITED_MESSAGE`; switched and sibling busy → "Both <class> models are rate-limited right now. Please try again in about a minute." Both code `rate_limited`; ws decides by a local flag set when the `model_fallback` record passes.
- Notice: `ModelFallbackFrame{from_model,to_model}` → status line + note under the reply; live only; selector unchanged; next turn on the chosen model.
- Gemini thought-signature guard (R5, Complexity Tracking): copies only; test that stored events are not mutated; owner live check.
- Untouchable: `generate_with_retry`, `make_before_model_callback`, and the existing tests (model_retry, runner_retry, ws_rate_limit, greeting, guide, titles) stay unedited.

## Files

Granted: wcl_agent/llm/models.py, wcl_agent/llm/model_retry.py, backend/app/model_state.py,
backend/app/agent_runner.py, backend/app/api/ws.py, frontend/src/api/wsClient.ts,
frontend/src/components/MessageList.tsx, frontend/src/toolLabels.ts, documentation/ai_guide.md (1 line),
backend/tests/test_model_fallback{,_ws,_history}.py, specs/021-ratelimit-fallback/**.
Queued (after 022 merges, then rebase): backend/app/schemas.py, frontend/src/types.ts, frontend/src/App.tsx.

## Implementation starts at

tasks.md T001 → Phases 2–4 (T002–T016a). Phase 5 (T017–T025) waits for the queued files.

## Progress (2026-10-25)

- Done and committed: T001–T016a (e24c99f backend fallback + runner; 67af96e socket plumbing,
  split message, SC-007 history test), T020/T022/T026 (39245f8 Frame type, fallbackLabel,
  ai_guide line). Full suite: 1046 passed / 3 skipped / 1 deselected; frontend build green.
- Remaining, waiting for 022 to merge (then rebase onto the sprint tip): T017 ModelFallbackFrame
  in schemas.py, T018 forward it in ws.py (the `model_fallback` branch currently only sets
  `switched`), T019 frame assertion in test_switched_turn_stores_the_reply_once, T021 types.ts,
  T023 App.tsx, T024 MessageList.tsx note (shadcn search first), T025 build, T027–T029.

## Done (2026-10-25)

- Rebased onto sprint tip ee69ae4 (022 merged); Phase 5 committed (6d23209). All 29 tasks
  done. Suite 1060 passed / 3 skipped / 1 deselected (1022 baseline + 38 new); frontend
  build green. Handed off to the scrum master; sc-164 stays In Progress until told.
