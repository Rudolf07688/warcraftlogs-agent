---
id: ws-refresh-actor-patch-signature
anchors: [sym:wcl_agent/cache/cache.py::set_refresh_actor, file:backend/app/api/ws.py]
by: dev-2 Tomas
source: meta/team/dev-2.md L15
verified: 03a3982 2026-11-07
---
The ws tests (`test_turn_path`, `test_048_empty_outcome`, `test_model_fallback_ws`,
`test_conversation_titles` and others) patch `ws_mod.set_refresh_actor` with
`lambda *_: None`. Adding a keyword argument where `ws.py` calls it breaks all of them. Add a
new function instead, as `abandon_turn` did.
