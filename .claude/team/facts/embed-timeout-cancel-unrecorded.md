---
id: embed-timeout-cancel-unrecorded
anchors: [sym:backend/app/kb/search.py::_embed, sym:backend/app/kb/embedder.py::VertexEmbedder._request]
by: lead; fixed by dev-3 Nils (061)
source: meta/sprints/2026-11-05/board.jsonl #106, #107
verified: 9989a02 2026-11-05
---
KB search wraps the query embedding in `asyncio.timeout(EMBED_TIMEOUT_S)` (3.0 s), which
cancels the provider call: the embedder sees `CancelledError`, a BaseException. So
`VertexEmbedder._request` records in `except BaseException` (error.type `CancelledError`) and
re-raises; an `except Exception` there leaves D8 blank during an outage (sc-503). Query
requests run under `asyncio.gather`, whose own cancellation hides a swallowed cancel: test
that on the document path.
