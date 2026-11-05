---
id: tombstones-single-process
anchors: [sym:backend/app/services/fetch_persistence.py::_bury, file:backend/Dockerfile]
by: dev-2 Tomas
source: meta/sprints/2026-11-01/board.jsonl #50
verified: b9cf9a3 2026-11-05
---
Report-gone tombstones live in the writer process (`fetch_persistence._tombstones`, at most
1024 codes, 10-minute TTL). A fetch whose `requested_at` is at or before a code's tombstone is not
stored. That is sound only because one uvicorn process runs one writer (`backend/Dockerfile`
starts uvicorn with no `--workers`). More workers or a second writer process break the
private-report race guard.
