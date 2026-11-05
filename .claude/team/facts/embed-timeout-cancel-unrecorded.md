---
id: embed-timeout-cancel-unrecorded
anchors: [sym:backend/app/kb/search.py::_embed, sym:backend/app/kb/embedder.py::VertexEmbedder._request]
by: dev-3 Nils
source: meta/sprints/2026-11-05/board.jsonl #106, #107
verified: ec24bad 2026-11-05
---
KB search's `asyncio.timeout(EMBED_TIMEOUT_S)` (3.0 s) cancels the provider call, so the
embedder sees `CancelledError`, a BaseException. `VertexEmbedder._request` records a query in
`except BaseException` and re-raises; `except Exception` leaves D8 blank in an outage (sc-503).
A cancelled document request (indexer shutdown) isn't recorded. Queries run in a `TaskGroup`
(`gather` would leave siblings retrying), whose own cancellation hides a swallowed cancel: test
that on the document path. Query retry waits end by `QUERY_DEADLINE_S`: a 429 records
`ModelRateLimited`.
