---
id: wcl-fakes-install
anchors: [file:backend/tests/wcl_fakes.py, file:wcl_agent/tools/]
by: dev-2 Tomas
source: meta/team/dev-2.md L23
verified: 32010a6 2026-11-05
---
Tool tests fake Warcraft Logs with `backend.tests.wcl_fakes.install(monkeypatch, responder)`.
It replaces `wcl_client.get_async_client`, which every `wcl_agent` module reaches WCL through.
`responder(query, variables)`, sync or async, returns the payload; the returned fake records
`.calls` and `.count(needle)`. To test the client itself, use `mock_async_client(handler)`, a
real client over `httpx.MockTransport`.
