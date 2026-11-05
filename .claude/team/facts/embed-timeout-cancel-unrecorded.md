---
id: embed-timeout-cancel-unrecorded
anchors: [sym:backend/app/kb/search.py::_embed, sym:backend/app/kb/embedder.py::VertexEmbedder.embed]
by: lead
source: meta/sprints/2026-11-05/board.jsonl #106, #107
verified: b9cf9a3 2026-11-05
---
KB search wraps the query embedding in `asyncio.timeout(EMBED_TIMEOUT_S)` (3.0 s). The
timeout cancels the provider call, so `VertexEmbedder.embed` sees `CancelledError`, which its
`except Exception` doesn't catch, and records nothing. Timed-out query embeddings leave no
`app_embedding_*` series (sc-503). Live query embeddings take about 3 s on this host, so
semantic search keeps falling back to keywords (sc-428).
