---
id: loki-structured-metadata-64k
anchors: [sym:backend/app/telemetry/redaction.py::_fit_content, comp:loki]
by: dev-3 Nils
source: meta/sprints/2026-11-04/board.jsonl #52, #62
verified: b9cf9a3 2026-11-05
---
Loki refuses a record whose structured metadata is over 64 KiB (400 "structured metadata
too large"), and OTLP log attributes become structured metadata. So the backend cuts dev
content records to `CONTENT_RECORD_BUDGET` (32,000 chars) before scrubbing and marks them
`app.content.truncated="true"`. Any new log path that carries big attributes needs a
similar bound.
