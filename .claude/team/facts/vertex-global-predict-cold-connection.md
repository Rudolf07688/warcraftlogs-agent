---
id: vertex-global-predict-cold-connection
anchors: [sym:wcl_agent/llm/generation.py::embed_texts, file:backend/app/kb/embedder.py]
by: dev-3 Nils
source: 061 board #23
verified: 0678ea7 2026-11-05
---
On Vertex, google-genai sends gemini-embedding-001 to `:predict` (not embedContent). The
`global` endpoint answers :predict about 12 s late on every NEW connection (even a 401; measured
2026-11-05), then ~0.5-1 s on that connection; httpx closes idle connections after 5 s. So
embeddings run at the regional `kb_embed_location` (`embed_texts(location=)`, its own cached
client). Unauthenticated curl timings reproduce it without spending tokens.
