---
id: ws-drop-after-retraction-placeholder
anchors: [sym:backend/app/api/ws.py::_run_chat_turn, file:frontend/src/App.tsx]
by: dev-5 Edda
verified: 4fc12a3 2026-11-22
---
A turn ending by WebSocketDisconnect after an interim with no tokens kept stores a partial '(no
response)' (085). Reason: App.reloadAfterDrop re-appends its local partial whenever the chat's
last stored message is not an agent one (meant for a server restart), and that local copy can be
retracted text when the interim frame was lost with the socket. Cancel and error paths store
nothing in that case: the browser drops its copy there.
