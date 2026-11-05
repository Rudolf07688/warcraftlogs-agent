---
id: raw-store-probe-before-429
anchors: [sym:wcl_agent/client/wcl_client.py::AsyncWCLClient.query, sym:wcl_agent/client/wcl_client.py::set_fetch_source]
by: dev-2 Tomas
source: meta/sprints/2026-11-01/board.jsonl #40
verified: b9cf9a3 2026-11-05
---
The raw-store probe, which answers from stored data before calling WCL, runs inside the
client's single-flight and lane slot, before the 429 block check. Stored answers therefore
keep working while WCL is rate-limited. The fetch source is an object with `__call__` and
`scope()`, installed by `set_fetch_source` in `main.py`. CLI, evals and tests run without
one, so their request path is unchanged.
