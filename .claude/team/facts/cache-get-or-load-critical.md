---
id: cache-get-or-load-critical
anchors: [sym:wcl_agent/cache/cache.py::get_or_load, sym:wcl_agent/cache/cache.py::_shared, comp:redis]
by: dev-1 Ansel
source: meta/team/dev-1.md L12; meta/sprints/2026-11-01b/board.jsonl #44; meta/sprints/2026-11-02/board.jsonl #33
verified: 03a3982 2026-11-07
---
GitNexus rates `get_or_load` and `_shared` CRITICAL (63 upstream at b9cf9a3): every cached
WCL read goes through them. Keep changes additive: don't change values, TTLs, locks or the
unshareable handling. Run the full suite and the cache tests (`test_wcl_cache`, the 047
local-rate tests) before hand-off.
