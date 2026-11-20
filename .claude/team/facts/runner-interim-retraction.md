---
id: runner-interim-retraction
anchors: [sym:backend/app/agent_runner.py::_run_turn, sym:backend/app/api/ws.py::_run_chat_turn, file:frontend/src/App.tsx]
by: dev-5 Edda
verified: 3dcf75c 2026-11-20
---
On chat turns an 'interim' record means: all answer text streamed so far was progress. ws.py
clears its tokens, App clears streamRef, so the answer is the tokens after the last interim;
tests concatenating a chat turn's tokens must do the same. Jobs (USER_ID) get no interim or
thinking records and keep sc-302's paragraph join. 'thinking' lines come only from events whose
author equals runner.agent.name: fake runners need an agent name and event author to produce
them.
