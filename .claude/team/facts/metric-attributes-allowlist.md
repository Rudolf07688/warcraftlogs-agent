---
id: metric-attributes-allowlist
anchors: [sym:backend/app/telemetry/setup.py::METRIC_ATTRIBUTES, file:backend/app/telemetry/metrics.py]
by: dev-3 Nils
source: meta/sprints/2026-11-04b/board.jsonl #37; meta/sprints/2026-11-04/board.jsonl #38
verified: 32010a6 2026-11-05
---
A backend metric label survives only if its key is in `setup.METRIC_ATTRIBUTES`: one global
allowlist, applied through a View to every instrument, library ones included. New app
attributes are enums namespaced `app.*` (`app.cache.name`, `app.rag.index`), because a bare
key like `result` would let any library's attribute of that name through. `session.id` is
never a metric label.
