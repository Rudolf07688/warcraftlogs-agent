---
id: sqlcommenter-baggage
anchors: [sym:backend/app/telemetry/setup.py::instrument]
by: dev-1 Ansel
source: meta/team/dev-1.md L21; meta/sprints/2026-11-05/board.jsonl #64
verified: b9cf9a3 2026-11-05
---
opentelemetry-instrumentation-sqlalchemy 0.63b1 builds the SQL comment with a module-level
`TraceContextTextMapPropagator`: it can inject `traceparent` and `tracestate`, never baggage.
`"tracestate": False` in `commenter_options` is the real guard. `"baggage": False` only
guards against a future upgrade, so a mutation that removes it can't bite. Check claims
about library behaviour against the installed code in `.venv`.
