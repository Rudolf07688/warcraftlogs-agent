# Tasks: Thinking status line and interim text as status

**Input**: `specs/080-thinking-status/` (plan.md, spec.md, research.md, contracts/stream-events.md)
**Tests**: required (security-core, D18): hostile inputs first, asserted where the guard acts.

## Phase 1: Setup

- [X] T001 Add `ThinkingFrame` and `InterimFrame` (type literal, `text` max_length 120) to backend/app/schemas.py

## Phase 2: Foundational

- [X] T002 Add `_status_line(text)` (clean + first sentence + 80-char cap) and the THINKING_INTERVAL_S throttle clock to backend/app/agent_runner.py

## Phase 3: User Story 1 - status line from thinking (P1)

- [X] T003 [P] [US1] Runner tests in backend/tests/test_080_thinking_runner.py: hostile thought text (HTML, md link, bold, fence, 10k no sentence end, newlines/controls/ANSI/bidi) → frame text clean and capped; throttle ≤1/s (fake clock); no thinking after answer text; sub-agent author ignored; Claude contract example (partial Part thought=True) yields thinking; non-partial aggregate used only without partials; USER_ID job records unchanged
- [X] T004 [US1] Yield `thinking` records from `_run_turn` for chat turns in backend/app/agent_runner.py; document in its docstring
- [X] T005 [US1] Forward `thinking` as ThinkingFrame in backend/app/api/ws.py (never into tokens)
- [X] T006 [P] [US1] Frontend tests in frontend/src/App.thinking.test.tsx: hostile text renders inert (no img/a/strong/code), capped; hidden after first token; thinking frame after answer start ignored; generic "Thinking… Ns" after 3 s with fake timers; cleared on done
- [X] T007 [US1] Frame types in frontend/src/api/wsClient.ts; thought + activity state in frontend/src/App.tsx; ThinkingLine in frontend/src/components/MessageList.tsx; label in frontend/src/toolLabels.ts; style in frontend/src/styles.css

## Phase 4: User Story 2 - kept answer starts at the verdict (P1)

- [X] T008 [P] [US2] Runner tests (same file): interim text → tool call yields `interim` before `tool_start`, final tokens without paragraph prefix; text after a call retracted at tool result; interim + no answer → closing token alone
- [X] T009 [P] [US2] WS tests in backend/tests/test_080_thinking_ws.py: stored message = tokens after last interim (no report code / retry line); KB offer gets only final text; superseded/dropped mid-segment saves the live segment, after retraction saves nothing; client thinking/interim frame rejected, nothing echoed
- [X] T010 [US2] Yield `interim` from `_run_turn` (chat only) in backend/app/agent_runner.py
- [X] T011 [US2] Clear tokens and forward InterimFrame in backend/app/api/ws.py
- [X] T012 [US2] Frontend: `interim` clears stream text, shows status; done content = final segment (frontend/src/App.tsx, test in frontend/src/App.thinking.test.tsx)

## Phase 5: Polish

- [ ] T013 mutate.py bites: thinking suppressed after answer; author filter; sanitizer; ws tokens.clear on interim; frontend text-only render
- [ ] T014 Existing runner/ws suites green (test_046_empty_turn, test_tool_start_once, test_turn_path, test_048_empty_outcome, test_proposal_ws); guards.py; GitNexus detect-changes; check.py receipt

## Dependencies

T001, T002 → US1 and US2. US2's runner task (T010) shares `_run_turn` with T004: do T004 first.
Tests [P] can be written in parallel with each other; implementation is sequential per file.
MVP: US1 + US2 together (one sprint stream).
