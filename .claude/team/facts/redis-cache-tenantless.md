---
id: redis-cache-tenantless
anchors: [sym:wcl_agent/cache/cache.py::mark_unshareable, file:wcl_agent/cache/cache.py, comp:redis]
by: dev-1 Ansel
source: meta/team/dev-1.md L15; meta/sprints/2026-11-01/board.jsonl #36
verified: 03a3982 2026-11-07
---
The shared Redis cache is tenant-less: keys never hold a user, tenant or conversation id,
every workspace reads the same entry, and loaders back-fill it on a miss. A load that served
data only one tenant may see (a grant-only raw-store hit) must call `mark_unshareable()`, so
the result skips Redis and the memo. Any new read layer under `get_or_load` that serves
tenant-private data without that mark leaks it to every workspace.
