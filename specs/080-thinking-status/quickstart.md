# Quickstart: verify 080

- Backend: `python3 .claude/team/check.py run backend/tests/test_080_thinking_runner.py backend/tests/test_080_thinking_ws.py --as edda`
- Frontend: `cd frontend && npx vitest run src/App.thinking.test.tsx`
- Live (team-lead, `live-check:080`): a multi-tool question on Gemini and on Claude: a status line
  under the spell cards during the gaps; no troubleshooting paragraph in the answer; reload shows
  the same answer.
