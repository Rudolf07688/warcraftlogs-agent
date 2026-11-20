# Checkpoint: 080 thinking status

## Decisions (board)
- scope:080:interim-segment: `interim` = drop all answer text so far; emitted at the round's first new tool call, or at its tool result for text after a call.
- scope:080:partial-save: interrupted mid-segment saves what the live view held; retracted text never saved.
- scope:080:chat-only: new records only when `user_id != USER_ID`.
- scope:080:status-line: first sentence of the latest thought paragraph, cleaned, 80 chars, ≤1/s, root agent only, none once the segment has text; generic "Thinking… Ns" in the browser.
- owner:backend/app/schemas.py granted (#68) for ThinkingFrame / InterimFrame.

## Files
backend/app/schemas.py, backend/app/agent_runner.py, backend/app/api/ws.py,
backend/tests/test_080_thinking_runner.py, backend/tests/test_080_thinking_ws.py,
frontend/src/api/wsClient.ts, frontend/src/App.tsx, frontend/src/components/MessageList.tsx,
frontend/src/toolLabels.ts, frontend/src/styles.css, frontend/src/App.thinking.test.tsx

## Where implementation starts
T001 (schemas) and T002 (`_status_line` in agent_runner.py), then runner tests (T003, T008).
