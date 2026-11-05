---
id: cache-single-flight-starter-context
anchors: [sym:wcl_agent/cache/cache.py::_shared, sym:wcl_agent/cache/cache.py::_flight, sym:wcl_agent/client/wcl_client.py::AsyncWCLClient.query]
by: dev-3 Nils, dev-2 Tomas
source: meta/team/dev-3.md L14; meta/team/dev-2.md L19; meta/sprints/2026-11-01/board.jsonl #40, #134
verified: b9cf9a3 2026-11-05
---
Both single-flights, the cache's `_shared` and `AsyncWCLClient.query`, run the shared task in
the STARTER's copied context: every ContextVar read inside the load (`_Load`, tenant, turn)
is the first caller's. If the answer depends on the caller, key the flight by that scope (the
client appends `source.scope()`, the tenant) or let joiners reload: in the cache, a joined
unshareable load runs its own `_lookup`.
