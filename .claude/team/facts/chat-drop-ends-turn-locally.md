---
id: chat-drop-ends-turn-locally
anchors: [file:frontend/src/App.tsx, sym:backend/app/api/ws.py::_persist_partial]
by: dev-2 Tomas
verified: 32010a6 2026-11-05
---
App.handleStatus ends a streaming turn when the socket drops (partial text kept, note in the
error line, composer free); the next open reloads that chat (reloadAfterDrop). The backend saves
a status=partial message only when the process survives (_persist_partial); after a restart the
reload re-appends the local partial. The Composer is disabled while disconnected, so tests
cannot click send mid-drop. Partial and `done` answers go only into the open chat; dropRef is
cleared by sendText and selectConversation.
