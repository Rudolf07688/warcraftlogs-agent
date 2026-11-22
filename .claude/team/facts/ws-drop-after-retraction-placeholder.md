---
id: ws-drop-after-retraction-placeholder
anchors: [sym:backend/app/api/ws.py::_run_chat_turn, file:frontend/src/App.tsx]
by: dev-5 Edda
verified: 9107884 2026-11-22
---
A drop (WebSocketDisconnect, or WebSocketDisconnected on a later send to the dead socket)
after an interim with no tokens kept stores a partial '(no response)' (085). The server learns of
a drop only at its next send, so App.reloadAfterDrop shows its local copy while nothing is saved
and rechecks (DROP_RECHECK_MS: 9 rechecks, 8 min) until a saved agent message replaces it. Cancel and error paths store nothing: the browser drops its copy.
