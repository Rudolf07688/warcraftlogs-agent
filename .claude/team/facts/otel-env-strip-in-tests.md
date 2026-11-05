---
id: otel-env-strip-in-tests
anchors: [file:backend/tests/conftest.py, file:bin/claude-otel, sym:backend/app/telemetry/config.py::load_config]
by: po Maren
source: meta/team/po.md L36; meta/sprints/2026-11-04/board.jsonl #38
verified: b9cf9a3 2026-11-05
---
Backend telemetry switches on from `OTEL_EXPORTER_OTLP_ENDPOINT` alone, and the standard
`OTEL_*` names reach every child process of a shell that set them (`bin/claude-otel` exports
them for Claude Code). `backend/tests/conftest.py` deletes every `OTEL_*` at import. A new
script or tool that starts the backend outside pytest must clear them too, or it exports
into someone else's stack.
