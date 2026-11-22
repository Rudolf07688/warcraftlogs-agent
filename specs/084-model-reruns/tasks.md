# Tasks: 084 model re-runs and the runner

Bounds tests come before each path's code (developer rule 11).

## Phase 1: US1 Gemini empty STOP (P1, sc-586)
- [X] T001 [US1] Bound tests in backend/tests/test_084_reruns.py: an always-empty Gemini fake gets exactly one re-run; the re-run counts in model_requests and empty_retries; N such calls trip round_cap; empty-then-answer yields the answer; the held empty final is never passed on
- [X] T002 [US1] TurnStats.empty_retries/reruns, _count_rerun, _CallWatch/_watch, _empty_stop, RetryingGemini re-run in wcl_agent/llm/model_retry.py

## Phase 2: US2 Claude time bound and counting (P2, sc-580)
- [X] T003 [US2] Bound tests: a hung Claude stream (scripted transport) is cut at the bound, its HTTP stream closed, one low-effort re-run follows; a stream that keeps thinking past the bound (_clock) is cut; the re-run cut too ends the call; a cut after answer text keeps the text, no re-run; the budget re-run counts as a request; non-streamed calls are not bounded
- [X] T004 [US2] CLAUDE_CALL_TIMEOUT_S, ModelCallTimedOut, _within, _cut_response, RetryingClaude rework in wcl_agent/llm/model_retry.py
- [X] T005 [US2] budget_retries/empty_retries on the turn stats line in backend/app/agent_runner.py (+ test)

## Phase 3: US3 runner edges (P3, sc-582)
- [X] T006 [US3] Tests in backend/tests/test_084_runner_edges.py: re-run thoughts not spliced; held restored on pending ending; heading line sentence; record shapes pinned (contract:chat-status-records)
- [X] T007 [US3] Runner changes in backend/app/agent_runner.py (_status_line, _run_turn)

## Phase 4: Polish
- [X] T008 Mutation bites for the re-run cap and the time bound (mutate.py)
- [X] T009 Existing suites: test_079, test_080_thinking_runner, test_046_empty_turn, test_model_retry, test_runner_retry
- [X] T010 detect-changes, receipt, facts, hand-off
