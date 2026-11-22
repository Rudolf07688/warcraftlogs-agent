---
id: runner-interim-retraction
anchors: [sym:backend/app/agent_runner.py::_run_turn, sym:backend/app/api/ws.py::_run_chat_turn, file:frontend/src/App.tsx]
by: dev-5 Edda
verified: 9107884 2026-11-22
---
On chat turns an 'interim' record means all answer text so far was progress; ws.py
clears its tokens before sending the frame (085), App clears streamRef. Only text <= INTERIM_MAX_CHARS,
not beside a PRESENTING_TOOLS call, is retracted; a turn ending
without an answer, or on a tool call never answered, re-emits the retracted text as a token. Answer = tokens after the last interim.
Jobs (USER_ID) get none of this. 'thinking' needs event.author == agent name in fakes.
