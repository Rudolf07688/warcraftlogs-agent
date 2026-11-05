---
id: chat-drop-ends-turn-locally
anchors: [file:frontend/src/App.tsx, sym:backend/app/api/ws.py::_persist_partial]
by: dev-2 Tomas
verified: b67052b 2026-11-05
---
App.handleStatus ends a streaming turn when the socket drops (partial text kept, note in the
error line, composer free) and the next open reloads that chat (reloadAfterDrop). The backend
saves a status=partial agent message only when the process survives and sees the disconnect
(_persist_partial); a backend restart saves nothing, so the reload re-appends the local partial.
The Composer is disabled while disconnected, so tests cannot click send between drop and
reconnect.
