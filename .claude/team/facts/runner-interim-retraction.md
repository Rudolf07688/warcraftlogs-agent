---
id: runner-interim-retraction
anchors: [sym:backend/app/agent_runner.py::_run_turn, sym:backend/app/api/ws.py::_run_chat_turn, file:frontend/src/App.tsx]
by: dev-5 Edda
verified: 2a2d3c0 2026-11-20
---
On chat turns an 'interim' record means: all answer text streamed so far was progress; ws.py
clears its tokens (after sending the frame), App clears streamRef. Only text <= INTERIM_MAX_CHARS,
not next to a PRESENTING_TOOLS call, is retracted, never after text was kept; a turn ending
without an answer re-emits the retracted text as a token. Answer = tokens after the last interim.
Jobs (USER_ID) get none of this. 'thinking' needs event.author == runner.agent.name in fakes.
