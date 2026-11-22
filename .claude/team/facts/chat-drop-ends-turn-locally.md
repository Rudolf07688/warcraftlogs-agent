---
id: chat-drop-ends-turn-locally
anchors: [file:frontend/src/App.tsx, sym:backend/app/api/ws.py::_persist_partial]
by: dev-2 Tomas
verified: 56b4a72 2026-11-22
---
App.handleStatus ends a streaming turn when the socket drops (partial kept, note, composer free);
the reconnect reloads that chat (reloadAfterDrop). The backend saves a partial only when its next
send fails, so while none is saved App rechecks (DROP_RECHECK_MS, 8 min) in one chain;
stopRechecks on send, chat open and new chat. After a restart the local partial stays. Composer
is disabled while disconnected: no send mid-drop in tests. sendText and selectConversation clear
dropRef.
