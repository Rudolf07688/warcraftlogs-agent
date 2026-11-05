---
id: ws-test-helpers
anchors: [file:backend/tests/test_proposal_ws.py, file:backend/app/api/ws.py]
by: dev-2 Tomas
source: meta/team/dev-2.md L23
verified: b9cf9a3 2026-11-05
---
For backend WebSocket tests, reuse the helpers in `backend/tests/test_proposal_ws.py`
(`_identity`, `_quiet`, `_ctx_stream`, `_tool_end`, `_run`) rather than building a new chat
harness.
